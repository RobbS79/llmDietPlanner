"""Replace-recipe swap endpoint (POST /api/recipes/<meal_identifier>/replace/).

Curated-corpus-only swap for one plan slot, optionally steered by a free-text
hint. Spec: docs/superpowers/specs/2026-07-16-replace-recipe-swap-design.md.
"""
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from diet_planner.models import (
    CuratedRecipe,
    DietaryGoal,
    DietaryPlan,
    MealInstance,
    Recipe,
)
from diet_planner.services.prompt_facets import PromptFacets


def make_recipe(**kw):
    """A published, fully catalog-mapped CuratedRecipe (passes the hard gate)."""
    defaults = dict(
        name_cs=kw.pop('name_cs', 'Test dish'),
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=['lunch', 'dinner'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'}],
        instructions=[{'text': 'Uvař rýži a podávej.', 'time_min': 10, 'tip': None}],
        base_servings=1,
        base_nutrition={'calories': 500, 'protein': 30, 'carbs': 60, 'fat': 12},
        source_url='https://example.test/r',
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class ReplaceRecipeTestBase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='chef')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _plan_with_lunch(self, recipe):
        """A plan whose lunch slot is served from `recipe` (curated)."""
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
            'diet_planner:recipe-replace',
            kwargs={'meal_identifier': f'{self.goal.id}:1:lunch:0'},
        )


class BlankHintSwapTest(ReplaceRecipeTestBase):
    def test_swaps_to_a_different_curated_recipe(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        plan = self._plan_with_lunch(current)

        resp = self.client.post(self._url(), {'hint': ''}, format='json')

        self.assertEqual(resp.status_code, 200)
        body = resp.data['data']
        self.assertTrue(body['replaced'])
        self.assertIsNone(body['hint_matched'])
        # The lunch slot now holds the *other* recipe, not the current one.
        plan.refresh_from_db()
        lunch = plan.days[0]['lunch']
        self.assertEqual(lunch['curated_recipe_id'], other.id)
        self.assertEqual(lunch['name'], 'Hovězí guláš')
        # Identifier is preserved so the plan/recipe routes still address it.
        self.assertEqual(lunch['meal_identifier'], f'{self.goal.id}:1:lunch:0')
        # Response carries the serialized new recipe in RecipeDetailView shape.
        self.assertEqual(body['recipe']['name'], 'Hovězí guláš')
        self.assertIn('deals', body['recipe'])
        self.assertIn('price_range', body['recipe'])

    def test_never_returns_the_current_recipe(self):
        # Only the current recipe is eligible -> nothing else to swap to.
        current = make_recipe(name_cs='Jediné jídlo')
        plan = self._plan_with_lunch(current)

        resp = self.client.post(self._url(), {'hint': ''}, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['data']['replaced'])
        self.assertEqual(resp.data['data']['reason'], 'no_alternatives')


class HintSteeringTest(ReplaceRecipeTestBase):
    def test_hint_filters_candidates(self):
        current = make_recipe(name_cs='Kuře s rýží')
        chicken = make_recipe(name_cs='Kuřecí salát', ingredients=[
            {'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'},
        ])
        make_recipe(name_cs='Hovězí guláš', ingredients=[
            {'name': 'hovězí', 'quantity': 150, 'unit': 'g', 'canonical': 'beef-chuck'},
        ])
        plan = self._plan_with_lunch(current)

        facets = PromptFacets(wanted_ingredients={'kuřecí'})
        with patch('diet_planner.views.extract_prompt_facets', return_value=facets) as m:
            resp = self.client.post(self._url(), {'hint': 'něco s kuřecím'}, format='json')

        self.assertEqual(resp.status_code, 200)
        m.assert_called_once()
        body = resp.data['data']
        self.assertTrue(body['replaced'])
        self.assertTrue(body['hint_matched'])
        plan.refresh_from_db()
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], chicken.id)

    def test_hint_no_match_falls_back_to_next_best(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš', ingredients=[
            {'name': 'hovězí', 'quantity': 150, 'unit': 'g', 'canonical': 'beef-chuck'},
        ])
        plan = self._plan_with_lunch(current)

        # A hint no eligible recipe satisfies -> retry without facets.
        facets = PromptFacets(wanted_ingredients={'tofu'})
        with patch('diet_planner.views.extract_prompt_facets', return_value=facets):
            resp = self.client.post(self._url(), {'hint': 'něco s tofu'}, format='json')

        self.assertEqual(resp.status_code, 200)
        body = resp.data['data']
        self.assertTrue(body['replaced'])
        self.assertFalse(body['hint_matched'])
        plan.refresh_from_db()
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], other.id)

    def test_empty_facets_from_llm_failure_flags_no_match(self):
        # extract_prompt_facets NEVER raises: on any LLM error it returns empty
        # facets, which match every recipe. A dropped hint must therefore report
        # hint_matched=False, not masquerade as a successful match.
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        plan = self._plan_with_lunch(current)

        with patch('diet_planner.views.extract_prompt_facets', return_value=PromptFacets()):
            resp = self.client.post(self._url(), {'hint': 'něco s kuřecím'}, format='json')

        self.assertEqual(resp.status_code, 200)
        body = resp.data['data']
        self.assertTrue(body['replaced'])
        self.assertFalse(body['hint_matched'])
        plan.refresh_from_db()
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], other.id)

    def test_blank_hint_makes_no_llm_call(self):
        make_recipe(name_cs='Kuře s rýží')
        make_recipe(name_cs='Hovězí guláš')
        self._plan_with_lunch(CuratedRecipe.objects.first())
        with patch('diet_planner.views.extract_prompt_facets') as m:
            resp = self.client.post(self._url(), {'hint': '   '}, format='json')
        self.assertEqual(resp.status_code, 200)
        m.assert_not_called()


