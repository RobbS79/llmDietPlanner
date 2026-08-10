"""Refine-chat endpoint (POST /api/recipes/<meal_identifier>/refine/).

Preview turns NEVER write; only an accept turn commits.
Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import CuratedRecipe, DietaryGoal, DietaryPlan, MealInstance, Recipe
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.tests.test_recipe_replace import make_recipe


class RefineTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _plan_with_lunch(self, recipe):
        from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
        meal = scale_recipe_to_meal(recipe)
        meal['meal_identifier'] = f'{self.goal.id}:1:lunch:0'
        return DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{'day_number': 1, 'lunch': meal, 'small_meals': [], 'snacks': []}],
            currency='CZK',
        )

    def _url(self):
        return reverse(
            'diet_planner:recipe-refine',
            kwargs={'meal_identifier': f'{self.goal.id}:1:lunch:0'},
        )

    def _preview(self, messages, rejected_ids=None):
        return self.client.post(
            self._url(),
            {'messages': messages, 'rejected_ids': rejected_ids or []},
            format='json',
        )


USER_MSG = [{'role': 'user', 'text': 'něco s kuřecím'}]


class PreviewTurnTest(RefineTestBase):
    def test_returns_candidate_question_and_match_flag_without_writing(self):
        current = make_recipe(name_cs='Kuře s rýží')
        chicken = make_recipe(name_cs='Kuřecí salát', ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
        ])
        plan = self._plan_with_lunch(current)
        before = plan.days

        facets = PromptFacets(wanted_ingredients={'kuřecí'})
        with patch('diet_planner.views.refine_conversation',
                   return_value=(facets, 'Chcete to spíš rychlé?')) as m:
            resp = self._preview(USER_MSG)

        self.assertEqual(resp.status_code, 200)
        m.assert_called_once()
        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], chicken.id)
        self.assertEqual(body['candidate']['name'], 'Kuřecí salát')
        self.assertEqual(body['candidate']['why'], 'Odpovídá: kuřecí prsa')
        self.assertEqual(body['question'], 'Chcete to spíš rychlé?')
        self.assertTrue(body['hint_matched'])
        # PREVIEW MUST NOT WRITE: plan untouched, no Recipe row churn,
        # no usage bump, no cooked-state reset.
        plan.refresh_from_db()
        self.assertEqual(plan.days, before)
        chicken.refresh_from_db()
        self.assertEqual(chicken.usage_count, 0)
        self.assertFalse(Recipe.objects.filter(name='Kuřecí salát').exists())

    def test_rejected_ids_are_excluded_from_selection(self):
        current = make_recipe(name_cs='Kuře s rýží')
        first = make_recipe(name_cs='Hovězí guláš')
        second = make_recipe(name_cs='Těstoviny', cuisine='italian')

        self._plan_with_lunch(current)
        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG, rejected_ids=[first.id])

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], second.id)

    def test_empty_facets_flags_no_match_but_still_offers_candidate(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG)

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], other.id)
        self.assertFalse(body['hint_matched'])
        self.assertIsNone(body['question'])
        self.assertIsNone(body['candidate']['why'])

    def test_unmatchable_facets_fall_back_to_next_best(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš', ingredients=[
            {'name': 'hovězí', 'quantity': 150, 'unit': 'g', 'canonical': 'beef-chuck'},
        ])
        self._plan_with_lunch(current)

        facets = PromptFacets(wanted_ingredients={'tofu'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview(USER_MSG)

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], other.id)
        self.assertFalse(body['hint_matched'])

    def test_all_alternatives_rejected_reports_no_alternatives(self):
        current = make_recipe(name_cs='Kuře s rýží')
        only_other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG, rejected_ids=[only_other.id])

        body = resp.data['data']
        self.assertIsNone(body['candidate'])
        self.assertEqual(body['reason'], 'no_alternatives')

    def test_messages_are_clamped_before_the_llm_sees_them(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)

        oversized = [{'role': 'user', 'text': f'zpráva {i}'} for i in range(30)]
        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)) as m:
            self._preview(oversized)

        passed = m.call_args.args[0]
        self.assertLessEqual(len(passed), 16)
        self.assertLessEqual(sum(1 for x in passed if x['role'] == 'user'), 8)

    def test_oversized_rejected_id_string_is_ignored_not_500(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)
        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG, rejected_ids=['9' * 5000])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['candidate']['curated_recipe_id'], other.id)

    def test_cuisine_in_why_line_is_czech_never_raw_slug(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Svíčková', cuisine='czech')
        self._plan_with_lunch(current)

        facets = PromptFacets(cuisines={'czech'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview(USER_MSG)

        why = resp.data['data']['candidate']['why']
        self.assertEqual(why, 'Odpovídá: česká kuchyně')

    def test_unknown_cuisine_slug_is_dropped_from_why_line(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Kimchi bowl', cuisine='korean')
        self._plan_with_lunch(current)

        facets = PromptFacets(cuisines={'korean'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview(USER_MSG)

        # Matched on cuisine (hint honored) but the slug has no Czech label:
        # better no why-line than an English leak.
        body = resp.data['data']
        self.assertTrue(body['hint_matched'])
        self.assertIsNone(body['candidate']['why'])

    def test_other_users_meal_is_404(self):
        current = make_recipe(name_cs='Kuře')
        make_recipe(name_cs='Hovezí')
        self._plan_with_lunch(current)
        intruder = get_user_model().objects.create(username='intruder')
        other = APIClient()
        other.force_authenticate(user=intruder)
        resp = other.post(self._url(), {'messages': USER_MSG, 'rejected_ids': []}, format='json')
        self.assertEqual(resp.status_code, 404)


class ProfilePreferencesGateTest(RefineTestBase):
    """Profile dietary preferences must constrain refine candidates — the user
    set them once; every surface honors them (no re-stating in chat needed)."""

    def _set_profile_styles(self, styles):
        profile = self.user.profile
        profile.dietary_preferences = {'dietary_styles': styles, 'allergies': ['none']}
        profile.save()

    def test_preview_offers_only_profile_compatible_candidates(self):
        self._set_profile_styles(['gluten_free'])
        current = make_recipe(name_cs='Kuře s rýží', dietary_tags=['gluten_free'])
        make_recipe(name_cs='Zapečené těstoviny')  # not gluten-free
        self._plan_with_lunch(current)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG)

        # The only alternative violates the profile → honest no-alternatives,
        # never a gluten dish for a gluten-free profile.
        self.assertIsNone(resp.data['data']['candidate'])
        self.assertEqual(resp.data['data']['reason'], 'no_alternatives')

        safe = make_recipe(name_cs='Rizoto', dietary_tags=['gluten_free'])
        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview(USER_MSG)
        self.assertEqual(resp.data['data']['candidate']['curated_recipe_id'], safe.id)

    def test_accept_rejects_profile_incompatible_recipe(self):
        self._set_profile_styles(['gluten_free'])
        current = make_recipe(name_cs='Kuře s rýží', dietary_tags=['gluten_free'])
        gluten = make_recipe(name_cs='Zapečené těstoviny')
        plan = self._plan_with_lunch(current)
        before = plan.days

        resp = self.client.post(self._url(), {'accept': gluten.id}, format='json')

        self.assertEqual(resp.status_code, 400)
        plan.refresh_from_db()
        self.assertEqual(plan.days, before)


class ChatStatedRestrictionsTest(RefineTestBase):
    def test_chat_dietary_is_a_hard_gate_never_relaxed_by_fallback(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Zapečené těstoviny')  # not gluten-free
        self._plan_with_lunch(current)

        facets = PromptFacets(dietary={'gluten_free'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview([{'role': 'user', 'text': 'nejím lepek'}])

        # "nejím lepek" must NOT degrade to offering a gluten dish.
        body = resp.data['data']
        self.assertIsNone(body['candidate'])
        self.assertEqual(body['reason'], 'no_alternatives')

    def test_chat_dietary_offers_compatible_candidate(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Zapečené těstoviny')
        safe = make_recipe(name_cs='Rizoto', dietary_tags=['gluten_free'])
        self._plan_with_lunch(current)

        facets = PromptFacets(dietary={'gluten_free'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview([{'role': 'user', 'text': 'nejím lepek'}])

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], safe.id)
        self.assertTrue(body['hint_matched'])


class PlanTimeBudgetTest(RefineTestBase):
    """A cooking-time limit stated in the PLAN prompt keeps applying inside the
    chat (prod goal 141: prompt said max 30 min, chat offered 35/45/90).

    These cover the v1 facet path — the fallback the endpoint serves whenever
    the agent is off or crashes, so the promise must hold on both paths.
    """

    def _plan_with_budget(self, recipe, minutes):
        plan = self._plan_with_lunch(recipe)
        plan.grounding_debug = {'facets': {'max_time_minutes': minutes},
                                'coverage': {'filled': 1, 'total': 1}}
        plan.save(update_fields=['grounding_debug'])
        return plan

    def test_slow_dish_is_not_offered_even_when_it_fits_the_wish(self):
        # The slow dish is exactly what the user asked for and outranks the
        # quick one by 20 points — the time cap must still keep it out.
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Pečené koleno', prep_time=30, cook_time=60, ingredients=[
            {'name': 'vepřové koleno', 'quantity': 1000, 'unit': 'g',
             'canonical': 'pork-knuckle'},
        ])
        quick = make_recipe(name_cs='Rychlá omeleta', prep_time=5, cook_time=10)
        self._plan_with_budget(current, 30)

        facets = PromptFacets(wanted_ingredients={'vepřové'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview([{'role': 'user', 'text': 'něco vepřového'}])

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], quick.id)
        self.assertFalse(body['hint_matched'])  # honest: the wish didn't fit

    def test_limit_survives_the_unmatched_facets_fallback(self):
        # Facets nobody can satisfy fall back to "next best" — which must still
        # be next-best WITHIN the time the user has. The slow dish is the
        # better-ranked one (easy vs medium), so only the cap can exclude it.
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Pečené koleno', prep_time=30, cook_time=60,
                    difficulty=CuratedRecipe.Difficulty.EASY)
        quick = make_recipe(name_cs='Rychlá omeleta', prep_time=5, cook_time=10,
                            difficulty=CuratedRecipe.Difficulty.MEDIUM)
        self._plan_with_budget(current, 30)

        facets = PromptFacets(cuisines={'klingon'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview([{'role': 'user', 'text': 'něco klingonského'}])

        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], quick.id)
        self.assertFalse(body['hint_matched'])

    def test_nothing_fits_the_limit_is_reported_honestly(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Pečené koleno', prep_time=30, cook_time=60)
        self._plan_with_budget(current, 30)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview([{'role': 'user', 'text': 'něco jiného'}])

        body = resp.data['data']
        self.assertIsNone(body['candidate'])
        self.assertEqual(body['reason'], 'no_alternatives')

    def test_a_limit_restated_in_the_chat_wins(self):
        current = make_recipe(name_cs='Kuře s rýží')
        slow = make_recipe(name_cs='Pečené koleno', prep_time=30, cook_time=60)
        self._plan_with_budget(current, 30)

        # "Dneska mám čas" — the newer explicit limit replaces the old one.
        facets = PromptFacets(max_time_minutes=120)
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview([{'role': 'user', 'text': 'dnes mám klidně dvě hodiny'}])

        self.assertEqual(resp.data['data']['candidate']['curated_recipe_id'], slow.id)

    def test_no_stated_limit_leaves_everything_on_the_table(self):
        current = make_recipe(name_cs='Kuře s rýží')
        slow = make_recipe(name_cs='Pečené koleno', prep_time=30, cook_time=60)
        self._plan_with_lunch(current)  # no grounding_debug at all

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview([{'role': 'user', 'text': 'něco jiného'}])

        self.assertEqual(resp.data['data']['candidate']['curated_recipe_id'], slow.id)


class WhyLineIngredientTest(RefineTestBase):
    def test_why_line_shows_recipe_ingredient_not_facet_token(self):
        # The LLM normalizes "testoviny" -> token "pasta"; the user must see
        # the recipe's actual Czech ingredient, never the internal token.
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Boloňské špagety', ingredients=[
            {'name': 'těstoviny penne', 'quantity': 100, 'unit': 'g', 'canonical': 'pasta-penne'},
        ])
        self._plan_with_lunch(current)

        facets = PromptFacets(wanted_ingredients={'pasta'})
        with patch('diet_planner.views.refine_conversation', return_value=(facets, None)):
            resp = self._preview(USER_MSG)

        why = resp.data['data']['candidate']['why']
        self.assertEqual(why, 'Odpovídá: těstoviny penne')
        self.assertNotIn('pasta', why)


class AcceptTurnTest(RefineTestBase):
    def test_accept_commits_the_swap_with_all_side_effects(self):
        from django.utils import timezone
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        plan = self._plan_with_lunch(current)
        ident = f'{self.goal.id}:1:lunch:0'
        MealInstance.objects.create(
            user=self.user, dietary_goal=self.goal, meal_identifier=ident,
            meal_name='Kuře s rýží', day_number=1, meal_type='lunch',
            is_cooked=True, cooked_at=timezone.now(),
        )

        resp = self.client.post(self._url(), {'accept': other.id}, format='json')

        self.assertEqual(resp.status_code, 200)
        body = resp.data['data']
        self.assertTrue(body['replaced'])
        self.assertEqual(body['recipe']['name'], 'Hovězí guláš')
        plan.refresh_from_db()
        lunch = plan.days[0]['lunch']
        self.assertEqual(lunch['curated_recipe_id'], other.id)
        self.assertEqual(lunch['meal_identifier'], ident)
        other.refresh_from_db()
        self.assertEqual(other.usage_count, 1)
        mi = MealInstance.objects.get(meal_identifier=ident, user=self.user)
        self.assertFalse(mi.is_cooked)
        self.assertIsNone(mi.cooked_at)

    def test_accept_returns_the_replaced_recipe_so_the_swap_can_be_undone(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)

        resp = self.client.post(self._url(), {'accept': other.id}, format='json')

        self.assertEqual(resp.data['data']['previous'],
                         {'curated_recipe_id': current.id, 'name': 'Kuře s rýží'})

    def test_undo_swaps_straight_back_to_the_previous_recipe(self):
        # The whole point of returning `previous`: accepting it must be valid,
        # which holds because _accept only ever excludes the CURRENT recipe.
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        plan = self._plan_with_lunch(current)

        self.client.post(self._url(), {'accept': other.id}, format='json')
        undo = self.client.post(self._url(), {'accept': current.id}, format='json')

        self.assertEqual(undo.status_code, 200)
        self.assertEqual(undo.data['data']['recipe']['name'], 'Kuře s rýží')
        plan.refresh_from_db()
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], current.id)

    def test_previous_is_null_when_the_meal_had_no_corpus_recipe(self):
        other = make_recipe(name_cs='Hovězí guláš')
        plan = self._plan_with_lunch(other)
        # An LLM-generated meal carries no curated_recipe_id — nothing to
        # return to, so the UI must not offer an undo.
        del plan.days[0]['lunch']['curated_recipe_id']
        plan.save(update_fields=['days'])
        replacement = make_recipe(name_cs='Svíčková')

        resp = self.client.post(self._url(), {'accept': replacement.id}, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.data['data']['previous'])

    def test_accept_makes_no_llm_call(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)
        with patch('diet_planner.views.refine_conversation') as m:
            resp = self.client.post(self._url(), {'accept': other.id}, format='json')
        self.assertEqual(resp.status_code, 200)
        m.assert_not_called()

    def test_accept_rejects_ineligible_recipe_without_writing(self):
        current = make_recipe(name_cs='Kuře s rýží')
        # Wrong slot: breakfast-only recipe is NOT eligible for lunch.
        breakfast_only = make_recipe(name_cs='Ovesná kaše', meal_types=['breakfast'])
        plan = self._plan_with_lunch(current)
        before = plan.days

        resp = self.client.post(self._url(), {'accept': breakfast_only.id}, format='json')

        self.assertEqual(resp.status_code, 400)
        plan.refresh_from_db()
        self.assertEqual(plan.days, before)
        breakfast_only.refresh_from_db()
        self.assertEqual(breakfast_only.usage_count, 0)

    def test_accept_rejects_the_current_recipe_itself(self):
        current = make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(current)
        resp = self.client.post(self._url(), {'accept': current.id}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_accept_rejects_garbage_id(self):
        current = make_recipe(name_cs='Kuře s rýží')
        self._plan_with_lunch(current)
        resp = self.client.post(self._url(), {'accept': 'DROP TABLE'}, format='json')
        self.assertEqual(resp.status_code, 400)


class CandidateCardPortionTest(RefineTestBase):
    """The kcal on a candidate card must be the portion the user would actually
    be served — the same number the accept turn commits. Showing the whole pot
    (base_nutrition) misinforms the very choice the card exists to support."""

    def test_candidate_card_shows_per_portion_calories_not_the_whole_pot(self):
        current = make_recipe(name_cs='Aktuální oběd', base_servings=1,
                              base_nutrition={'calories': 500, 'protein': 30,
                                              'carbs': 60, 'fat': 12})
        make_recipe(name_cs='Velký hrnec', base_servings=6,
                    base_nutrition={'calories': 3000, 'protein': 180,
                                    'carbs': 360, 'fat': 72})
        self._plan_with_lunch(current)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            resp = self._preview([{'role': 'user', 'text': 'něco jiného'}])

        card = resp.json()['data']['candidate']
        self.assertEqual(card['name'], 'Velký hrnec')
        self.assertEqual(card['calories'], 500)

    def test_candidate_card_matches_what_accepting_it_commits(self):
        current = make_recipe(name_cs='Aktuální oběd', base_servings=1,
                              base_nutrition={'calories': 500, 'protein': 30,
                                              'carbs': 60, 'fat': 12})
        big = make_recipe(name_cs='Velký hrnec', base_servings=6,
                          base_nutrition={'calories': 3000, 'protein': 180,
                                          'carbs': 360, 'fat': 72})
        plan = self._plan_with_lunch(current)

        with patch('diet_planner.views.refine_conversation',
                   return_value=(PromptFacets(), None)):
            previewed = self._preview([{'role': 'user', 'text': 'něco jiného'}])
        card = previewed.json()['data']['candidate']

        self.client.post(self._url(), {'accept': big.id}, format='json')
        plan.refresh_from_db()
        committed = plan.days[0]['lunch']['nutritional_info']['calories']

        self.assertEqual(card['calories'], committed)
