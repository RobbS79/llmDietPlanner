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
        self.assertEqual(n.unconverted, [{'name': 'mystery', 'canonical': 'mystery', 'unit': 'g', 'reason': 'no_nutrition'}])

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
