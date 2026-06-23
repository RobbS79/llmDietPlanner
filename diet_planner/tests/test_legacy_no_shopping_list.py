"""Legacy generation path must call meal-plan-only generation and store no
whole-plan shopping list."""
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from diet_planner.models import DietaryGoal, DietaryPlan

FAKE_DAYS = [
    {"day_number": 1,
     "breakfast": {"name": "Eggs", "ingredients": [{"name": "eggs", "quantity": 2, "unit": "ks"}]}},
]


class LegacyPathOmitsShoppingList(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username="leguser")
        self.goal = DietaryGoal.objects.create(
            user=user, prompt="x", num_days=1, country="CZ", currency="CZK",
        )

    @patch("diet_planner.tasks.transform_days_to_new_format", side_effect=lambda d, g: d)
    @patch("diet_planner.tasks._assert_plan_has_content")
    @patch("diet_planner.services.recipe_retrieval.grounding_enabled", return_value=False)
    @patch("diet_planner.tasks.GeminiService")
    def test_meal_plan_only_and_no_shopping_list(self, m_gem, *_):
        inst = m_gem.return_value
        inst.generate_meal_plan_only.return_value = {
            "response": {"days": FAKE_DAYS},
            "model": "x", "input_tokens": 1, "output_tokens": 1,
            "total_tokens": 2, "cost_usd": 0.0,
        }
        from diet_planner.tasks import process_dietary_goal_task
        # Bound Celery task — invoke underlying function via .run().
        process_dietary_goal_task.run(self.goal.id)

        inst.generate_meal_plan_only.assert_called_once()
        plan = DietaryPlan.objects.get(dietary_goal=self.goal)
        self.assertEqual(plan.days, FAKE_DAYS)
        self.assertIn(getattr(plan, "shopping_list", []), ([], None))
