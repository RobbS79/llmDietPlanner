"""The catalog-constrained task (the path prod actually uses when
CATALOG_CONSTRAINED_GENERATION is on) must fire the ``plan_generated`` CAPI
activation event exactly once when generation completes successfully.

Scaffolding (setUp, product fixtures, LLM mock shape, patch targets) is
mirrored from ``test_catalog_task_restrictions.py`` — that test already
drives ``process_dietary_goal_catalog_task`` to a successful COMPLETED
result via ``GeminiService.generate_catalog_constrained_plan`` mocked with a
minimal valid plan payload, and disables recipe grounding so the mock
payload doesn't need to satisfy the curated-recipe overlay.
"""
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal, PriceSourceType
from diet_planner.tests.factories import make_price


# The catalog task falls back to the legacy flow when fewer than 10 products
# remain after dietary-restriction filtering, so we need >= 10 products to
# survive (no restrictions here, so all of them survive).
_PRODUCTS = [
    ("kuřecí prsa", 139.90),
    ("hovězí maso", 199.90),
    ("šunka", 49.90),
    ("rýže basmati", 45.90),
    ("rajčata", 29.90),
    ("jogurt bílý", 18.90),
    ("vejce 10ks M", 64.90),
    ("špenát mražený", 29.90),
    ("olivový olej extra virgin", 89.90),
    ("mléko polotučné", 22.90),
    ("brambory", 19.90),
    ("cibule", 14.90),
    ("mrkev", 12.90),
    ("paprika", 39.90),
]


class PlanGeneratedEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plangenuser", password="test")
        for name, price in _PRODUCTS:
            make_price(
                store_code="LIDL_CZ",
                normalized_name=name,
                display_name=name.title(),
                price=price,
                source_type=PriceSourceType.STORE_REGULAR,
            )
        self.goal = DietaryGoal.objects.create(
            user=self.user,
            prompt="jídelníček",
            country="CZ",
            city="Prague",
            shop="LIDL_CZ",
            num_days=1,
            status=DietaryGoal.StatusChoices.PROCESSING,
        )

    @patch("diet_planner.tasks.track_plan_generated")
    def test_catalog_task_fires_plan_generated_on_success(self, mock_track):
        from diet_planner.llm_service import GeminiService
        from diet_planner.tasks import process_dietary_goal_catalog_task

        def _capture(self_llm, *, user_prompt, catalog_text, goal, **kw):
            return {
                "response": {"days": [{
                    "day_number": 1,
                    "lunch": {
                        "name": "Rýže",
                        "ingredients": [{"name": "rýže basmati", "quantity": 100, "unit": "g"}],
                        "instructions": ["uvařit"],
                    },
                }]},
                "input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                "cost_usd": 0.0, "model": "gemini-test",
            }

        with patch.object(
            GeminiService, "generate_catalog_constrained_plan", _capture
        ), patch(
            "diet_planner.services.recipe_retrieval.grounding_enabled",
            return_value=False,
        ):
            result = process_dietary_goal_catalog_task.apply(args=[self.goal.id]).get()

        self.assertEqual(result["status"], "success", result)
        mock_track.assert_called_once()
        self.assertEqual(mock_track.call_args.args[0], self.goal.user)
        self.assertEqual(mock_track.call_args.args[1], self.goal.id)
