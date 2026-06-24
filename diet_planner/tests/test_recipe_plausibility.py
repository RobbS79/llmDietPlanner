"""Tests for the pure portion-plausibility detector."""
from django.test import SimpleTestCase

from diet_planner.services.recipe_plausibility import (
    SINGLE_CAP_G,
    TOTAL_CEILING_G,
    check_portion_plausibility,
)


class CheckPortionPlausibilityTest(SimpleTestCase):
    def test_normal_dish_is_ok(self):
        ings = [
            {"name": "kuřecí prsa", "quantity": 600, "unit": "g"},   # 150 g/portion
            {"name": "rýže", "quantity": 320, "unit": "g"},          # 80 g/portion
            {"name": "sůl", "quantity": None, "unit": None},
        ]
        r = check_portion_plausibility(ings, base_servings=4)
        self.assertTrue(r.ok)
        self.assertEqual(r.reasons, [])
        self.assertEqual(r.per_portion_total_g, 230.0)

    def test_single_ingredient_over_cap_is_flagged(self):
        ings = [{"name": "kuřecí prsa", "quantity": 680, "unit": "g"}]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertFalse(r.ok)
        self.assertEqual(len(r.offenders), 1)
        self.assertEqual(r.offenders[0]["name"], "kuřecí prsa")
        self.assertTrue(any("kuřecí prsa" in reason for reason in r.reasons))

    def test_inflated_dish_trips_total_ceiling(self):
        # Six 300 g rows at base_servings=1 -> 1800 g/portion total, but no
        # single row exceeds the single cap. Total ceiling must catch it.
        ings = [{"name": f"i{n}", "quantity": 300, "unit": "g"} for n in range(6)]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertFalse(r.ok)
        self.assertEqual(r.offenders, [])
        self.assertTrue(any("total" in reason for reason in r.reasons))
        self.assertGreater(r.per_portion_total_g, TOTAL_CEILING_G)

    def test_ml_treated_as_grams(self):
        ings = [{"name": "vývar", "quantity": 500, "unit": "ml"}]  # 500 g/portion, under caps
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_total_g, 500.0)

    def test_pieces_and_to_taste_ignored(self):
        ings = [
            {"name": "vejce", "quantity": 12, "unit": "ks"},
            {"name": "pepř", "quantity": "dle chuti", "unit": None},
        ]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_total_g, 0.0)

    def test_czech_decimal_comma_quantity_parsed(self):
        ings = [{"name": "máslo", "quantity": "1,5", "unit": "g"}]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_total_g, 1.5)

    def test_zero_base_servings_treated_as_one(self):
        ings = [{"name": "kuře", "quantity": 680, "unit": "g"}]
        r = check_portion_plausibility(ings, base_servings=0)
        self.assertFalse(r.ok)
        self.assertEqual(r.per_portion_total_g, 680.0)

    def test_no_weighable_rows_is_ok(self):
        r = check_portion_plausibility([], base_servings=4)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_max_single_g, 0.0)

    def test_thresholds_are_numbers(self):
        self.assertIsInstance(SINGLE_CAP_G, float)
        self.assertIsInstance(TOTAL_CEILING_G, float)
