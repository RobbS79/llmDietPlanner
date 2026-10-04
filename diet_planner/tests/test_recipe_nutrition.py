"""Nutrition is arithmetic: grams × nutrients per 100 g, summed over the recipe."""
from django.test import SimpleTestCase

from diet_planner.services.nutrition_lookups import NutrientRow
from diet_planner.services.recipe_nutrition import (
    compute_recipe_nutrition, computed_base_nutrition,
)

TABLE = {
    'chicken-breast': NutrientRow(165, 31, 0, 3.6, None, None, {}),
    'rice-basmati': NutrientRow(360, 7, 79, 0.6, None, None, {}),
    'olive-oil': NutrientRow(884, 0, 0, 100, 0.92, None, {}),
    'onion': NutrientRow(40, 1.1, 9.3, 0.1, None, 110, {}),
    'salt': NutrientRow(0, 0, 0, 0, None, None, {}),
}
RECIPE = [
    {'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g', 'canonical': 'chicken-breast'},
    {'name': 'rýže', 'quantity': 200, 'unit': 'g', 'canonical': 'rice-basmati'},
    {'name': 'olivový olej', 'quantity': 1, 'unit': 'lžíce', 'canonical': 'olive-oil'},
    {'name': 'cibule', 'quantity': 1, 'unit': 'ks', 'canonical': 'onion'},
    {'name': 'sůl', 'quantity': None, 'unit': None, 'canonical': 'salt'},
]


class ComputeTest(SimpleTestCase):
    def test_hand_checked_totals(self):
        n = compute_recipe_nutrition(RECIPE, TABLE)
        # 400 g chicken 660 kcal + 200 g rice 720 + 13.8 g oil 122.0 + 110 g onion 44 + salt 0
        self.assertAlmostEqual(n.calories, 660 + 720 + 13.8 * 8.84 + 44, places=1)
        self.assertAlmostEqual(n.protein, 124 + 14 + 0 + 1.21, places=2)
        self.assertAlmostEqual(n.fat, 14.4 + 1.2 + 13.8 + 0.11, places=2)
        self.assertTrue(n.complete)
        self.assertEqual((n.lines_total, n.lines_converted), (5, 5))
        self.assertEqual(n.unconverted, [])

    def test_missing_nutrients_block(self):
        n = compute_recipe_nutrition(RECIPE + [{'name': 'mystery', 'quantity': 50, 'unit': 'g', 'canonical': 'mystery'}], TABLE)
        self.assertFalse(n.complete)
        self.assertEqual(n.unconverted, [{'name': 'mystery', 'canonical': 'mystery', 'unit': 'g', 'reason': 'no_nutrition', 'optional': False}])

    def test_unresolved_canonical_blocks(self):
        n = compute_recipe_nutrition([{'name': 'něco', 'quantity': 50, 'unit': 'g'}], TABLE)
        self.assertEqual(n.unconverted[0]['reason'], 'no_canonical')
        self.assertFalse(n.complete)

    def test_volume_without_density_blocks(self):
        n = compute_recipe_nutrition([{'name': 'rýže', 'quantity': 1, 'unit': 'hrnek', 'canonical': 'rice-basmati'}], TABLE)
        self.assertEqual(n.unconverted[0]['reason'], 'no_density')

    def test_optional_lines_never_block_but_count_when_they_convert(self):
        n = compute_recipe_nutrition([
            {'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
            {'name': 'petržel', 'quantity': 1, 'unit': 'svazek', 'canonical': 'parsley', 'optional': True},
            {'name': 'olej', 'quantity': 1, 'unit': 'lžička', 'canonical': 'olive-oil', 'optional': True},
        ], TABLE)
        self.assertTrue(n.complete)
        self.assertAlmostEqual(n.calories, 360 + 4.6 * 8.84, places=1)
        self.assertEqual(n.unconverted[0]['name'], 'petržel')

    def test_to_taste_line_with_unresolved_canonical_does_not_block(self):
        n = compute_recipe_nutrition([{'name': 'pepř', 'quantity': None, 'unit': None}], TABLE)
        self.assertTrue(n.complete)
        self.assertEqual(n.lines_converted, 1)

    def test_computed_base_nutrition_shape(self):
        b = computed_base_nutrition(compute_recipe_nutrition(RECIPE, TABLE))
        self.assertEqual(set(b), {'calories', 'protein', 'carbs', 'fat', 'source', 'computed_at'})
        self.assertIsInstance(b['calories'], int)
        self.assertEqual(b['source'], 'computed')
        self.assertEqual(b['protein'], round(139.21, 1))

    def test_bad_quantity_is_reported_and_incomplete(self):
        n = compute_recipe_nutrition([{'name': 'rýže', 'canonical': 'rice-basmati', 'quantity': '1/2', 'unit': 'kg'}], TABLE)
        self.assertEqual(n.unconverted[0]['reason'], 'bad_quantity')
        self.assertFalse(n.complete)


class FryingOilTest(SimpleTestCase):
    T = dict(TABLE, **{'sunflower-oil': NutrientRow(884, 0, 0, 100, 0.92, None, {}),
                       'butter': NutrientRow(717, 0.9, 0.1, 81, 0.911, None, {})})

    def _kcal(self, line):
        n = compute_recipe_nutrition([line], self.T)
        return n, n.calories

    def test_deep_fry_oil_counts_quarter(self):
        n, kcal = self._kcal({'name': 'olej na smažení', 'quantity': 200, 'unit': 'ml',
                              'canonical': 'sunflower-oil'})
        self.assertAlmostEqual(kcal, 200 * 0.92 * 0.25 * 8.84, places=1)
        self.assertEqual(n.absorbed_lines, 1)
        self.assertEqual(computed_base_nutrition(n)['frying_oil_factor'], 0.25)

    def test_shallow_fry_counts_full(self):
        n, kcal = self._kcal({'name': 'Olej na smažení', 'quantity': 2, 'unit': 'lžíce',
                              'canonical': 'sunflower-oil'})
        self.assertAlmostEqual(kcal, 27.6 * 8.84, places=1)
        self.assertEqual(n.absorbed_lines, 0)
        self.assertNotIn('frying_oil_factor', computed_base_nutrition(n))

    def test_butter_without_marker_full(self):
        n, kcal = self._kcal({'name': 'máslo', 'quantity': 200, 'unit': 'g', 'canonical': 'butter'})
        self.assertAlmostEqual(kcal, 200 * 7.17, places=1)
        self.assertEqual(n.absorbed_lines, 0)

    def test_non_fat_with_marker_full(self):
        n, kcal = self._kcal({'name': 'rýže na smažení', 'quantity': 200, 'unit': 'g',
                              'canonical': 'rice-basmati'})
        self.assertAlmostEqual(kcal, 720, places=1)
        self.assertEqual(n.absorbed_lines, 0)
