"""The pool generation task (``generate_meal_pool_task``, the path every
caller now dispatches) must fire the ``plan_generated`` CAPI activation event
exactly once when generation completes successfully — and never when it fails.

``build_meal_pool`` is patched so the test exercises only the task's
persistence + event wiring, not corpus selection or Gemini.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal
from diet_planner.services.meal_pool import PoolResult
from diet_planner.tasks import generate_meal_pool_task


class PlanGeneratedEventTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("plangenuser", password="test")
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt="jídelníček", country="CZ", currency="CZK",
            language_code="cs", dinners=1,
        )

    def _result(self):
        return PoolResult(
            meals=[{
                "slot": "dinner", "index": 0, "name": "Rýže",
                "meal_identifier": f"{self.goal.id}:dinner:0",
                "ingredients": [{"name": "rýže basmati", "quantity": 100, "unit": "g"}],
                "source": "curated",
            }],
            grounding_debug={"facets": {}, "coverage": {"filled": 1, "total": 1}, "gaps": [],
                             "shortfall": {}, "counts": {"dinner": 1}},
            llm_usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                       "cost_usd": 0.0, "model": None},
        )

    @patch("diet_planner.tasks.track_plan_generated")
    def test_pool_task_fires_plan_generated_on_success(self, mock_track):
        with patch("diet_planner.tasks.build_meal_pool", return_value=self._result()):
            result = generate_meal_pool_task.apply(args=[self.goal.id]).get()

        self.assertEqual(result["status"], "success", result)
        mock_track.assert_called_once()
        self.assertEqual(mock_track.call_args.args[0], self.goal.user)
        self.assertEqual(mock_track.call_args.args[1], self.goal.id)

    @patch("diet_planner.tasks.track_plan_generated")
    def test_pool_task_does_not_fire_on_failure(self, mock_track):
        with patch("diet_planner.tasks.build_meal_pool", side_effect=ValueError("empty pool")):
            try:
                generate_meal_pool_task.apply(args=[self.goal.id], throw=True)
            except Exception:
                pass
        mock_track.assert_not_called()
