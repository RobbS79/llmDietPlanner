"""The catalog-constrained task must pre-filter the product catalog by the
user's dietary restrictions BEFORE handing it to the LLM.

Regression: ``process_dietary_goal_catalog_task`` called
``build_catalog_for_prompt(goal)`` with no ``exclusions`` argument. After the
Task-5 refactor, ``build_catalog_for_prompt`` only filters when it receives a
resolved restriction set — so the catalog text shown to the LLM still listed
forbidden products (e.g. chicken for a vegetarian). The system-prompt block and
post-generation repair loop still caught violations, but the "constrain the LLM
to allowed products only" guarantee was silently bypassed (extra repair churn,
wasted tokens).

This test pins the wiring: a vegetarian goal must produce a catalog_text that
excludes meat.
"""
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth.models import User

from diet_planner.models import DietaryGoal, PriceSourceType
from diet_planner.tests.factories import make_price


# The catalog task falls back to the legacy flow when fewer than 10 products
# remain, so we need >= 10 vegetarian-safe items to survive the meat filter.
# 3 meats + 13 veg-safe = 16 products -> 13 after filtering.
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
    ("okurka", 17.90),
    ("jablka", 24.90),
]


class CatalogTaskDietaryFilterTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("cattask", password="test")
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
            prompt="vegetariánský jídelníček",
            dietary_restrictions="vegetarian",
            country="CZ",
            city="Prague",
            shop="LIDL_CZ",
            num_days=1,
            status=DietaryGoal.StatusChoices.PROCESSING,
        )

    def test_catalog_text_excludes_meat_for_vegetarian(self):
        captured = {}

        def _capture(self_llm, *, user_prompt, catalog_text, goal, **kw):
            captured["catalog_text"] = catalog_text
            return {
                "response": {"days": []},
                "input_tokens": 1, "output_tokens": 1, "total_tokens": 2,
                "cost_usd": 0.0, "model": "gemini-test",
            }

        from diet_planner.llm_service import GeminiService
        from diet_planner.tasks import process_dietary_goal_catalog_task

        with patch.object(
            GeminiService, "generate_catalog_constrained_plan", _capture
        ), patch(
            "diet_planner.services.recipe_retrieval.grounding_enabled",
            return_value=False,
        ):
            result = process_dietary_goal_catalog_task.apply(args=[self.goal.id]).get()

        assert result["status"] == "success", result
        text = captured["catalog_text"].lower()
        # Meat must be filtered out of the catalog the LLM sees.
        assert "kuřecí" not in text, text
        assert "hovězí" not in text
        assert "šunka" not in text
        # Vegetarian-safe staples must remain.
        assert "rýže" in text
        assert "rajčata" in text
