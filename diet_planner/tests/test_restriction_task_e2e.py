"""End-to-end: an unsatisfiable dietary restriction fails the goal.

Runs the real process_dietary_goal_task against a database-backed DietaryGoal
with only the Gemini API mocked. Gemini keeps returning a meal whose
instructions mention "flour" (a gluten_free violation with no deterministic
swap), so the repair loop re-prompts until the budget is exhausted. The task
must mark the goal FAILED rather than ship a restriction-violating plan.
"""
import json
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal


def _violating_model(state):
    """genai.GenerativeModel stand-in that always returns a gluten violation.

    First call returns a full {"days": [...]} plan; every later call returns a
    single replacement meal (the regenerate_meal re-prompt) — all violating.
    """
    days_envelope = json.dumps({"days": [{
        "day_number": 1,
        "lunch": {
            "name": "Rýže s omáčkou",
            "ingredients": [{"name": "rýže", "quantity": 100, "unit": "g"}],
            "instructions": ["Mix with flour until smooth."],
        },
    }]})
    single_meal = json.dumps({
        "name": "Pořád s lepkem",
        "ingredients": [{"name": "rýže", "quantity": 100, "unit": "g"}],
        "instructions": ["Mix with flour until smooth."],
        "food_category": "lunch_main_dish",
    })

    class _Model:
        def __init__(self, model_name, system_instruction):
            pass

        def generate_content(self, prompt, *a, **kw):
            state["calls"] += 1
            resp = MagicMock()
            finish = MagicMock()
            finish.name = "STOP"
            resp.candidates = [MagicMock(finish_reason=finish)]
            resp.text = days_envelope if state["calls"] == 1 else single_meal
            resp.usage_metadata = MagicMock(
                prompt_token_count=1, candidates_token_count=1, total_token_count=2,
            )
            return resp

    return _Model


@pytest.mark.django_db
def test_unsatisfiable_restriction_fails_goal_without_retry(monkeypatch):
    user = User.objects.create(username="e2e_restrict")
    goal = DietaryGoal.objects.create(
        user=user,
        prompt="bezlepkový jídelníček",
        dietary_restrictions="gluten_free",
        country="CZ",
        city="Praha",
        num_days=1,
        status=DietaryGoal.StatusChoices.PROCESSING,
    )

    state = {"calls": 0}
    import diet_planner.llm_service as llm_mod
    monkeypatch.setattr(
        llm_mod.genai, "GenerativeModel", _violating_model(state)
    )

    from diet_planner.tasks import process_dietary_goal_task
    result = process_dietary_goal_task.apply(args=[goal.id]).get()

    # Task returns a terminal failure (not a retry).
    assert result["status"] == "failed"
    assert result["reason"] == "dietary_restrictions_unsatisfiable"

    goal.refresh_from_db()
    assert goal.status == DietaryGoal.StatusChoices.FAILED
    assert "restrictions" in (goal.error_message or "").lower()

    # Initial plan + 2 re-prompts (per-meal cap) before giving up.
    assert state["calls"] == 3
