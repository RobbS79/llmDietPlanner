"""A degenerate LLM response (truncated/garbage -> zero days or no ingredients)
must NOT be shipped to a user as a COMPLETED plan. The task should fail the
goal instead (REFUND_ELIGIBLE when payment is pending).
"""
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal, DietaryPlan


# --------------------------------------------------------------------------- #
# Unit: the guard itself
# --------------------------------------------------------------------------- #
class _Goal:
    id = 1


def test_guard_rejects_zero_days():
    from diet_planner.tasks import _assert_plan_has_content
    with pytest.raises(ValueError):
        _assert_plan_has_content([], _Goal())


def test_guard_rejects_days_without_ingredients():
    from diet_planner.tasks import _assert_plan_has_content
    days = [{"day_number": 1, "lunch": {"name": "Nic", "ingredients": []}}]
    with pytest.raises(ValueError):
        _assert_plan_has_content(days, _Goal())


def test_guard_accepts_plan_with_ingredients():
    from diet_planner.tasks import _assert_plan_has_content
    days = [{
        "day_number": 1,
        "lunch": {"name": "Rýže", "ingredients": [{"name": "rýže", "quantity": 100, "unit": "g"}]},
    }]
    # Should not raise.
    _assert_plan_has_content(days, _Goal())


# --------------------------------------------------------------------------- #
# Integration: the catalog task must fail (not complete) on an empty plan
# --------------------------------------------------------------------------- #
class CatalogTaskEmptyPlanTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("emptyplan", password="test")
        self.goal = DietaryGoal.objects.create(
            user=self.user,
            prompt="jídelníček",
            country="CZ",
            city="Prague",
            shop="LIDL_CZ",
            num_days=1,
            status=DietaryGoal.StatusChoices.PROCESSING,
        )

    def test_empty_days_fails_goal_and_ships_no_plan(self):
        from diet_planner.llm_service import GeminiService
        from diet_planner.services.catalog import CatalogService
        from diet_planner.tasks import process_dietary_goal_catalog_task

        fake_catalog = {
            "products_by_category": {},
            "total_products": 20,  # above the small-catalog fallback threshold
            "pantry_staples": [],
            "store_name": "Lidl",
            "catalog_limited": False,
        }

        def _empty(self_llm, *, user_prompt, catalog_text, goal, **kw):
            return {
                "response": {"days": []},  # degenerate
                "input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                "cost_usd": 0.0, "model": "gemini-test",
            }

        with patch.object(CatalogService, "build_catalog_for_prompt", return_value=fake_catalog), \
             patch.object(CatalogService, "build_compact_prompt_text", return_value=""), \
             patch.object(GeminiService, "generate_catalog_constrained_plan", _empty), \
             patch("diet_planner.services.recipe_retrieval.grounding_enabled", return_value=False):
            # The guard raises; the task's generic handler marks the goal FAILED
            # and then retries (max_retries=3). What matters is the invariant
            # below: the goal is FAILED and NO plan was shipped.
            with pytest.raises(Exception):
                process_dietary_goal_catalog_task.apply(args=[self.goal.id]).get()

        self.goal.refresh_from_db()
        assert self.goal.status == DietaryGoal.StatusChoices.FAILED, self.goal.status
        assert not DietaryPlan.objects.filter(dietary_goal=self.goal).exists()
