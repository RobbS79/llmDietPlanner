"""Per-portion nutrition plausibility detector.

Calibrated against the 458-recipe published corpus on 2026-08-07 — see the
service docstring for the distribution these thresholds come from.
"""
from django.test import TestCase

from diet_planner.services.nutrition_plausibility import (
    atwater_kcal,
    check_nutrition_plausibility,
)


class AtwaterTest(TestCase):
    def test_sums_macros_with_atwater_factors(self):
        # 4 kcal/g protein and carbs, 9 kcal/g fat.
        self.assertAlmostEqual(atwater_kcal({'protein': 10, 'carbs': 20, 'fat': 5}), 165.0)

    def test_returns_none_without_any_macro(self):
        self.assertIsNone(atwater_kcal({'calories': 500}))
        self.assertIsNone(atwater_kcal({}))
        self.assertIsNone(atwater_kcal(None))

    def test_tolerates_string_and_czech_decimal_values(self):
        self.assertAlmostEqual(atwater_kcal({'protein': '10', 'fat': '2,5'}), 62.5)


class PortionFloorTest(TestCase):
    def test_a_healthy_main_passes(self):
        result = check_nutrition_plausibility(
            {'calories': 2400}, base_servings=4, dish_role='main')
        self.assertTrue(result.ok)
        self.assertEqual(result.per_portion_kcal, 600)
        self.assertEqual(result.reasons, [])

    def test_main_below_the_role_floor_is_flagged(self):
        # Prod: recke-kure-z-jednoho-plechu, 454 kcal over 6 servings = 76.
        result = check_nutrition_plausibility(
            {'calories': 454}, base_servings=6, dish_role='main')
        self.assertFalse(result.ok)
        self.assertTrue(any('below' in r for r in result.reasons))

    def test_sides_are_allowed_to_be_light(self):
        # A 70 kcal side is normal (corpus p50 for side = 72.5) and must not
        # be flagged by the floor that applies to mains.
        self.assertTrue(check_nutrition_plausibility(
            {'calories': 140}, base_servings=2, dish_role='side').ok)

    def test_unknown_role_uses_the_default_floor(self):
        self.assertFalse(check_nutrition_plausibility(
            {'calories': 100}, base_servings=2, dish_role=None).ok)

    def test_absurdly_high_per_portion_is_flagged(self):
        result = check_nutrition_plausibility(
            {'calories': 5000}, base_servings=1, dish_role='main')
        self.assertFalse(result.ok)
        self.assertTrue(any('above' in r for r in result.reasons))

    def test_missing_calories_is_not_evidence_of_a_problem(self):
        result = check_nutrition_plausibility({}, base_servings=4, dish_role='main')
        self.assertTrue(result.ok)
        self.assertIsNone(result.per_portion_kcal)

    def test_non_numeric_calories_is_ignored(self):
        self.assertTrue(check_nutrition_plausibility(
            {'calories': 'asi 400'}, base_servings=2, dish_role='main').ok)

    def test_zero_or_negative_servings_treated_as_one(self):
        result = check_nutrition_plausibility(
            {'calories': 600}, base_servings=0, dish_role='main')
        self.assertEqual(result.per_portion_kcal, 600)


class SuspectedBasisTest(TestCase):
    """The actionable signal: base_nutrition holding a PER-PORTION figure while
    the field contract says it covers base_servings."""

    def test_flags_per_portion_basis_when_undivided_value_is_plausible(self):
        # cuketove-lasagne: 362 kcal / 12 servings = 30. 362 is one portion.
        result = check_nutrition_plausibility(
            {'calories': 362}, base_servings=12, dish_role='main')
        self.assertFalse(result.ok)
        self.assertEqual(result.suspected_basis, 'per_portion')

    def test_no_basis_claim_when_the_undivided_value_is_also_implausible(self):
        # 60 kcal total is not a portion of anything either — a different bug.
        result = check_nutrition_plausibility(
            {'calories': 60}, base_servings=4, dish_role='main')
        self.assertFalse(result.ok)
        self.assertIsNone(result.suspected_basis)

    def test_single_serving_recipes_make_no_basis_claim(self):
        # With one serving the two bases are identical, so nothing is inferable.
        result = check_nutrition_plausibility(
            {'calories': 100}, base_servings=1, dish_role='main')
        self.assertIsNone(result.suspected_basis)

    def test_healthy_recipe_makes_no_basis_claim(self):
        result = check_nutrition_plausibility(
            {'calories': 2400}, base_servings=4, dish_role='main')
        self.assertIsNone(result.suspected_basis)


class AtwaterConsistencyTest(TestCase):
    def test_macros_disagreeing_with_calories_are_reported(self):
        # Claims 300 kcal but the macros add up to ~1200.
        result = check_nutrition_plausibility(
            {'calories': 300, 'protein': 50, 'carbs': 200, 'fat': 20},
            base_servings=1, dish_role='main')
        self.assertTrue(any('macros' in r for r in result.reasons))

    def test_consistent_macros_are_not_reported(self):
        # Prod smazena-ryze-s-vejcem: 360 stated, 352 from macros.
        result = check_nutrition_plausibility(
            {'calories': 360, 'protein': 9, 'carbs': 52, 'fat': 12},
            base_servings=1, dish_role='light')
        self.assertFalse(any('macros' in r for r in result.reasons))

    def test_missing_macros_produce_no_atwater_reason(self):
        result = check_nutrition_plausibility(
            {'calories': 600}, base_servings=1, dish_role='main')
        self.assertIsNone(result.atwater_kcal)
        self.assertFalse(any('macros' in r for r in result.reasons))


class AuditCommandTest(TestCase):
    """The command is read-only and must survive a corpus row it cannot judge."""

    def _run(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('audit_nutrition_plausibility', *args, stdout=out)
        return out.getvalue()

    def test_reports_flagged_recipes_with_the_basis_diagnosis(self):
        from diet_planner.tests.test_recipe_replace import make_recipe
        make_recipe(name_cs='Cuketové lasagne', slug='cuketove-lasagne',
                    dish_role='main', base_servings=12,
                    base_nutrition={'calories': 362})
        output = self._run()
        self.assertIn('cuketove-lasagne', output)
        self.assertIn('base_nutrition looks per-portion', output)
        self.assertIn('look like base_nutrition holds ONE portion', output)

    def test_healthy_corpus_flags_nothing(self):
        from diet_planner.tests.test_recipe_replace import make_recipe
        make_recipe(name_cs='Poctivý oběd', slug='poctivy-obed',
                    dish_role='main', base_servings=4,
                    base_nutrition={'calories': 2400})
        output = self._run()
        self.assertIn('Flagged 0', output)

    def test_recipes_without_stored_calories_are_not_scanned(self):
        from diet_planner.tests.test_recipe_replace import make_recipe
        make_recipe(name_cs='Bez hodnot', slug='bez-hodnot',
                    dish_role='main', base_servings=2, base_nutrition={})
        output = self._run()
        self.assertIn('Scanned 0 recipe(s)', output)

    def test_role_filter_narrows_the_scan(self):
        from diet_planner.tests.test_recipe_replace import make_recipe
        make_recipe(name_cs='Příloha', slug='priloha', dish_role='side',
                    base_servings=2, base_nutrition={'calories': 140})
        make_recipe(name_cs='Hlavní', slug='hlavni', dish_role='main',
                    base_servings=4, base_nutrition={'calories': 2400})
        output = self._run('--role', 'side')
        self.assertIn('Scanned 1 recipe(s)', output)