class NoAlternativesNoWriteTest(ReplaceRecipeTestBase):
    def test_no_alternatives_writes_nothing(self):
        current = make_recipe(name_cs='Jediné jídlo')
        plan = self._plan_with_lunch(current)
        before = plan.days

        resp = self.client.post(self._url(), {'hint': ''}, format='json')

        self.assertFalse(resp.data['data']['replaced'])
        plan.refresh_from_db()
        self.assertEqual(plan.days, before)
        current.refresh_from_db()
        self.assertEqual(current.usage_count, 0)


class CuisineVarietyTest(ReplaceRecipeTestBase):
    def test_swap_avoids_a_cuisine_already_dominating_the_plan(self):
        from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
        # Breakfast is already czech, so a lunch swap should prefer a *different*
        # cuisine rather than serving yet another near-identical czech dish.
        breakfast = make_recipe(name_cs='Česká snídaně', cuisine='czech', meal_types=['breakfast'])
        current = make_recipe(name_cs='Kuře s rýží', cuisine='czech')
        # The czech alt is MORE popular, so it wins on score UNLESS the
        # cuisine-monotony penalty (breakfast is already czech) is applied.
        make_recipe(name_cs='Svíčková', cuisine='czech', usage_count=10)
        italian = make_recipe(name_cs='Těstoviny', cuisine='italian')

        bmeal = scale_recipe_to_meal(breakfast)
        bmeal['meal_identifier'] = f'{self.goal.id}:1:breakfast:0'
        lmeal = scale_recipe_to_meal(current)
        lmeal['meal_identifier'] = f'{self.goal.id}:1:lunch:0'
        DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{'day_number': 1, 'breakfast': bmeal, 'lunch': lmeal, 'small_meals': [], 'snacks': []}],
            currency='CZK',
        )

        resp = self.client.post(self._url(), {'hint': ''}, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['replaced'])
        plan = DietaryPlan.objects.get(dietary_goal=self.goal)
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], italian.id)


class OwnershipTest(ReplaceRecipeTestBase):
    def test_other_users_meal_is_404(self):
        current = make_recipe(name_cs='Kuře')
        make_recipe(name_cs='Hovězí')
        plan = self._plan_with_lunch(current)

        intruder = get_user_model().objects.create(username='intruder')
        other_client = APIClient()
        other_client.force_authenticate(user=intruder)

        resp = other_client.post(self._url(), {'hint': ''}, format='json')

        self.assertEqual(resp.status_code, 404)
        plan.refresh_from_db()
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], current.id)


class SideEffectsTest(ReplaceRecipeTestBase):
    def test_stale_recipe_deleted_cooked_reset_and_usage_bumped(self):
        current = make_recipe(name_cs='Kuře s rýží')
        other = make_recipe(name_cs='Hovězí guláš')
        plan = self._plan_with_lunch(current)
        ident = f'{self.goal.id}:1:lunch:0'

        # A stale cached Recipe row for the OLD meal, and a cooked log entry.
        stale = Recipe.objects.create(
            meal_identifier=ident, dietary_goal=self.goal,
            name='Kuře s rýží', servings=1,
            instructions=['Uvař starou verzi.'],
            ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g'}],
        )
        stale_pk = stale.pk
        MealInstance.objects.create(
            user=self.user, dietary_goal=self.goal, meal_identifier=ident,
            meal_name='Kuře s rýží', day_number=1, meal_type='lunch',
            is_cooked=True, cooked_at=timezone.now(),
        )

        resp = self.client.post(self._url(), {'hint': ''}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['replaced'])

        # The cached row is refreshed IN PLACE (same pk) so a previously-public
        # /recepty/<pk>/ URL is not orphaned, and it now reflects the new dish.
        row = Recipe.objects.get(meal_identifier=ident)
        self.assertEqual(row.pk, stale_pk)
        self.assertEqual(row.name, 'Hovězí guláš')

        # Cooked state cleared so the new recipe doesn't show "Uvařeno".
        mi = MealInstance.objects.get(meal_identifier=ident, user=self.user)
        self.assertFalse(mi.is_cooked)
        self.assertIsNone(mi.cooked_at)

        # Plan rewritten + usage bumped on the chosen recipe.
        plan.refresh_from_db()
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], other.id)
        other.refresh_from_db()
        self.assertEqual(other.usage_count, 1)


class PortionedSwapTest(ReplaceRecipeTestBase):
    """A swap must serve a portion sized to the outgoing meal's calories, not
    the incoming recipe's whole multi-serving yield (goal 133)."""

    def test_swap_serves_portion_sized_to_outgoing_meal(self):
        current = make_recipe(name_cs='Aktuální oběd')          # 500 kcal / 1 serving
        make_recipe(name_cs='Velký hrnec', base_servings=6,
                    base_nutrition={'calories': 3000, 'protein': 120, 'carbs': 300, 'fat': 90},
                    ingredients=[{'name': 'rýže', 'quantity': 600, 'unit': 'g',
                                  'canonical': 'rice-basmati'}])
        plan = self._plan_with_lunch(current)
        resp = self.client.post(self._url(), {'hint': ''}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['replaced'])
        plan.refresh_from_db()
        meal = plan.days[0]['lunch']
        # 3000/6 = 500 kcal/portion; outgoing meal was 500 kcal -> 1 portion.
        self.assertEqual(meal['servings'], 1)
        self.assertEqual(meal['nutritional_info']['calories'], 500)
        self.assertEqual(meal['ingredients'][0]['quantity'], 100)
