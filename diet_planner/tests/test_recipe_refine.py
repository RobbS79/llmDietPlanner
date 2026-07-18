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
        self.assertEqual(body['candidate']['why'], 'Odpovídá: kuřecí')
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

    def test_other_users_meal_is_404(self):
        current = make_recipe(name_cs='Kuře')
        make_recipe(name_cs='Hovezí')
        self._plan_with_lunch(current)
        intruder = get_user_model().objects.create(username='intruder')
        other = APIClient()
        other.force_authenticate(user=intruder)
        resp = other.post(self._url(), {'messages': USER_MSG, 'rejected_ids': []}, format='json')
        self.assertEqual(resp.status_code, 404)
