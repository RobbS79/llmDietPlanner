"""Validator must not raise shopping-list errors when given no list.

Shopping/pricing live per-recipe now, so a plan is generated with an empty
whole-plan shopping list. The validator must treat that as normal, not flag it.
"""
from django.test import SimpleTestCase
from diet_planner.services.validation import MealPlanValidator


def _full_day(n):
    meal = lambda name: {"name": name, "ingredients": [{"name": "eggs", "quantity": 2, "unit": "ks"}]}
    return {
        "day_number": n,
        "breakfast": meal("Eggs"),
        "lunch": meal("Chicken"),
        "dinner": meal("Salad"),
    }


class ValidatorNoShopping(SimpleTestCase):
    def test_empty_shopping_list_no_price_errors(self):
        plan = {"days": [_full_day(1)]}
        result = MealPlanValidator().validate(plan, [], {"num_days": 1, "language": "cs"})
        joined = " ".join(result.errors).lower()
        self.assertNotIn("price", joined)
        self.assertNotIn("items without prices", joined)
        self.assertNotIn("shopping list", joined)
