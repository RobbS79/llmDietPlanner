"""Regression test for the legacy combined meal-plan + shopping-list path.

Bug (plan-#110 follow-up): ``generate_complete_plan_with_shopping_list`` passed
the raw ``days`` structure straight into ``generate_shopping_list_with_prices``,
which Task 9 rewrote to expect a FLAT aggregated list of
``{'ingredient', 'quantity', 'unit'}`` items. The pricing call therefore saw a
list of day dicts (``it.get('ingredient')`` was always empty), producing a
shopping list with zero parity to the recipes.

The fix: aggregate ingredients deterministically before pricing, so every recipe
ingredient appears on the shopping list (the aggregated list is the source of
truth).
"""
from unittest.mock import MagicMock

from diet_planner.llm_service import GeminiService


def _meal(name, ingredients):
    return {"name": name, "ingredients": ingredients, "instructions": ["cook"]}


def test_legacy_path_prices_aggregated_ingredients_not_raw_days():
    # Bypass the API-key-requiring __init__; we only exercise pure orchestration.
    svc = GeminiService.__new__(GeminiService)
    svc.default_model = "gemini-test"

    days = [
        {
            "day_number": 1,
            "breakfast": _meal("Oats", [{"name": "ovesné vločky", "quantity": 50, "unit": "g"}]),
            "lunch": _meal("Rice bowl", [{"name": "rýže", "quantity": 100, "unit": "g"}]),
            "dinner": _meal("Chicken", [{"name": "kuřecí prsa", "quantity": 150, "unit": "g"}]),
            "small_meals": [],
            "snacks": [],
        },
    ]

    svc.generate_meal_plan_only = MagicMock(return_value={
        "response": {"days": days},
        "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0,
    })

    captured = {}

    def _price(aggregated_items, shop_url, goal, model=None):
        captured["items"] = aggregated_items
        return {
            "response": {
                "shopping_list": [
                    {
                        "ingredient": it["ingredient"],
                        "quantity": it["quantity"],
                        "unit": it["unit"],
                        "price": 10,
                        "price_total": 10,
                        "currency": "CZK",
                    }
                    for it in aggregated_items
                ],
                "total_cost": 30,
            },
            "input_tokens": 1, "output_tokens": 1, "cost_usd": 0.0,
        }

    svc.generate_shopping_list_with_prices = MagicMock(side_effect=_price)

    result = svc.generate_complete_plan_with_shopping_list(
        user_prompt="x", shop_url="https://shop.example", goal=MagicMock(),
    )

    # The pricing call must receive a FLAT aggregated list — each entry a dict
    # with a non-empty 'ingredient' name — not the raw day dicts.
    items = captured["items"]
    assert all(isinstance(it, dict) and it.get("ingredient") for it in items), items
    names = {it["ingredient"].lower() for it in items}
    assert {"ovesné vločky", "rýže", "kuřecí prsa"} <= names

    # Every recipe ingredient must appear on the resulting shopping list.
    shop_names = {row["ingredient"].lower() for row in result["response"]["shopping_list"]}
    assert {"ovesné vločky", "rýže", "kuřecí prsa"} <= shop_names
