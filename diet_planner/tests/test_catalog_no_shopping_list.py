"""The catalog-constrained generation path must not build or store a
whole-plan shopping list anymore."""
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model

from diet_planner.models import DietaryGoal, DietaryPlan


FAKE_DAYS = [
    {"day_number": 1,
     "breakfast": {"name": "Eggs", "ingredients": [{"name": "eggs", "quantity": 2, "unit": "ks"}]}},
]


class CatalogPathOmitsShoppingList(TestCase):
    def setUp(self):
        user = get_user_model().objects.create(username="catuser")
        self.goal = DietaryGoal.objects.create(
            user=user, prompt="x", num_days=1, country="CZ", currency="CZK",
        )

    @patch("diet_planner.tasks.transform_days_to_new_format", side_effect=lambda d, g: d)
    @patch("diet_planner.tasks._assert_plan_has_content")
    @patch("diet_planner.services.recipe_retrieval.grounding_enabled", return_value=False)
    @patch("diet_planner.tasks.GeminiService")
    @patch("diet_planner.services.catalog.CatalogService")
    def test_no_shopping_list_stored(self, m_catalog_cls, m_gem, *_):
        cat = m_catalog_cls.return_value
        cat.build_catalog_for_prompt.return_value = {"total_products": 50, "pantry_staples": []}
        cat.build_compact_prompt_text.return_value = "catalog text"
        inst = m_gem.return_value
        inst.generate_catalog_constrained_plan.return_value = {
            "response": {"days": FAKE_DAYS},
            "model": "x", "input_tokens": 1, "output_tokens": 1,
            "total_tokens": 2, "cost_usd": 0.0,
        }
        from diet_planner.tasks import process_dietary_goal_catalog_task
        # Bound Celery task — invoke underlying function via .run().
        process_dietary_goal_catalog_task.run(self.goal.id)

        plan = DietaryPlan.objects.get(dietary_goal=self.goal)
        self.assertEqual(plan.days, FAKE_DAYS)
        self.assertIn(getattr(plan, "shopping_list", []), ([], None))
