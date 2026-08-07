"""Refresh of cached Recipe rows stranded by a corpus revision.

Recipe rows are a write-once cache built from the meal dict on first
recipe-detail GET. Nothing invalidates them when curation later corrects the
CuratedRecipe they came from, so prod accumulated rows whose stored nutrition
matches neither the whole-recipe total nor the per-portion value implied by the
current corpus (5 of 30 curated multi-portion rows as of 2026-08-07).
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from diet_planner.management.commands.refresh_stale_recipe_cache import (
    expected_calories,
    is_stale,
)
from diet_planner.models import DietaryGoal, DietaryPlan, MealInstance, Recipe
from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
from diet_planner.tests.test_recipe_replace import make_recipe


class StalenessDetectionTest(TestCase):
    """A row is consistent when its nutrition equals per-portion x servings —
    the invariant the per-portion display now relies on."""

    def test_expected_calories_scales_per_portion_by_servings(self):
        curated = make_recipe(base_servings=4, base_nutrition={'calories': 1233})
        self.assertAlmostEqual(expected_calories(curated, 2), 616.5, places=1)
        self.assertAlmostEqual(expected_calories(curated, 4), 1233.0, places=1)

    def test_expected_calories_is_none_without_usable_nutrition(self):
        self.assertIsNone(expected_calories(make_recipe(base_nutrition={}), 2))

    def test_consistent_row_is_not_stale(self):
        curated = make_recipe(base_servings=4, base_nutrition={'calories': 1233})
        row = Recipe(servings=2, nutritional_info={'calories': 616})
        self.assertFalse(is_stale(row, curated))

    def test_row_holding_the_whole_base_for_fewer_servings_is_stale(self):
        # Prod recipe 36: servings=5 but nutrition 5286, the full 10-portion
        # base — cached when the corpus still said base_servings=5.
        curated = make_recipe(base_servings=10, base_nutrition={'calories': 5286})
        row = Recipe(servings=5, nutritional_info={'calories': 5286})
        self.assertTrue(is_stale(row, curated))

    def test_small_rounding_differences_are_tolerated(self):
        curated = make_recipe(base_servings=4, base_nutrition={'calories': 1233})
        self.assertFalse(is_stale(Recipe(servings=2, nutritional_info={'calories': 617}), curated))

    def test_row_without_stored_calories_is_not_flagged(self):
        curated = make_recipe(base_servings=4, base_nutrition={'calories': 1233})
        self.assertFalse(is_stale(Recipe(servings=2, nutritional_info={}), curated))


class RefreshCommandTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username='repairer')
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt='týden jídel', num_days=1,
            country='CZ', currency='CZK', language_code='cs',
        )
        # A 10-portion recipe at 529 kcal/portion, cached back when the corpus
        # claimed 5 portions — so the row records servings=5 and the whole base.
        self.curated = make_recipe(
            name_cs='Bramborové halušky s brynzou',
            base_servings=10,
            base_nutrition={'calories': 5286, 'protein': 205, 'carbs': 799, 'fat': 100},
            ingredients=[{'name': 'brambory', 'quantity': 1500, 'unit': 'g',
                          'canonical': 'potato'}],
        )
        self.meal_id = f'{self.goal.id}:1:lunch:0'
        stale_meal = scale_recipe_to_meal(self.curated, portions=10)
        stale_meal['meal_identifier'] = self.meal_id
        stale_meal['servings'] = 5  # what the row was cached with
        self.plan = DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{'day_number': 1, 'lunch': stale_meal, 'small_meals': [], 'snacks': []}],
            currency='CZK',
        )
        self.row = Recipe.objects.create(
            meal_identifier=self.meal_id,
            dietary_goal=self.goal,
            name=self.curated.name_cs,
            servings=5,
            nutritional_info={'calories': 5286},
            ingredients=stale_meal['ingredients'],
            instructions=['Uvař.'],
            curated_recipe_slug=self.curated.slug,
        )

    def _run(self, *args):
        out = StringIO()
        call_command('refresh_stale_recipe_cache', *args, stdout=out)
        return out.getvalue()

    def test_dry_run_reports_the_stale_row_and_changes_nothing(self):
        output = self._run()
        self.assertIn(self.meal_id, output)
        self.row.refresh_from_db()
        self.assertEqual(self.row.servings, 5)
        self.assertEqual(self.row.nutritional_info['calories'], 5286)

    def test_apply_reportions_the_row_to_the_slot_target(self):
        self._run('--apply')
        self.row.refresh_from_db()
        # Lunch defaults to 650 kcal; at 529/portion that is one portion.
        self.assertEqual(self.row.servings, 1)
        self.assertEqual(self.row.nutritional_info['calories'], 529)

    def test_apply_rewrites_the_plan_slot_to_match(self):
        self._run('--apply')
        self.plan.refresh_from_db()
        meal = self.plan.days[0]['lunch']
        self.assertEqual(meal['servings'], 1)
        self.assertEqual(meal['nutritional_info']['calories'], 529)
        self.assertEqual(meal['meal_identifier'], self.meal_id)

    def test_apply_rescales_ingredients_from_the_current_corpus(self):
        self._run('--apply')
        self.row.refresh_from_db()
        # 1500 g across 10 portions, serving 1 → 150 g.
        self.assertEqual(self.row.ingredients[0]['quantity'], 150)

    def test_repair_keeps_the_same_row_pk(self):
        # A substantive row is published at /recepty/<pk>/ — recreating it would
        # orphan that live URL.
        pk_before = self.row.pk
        self._run('--apply')
        self.assertTrue(Recipe.objects.filter(pk=pk_before).exists())

    def test_cooked_state_survives_a_repair(self):
        # The dish is unchanged — only the amounts were wrong. Unlike a swap,
        # a repair must not tell the user they haven't cooked it.
        MealInstance.objects.create(
            meal_identifier=self.meal_id, user=self.user,
            dietary_goal=self.goal, meal_name=self.curated.name_cs,
            day_number=1, meal_type='lunch', is_cooked=True,
        )
        self._run('--apply')
        self.assertTrue(
            MealInstance.objects.get(meal_identifier=self.meal_id, user=self.user).is_cooked,
        )

    def test_consistent_rows_are_left_alone(self):
        good_meal = scale_recipe_to_meal(self.curated, portions=2)
        good_id = f'{self.goal.id}:1:dinner:0'
        good_meal['meal_identifier'] = good_id
        good = Recipe.objects.create(
            meal_identifier=good_id, dietary_goal=self.goal,
            name=self.curated.name_cs, servings=2,
            nutritional_info=good_meal['nutritional_info'],
            ingredients=good_meal['ingredients'], instructions=['Uvař.'],
            curated_recipe_slug=self.curated.slug,
        )
        before = good.nutritional_info['calories']
        self._run('--apply')
        good.refresh_from_db()
        self.assertEqual(good.nutritional_info['calories'], before)
        self.assertEqual(good.servings, 2)

    def test_rows_with_no_curated_source_are_skipped(self):
        Recipe.objects.create(
            meal_identifier=f'{self.goal.id}:1:breakfast:0', dietary_goal=self.goal,
            name='LLM omeleta', servings=1, nutritional_info={'calories': 400},
            ingredients=[], instructions=['Usmaž.'], curated_recipe_slug='',
        )
        output = self._run('--apply')
        self.assertNotIn('LLM omeleta', output)

    def test_orphaned_slug_is_reported_not_crashed(self):
        Recipe.objects.create(
            meal_identifier=f'{self.goal.id}:1:snack:0', dietary_goal=self.goal,
            name='Zmizelý recept', servings=2, nutritional_info={'calories': 900},
            ingredients=[], instructions=['x'], curated_recipe_slug='neexistujici-slug',
        )
        output = self._run('--apply')
        self.assertIn('neexistujici-slug', output)
