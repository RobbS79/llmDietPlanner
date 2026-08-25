"""Estimating a recipe's energy from what is actually in it."""
from django.test import SimpleTestCase

from diet_planner.services.nutrition_density import estimate_recipe_kcal

CATEGORIES = {
    'rice-basmati': 'grains', 'olive-oil': 'oils', 'eggs': 'eggs',
    'carrots': 'vegetables', 'chicken-breast': 'meat',
}


class EstimateRecipeKcalTest(SimpleTestCase):
    def test_weights_each_ingredient_by_its_category_energy(self):
        estimate = estimate_recipe_kcal(
            [{'name': 'rýže', 'quantity': 200, 'unit': 'g', 'canonical': 'rice-basmati'},
             {'name': 'mrkev', 'quantity': 100, 'unit': 'g', 'canonical': 'carrots'}],
            categories=CATEGORIES,
        )

        # 200 g dry rice at 3.5 + 100 g carrot at 0.35
        self.assertAlmostEqual(estimate.kcal, 735.0, places=1)
        self.assertEqual(estimate.coverage, 1.0)

    def test_oil_dominates_despite_small_mass(self):
        estimate = estimate_recipe_kcal(
            [{'name': 'olivový olej', 'quantity': 3, 'unit': 'lžíce', 'canonical': 'olive-oil'}],
            categories=CATEGORIES,
        )

        self.assertAlmostEqual(estimate.kcal, 396.0, places=1)

    def test_uncategorised_mass_lowers_coverage_without_inventing_energy(self):
        estimate = estimate_recipe_kcal(
            [{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
             {'name': 'záhada', 'quantity': 100, 'unit': 'g', 'canonical': 'mystery'}],
            categories=CATEGORIES,
        )

        self.assertAlmostEqual(estimate.kcal, 350.0, places=1)
        self.assertAlmostEqual(estimate.coverage, 0.5, places=2)

    def test_count_units_resolve_through_piece_weights(self):
        estimate = estimate_recipe_kcal(
            [{'name': 'vejce', 'quantity': 4, 'unit': 'ks', 'canonical': 'eggs'}],
            categories=CATEGORIES,
            piece_weights={'eggs': 55.0},
        )

        # 220 g of egg at 1.4 kcal/g
        self.assertAlmostEqual(estimate.kcal, 308.0, places=1)

    def test_empty_recipe_has_no_estimate_and_no_coverage(self):
        estimate = estimate_recipe_kcal([], categories=CATEGORIES)

        self.assertEqual(estimate.kcal, 0.0)
        self.assertEqual(estimate.coverage, 0.0)
