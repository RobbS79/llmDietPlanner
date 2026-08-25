"""Deciding whether a recipe's base_nutrition really holds ONE portion.

Fixtures are real prod rows (2026-08-24) so the thresholds stay honest.
"""
from django.test import SimpleTestCase

from diet_planner.services.nutrition_basis_repair import plan_basis_repair

PIECE_WEIGHTS = {'eggs': 55.0, 'onion': 110.0}
CATEGORIES = {
    'lentils': 'legumes', 'stock': 'beverages', 'coconut-milk': 'canned',
    'onion': 'vegetables', 'eggs': 'eggs', 'feta': 'dairy',
    'oats': 'grains', 'olive-oil': 'oils',
}


def _plan(**kw):
    kw.setdefault('piece_weights', PIECE_WEIGHTS)
    kw.setdefault('categories', CATEGORIES)
    return plan_basis_repair(**kw)


class PlanBasisRepairTest(SimpleTestCase):
    def test_repairs_when_the_multiplied_total_matches_the_ingredients(self):
        # kari-cockova-polevka: 500 kcal claimed for 4 portions of a 2.2 kg
        # lentil soup whose ingredients carry roughly 2000.
        plan = _plan(
            base_nutrition={'calories': 500, 'protein': 17, 'carbs': 46, 'fat': 28},
            base_servings=4,
            dish_role='main',
            ingredients=[
                {'name': 'čočka', 'quantity': 400, 'unit': 'g', 'canonical': 'lentils'},
                {'name': 'kokosové mléko', 'quantity': 800, 'unit': 'ml', 'canonical': 'coconut-milk'},
                {'name': 'vývar', 'quantity': 1000, 'unit': 'ml', 'canonical': 'stock'},
                {'name': 'cibule', 'quantity': 1, 'unit': 'ks', 'canonical': 'onion'},
            ],
        )

        self.assertEqual(plan.action, 'repair')
        self.assertEqual(plan.proposed,
                         {'calories': 2000, 'protein': 68, 'carbs': 184, 'fat': 112})

    def test_leaves_a_plausible_recipe_alone(self):
        plan = _plan(
            base_nutrition={'calories': 2000, 'protein': 68, 'carbs': 184, 'fat': 112},
            base_servings=4,
            dish_role='main',
            ingredients=[{'name': 'čočka', 'quantity': 400, 'unit': 'g', 'canonical': 'lentils'}],
        )

        self.assertEqual(plan.action, 'skip')
        self.assertEqual(plan.reason, 'not_a_basis_candidate')
        self.assertIsNone(plan.proposed)

    def test_refuses_to_multiply_when_the_stored_total_already_matches_the_food(self):
        # varena-vejce-natvrdo: 4 hard-boiled eggs really are ~300 kcal in
        # total. `base_servings` counts eggs, so one "portion" is legitimately
        # under the role floor and x4 would invent 900 kcal of nothing --
        # 1200 kcal is 3.9x what 220 g of egg can carry.
        plan = _plan(
            base_nutrition={'calories': 300, 'protein': 25, 'carbs': 2, 'fat': 20},
            base_servings=4,
            dish_role='light',
            ingredients=[{'name': 'vejce', 'quantity': 4, 'unit': 'ks', 'canonical': 'eggs'}],
        )

        self.assertEqual(plan.action, 'skip')
        self.assertEqual(plan.reason, 'corrected_outside_ingredient_energy')
        self.assertIsNone(plan.proposed)

    def test_refuses_a_multiply_that_would_outweigh_the_food_in_macros(self):
        # stredomorske-vajecne-muffiny: x12 implies 1512 g of protein, carbs
        # and fat from 860 g of egg and feta -- caught by the physical bound
        # before any category estimate is needed.
        plan = _plan(
            base_nutrition={'calories': 804, 'protein': 55.2, 'carbs': 14.4, 'fat': 56.4},
            base_servings=12,
            dish_role='light',
            ingredients=[
                {'name': 'vejce', 'quantity': 12, 'unit': 'ks', 'canonical': 'eggs'},
                {'name': 'feta', 'quantity': 200, 'unit': 'g', 'canonical': 'feta'},
            ],
        )

        self.assertEqual(plan.action, 'skip')
        self.assertEqual(plan.reason, 'macros_exceed_mass')

    def test_keeps_the_stored_total_when_it_fits_the_food_better_than_the_multiple(self):
        # Two servings of boiled eggs: x2 stays inside the band, but 280 kcal
        # is the reading the 220 g of egg actually supports.
        plan = _plan(
            base_nutrition={'calories': 280, 'protein': 20, 'carbs': 2, 'fat': 18},
            base_servings=2,
            dish_role='light',
            ingredients=[{'name': 'vejce', 'quantity': 4, 'unit': 'ks', 'canonical': 'eggs'}],
        )

        self.assertEqual(plan.action, 'skip')
        self.assertEqual(plan.reason, 'stored_matches_ingredient_energy')

    def test_repairs_a_dense_dry_batch_a_fixed_ceiling_would_have_refused(self):
        # domaci-granola: 4.6 kcal/g corrected is right for granola, and only
        # an ingredient-aware estimate can say so.
        plan = _plan(
            base_nutrition={'calories': 525, 'protein': 11, 'carbs': 57, 'fat': 31},
            base_servings=4,
            dish_role='light',
            ingredients=[
                {'name': 'ovesné vločky', 'quantity': 350, 'unit': 'g', 'canonical': 'oats'},
                {'name': 'olej', 'quantity': 60, 'unit': 'g', 'canonical': 'olive-oil'},
            ],
        )

        self.assertEqual(plan.action, 'repair')
        self.assertEqual(plan.proposed['calories'], 2100)

    def test_refuses_a_multiply_that_would_invent_more_macros_than_food(self):
        plan = _plan(
            base_nutrition={'calories': 500, 'protein': 40, 'carbs': 60, 'fat': 25},
            base_servings=4,
            dish_role='main',
            ingredients=[{'name': 'směs', 'quantity': 400, 'unit': 'g'}],
        )

        self.assertEqual(plan.action, 'skip')
        self.assertEqual(plan.reason, 'macros_exceed_mass')

    def test_will_not_guess_when_the_ingredients_are_mostly_unmeasured(self):
        plan = _plan(
            base_nutrition={'calories': 484, 'protein': 24, 'carbs': 58, 'fat': 15},
            base_servings=4,
            dish_role='main',
            ingredients=[
                {'name': 'brambory', 'quantity': 4, 'unit': 'ks', 'canonical': 'potatoes'},
                {'name': 'majoránka', 'quantity': 1, 'unit': 'dle chuti'},
                {'name': 'sůl', 'quantity': None, 'unit': 'g'},
                {'name': 'olej', 'quantity': 30, 'unit': 'g', 'canonical': 'olive-oil'},
            ],
            piece_weights={},
        )

        self.assertEqual(plan.action, 'skip')
        self.assertEqual(plan.reason, 'insufficient_mass_evidence')

    def test_will_not_guess_when_the_mass_has_no_known_categories(self):
        plan = _plan(
            base_nutrition={'calories': 400, 'protein': 12, 'carbs': 40, 'fat': 18},
            base_servings=4,
            dish_role='main',
            ingredients=[
                {'name': 'záhadná směs', 'quantity': 1200, 'unit': 'g', 'canonical': 'mystery'},
                {'name': 'druhá záhada', 'quantity': 600, 'unit': 'g', 'canonical': 'mystery2'},
            ],
        )

        self.assertEqual(plan.action, 'skip')
        self.assertEqual(plan.reason, 'insufficient_ingredient_data')

    def test_scales_every_numeric_nutrient_and_preserves_the_rest(self):
        plan = _plan(
            base_nutrition={'calories': 500, 'protein': 17, 'carbs': 46, 'fat': 28,
                            'fiber': 9, 'source': 'usda'},
            base_servings=4,
            dish_role='main',
            ingredients=[
                {'name': 'čočka', 'quantity': 400, 'unit': 'g', 'canonical': 'lentils'},
                {'name': 'vývar', 'quantity': 1800, 'unit': 'ml', 'canonical': 'stock'},
            ],
        )

        self.assertEqual(plan.action, 'repair')
        self.assertEqual(plan.proposed['fiber'], 36)
        self.assertEqual(plan.proposed['source'], 'usda')

    def test_reports_the_evidence_behind_the_decision(self):
        plan = _plan(
            base_nutrition={'calories': 500, 'protein': 17, 'carbs': 46, 'fat': 28},
            base_servings=4,
            dish_role='main',
            ingredients=[
                {'name': 'čočka', 'quantity': 400, 'unit': 'g', 'canonical': 'lentils'},
                {'name': 'vývar', 'quantity': 1800, 'unit': 'ml', 'canonical': 'stock'},
            ],
        )

        self.assertEqual(plan.evidence['mass_g'], 2200.0)
        self.assertEqual(plan.evidence['coverage'], 1.0)
        self.assertEqual(plan.evidence['estimated_kcal'], 1340.0)
        self.assertEqual(plan.evidence['corrected_kcal'], 2000.0)
