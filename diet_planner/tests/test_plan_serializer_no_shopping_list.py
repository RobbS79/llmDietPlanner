"""The plan serializer must not expose any whole-plan shopping list or
plan-level pricing. Shopping/pricing live only at the per-recipe level now."""
from django.test import TestCase

from diet_planner.models import DietaryGoal, DietaryPlan
from diet_planner.serializers import DietaryPlanSerializer


class PlanSerializerOmitsShoppingList(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create(username="u1")
        self.goal = DietaryGoal.objects.create(
            user=user, prompt="x", num_days=3, country="CZ", currency="CZK",
        )
        self.plan = DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{"day_number": 1, "breakfast": {"name": "Eggs", "ingredients": []}}],
            currency="CZK",
        )

    def test_serializer_drops_whole_plan_fields(self):
        data = DietaryPlanSerializer(self.plan).data
        for gone in (
            "shopping_list", "pricing", "total_price", "pantry_price",
            "pantry_basics_on", "pantry_fridge_on",
        ):
            self.assertNotIn(gone, data, f"{gone} should no longer be serialized")

    def test_serializer_keeps_days(self):
        data = DietaryPlanSerializer(self.plan).data
        self.assertIn("days", data)
