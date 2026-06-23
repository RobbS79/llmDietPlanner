"""After ripping out whole-plan code, the per-recipe pricing/deals engine and
the shared price-book helpers must still import and run."""
from django.test import TestCase


class PerRecipeEngineIntact(TestCase):
    def test_shared_helpers_import(self):
        from diet_planner.services.estimate_pricer import _FX_FROM_CZK, _load_book  # noqa
        from diet_planner.services.shopping_list_pricing import (  # noqa
            classify_pantry_level, item_is_excluded,
        )
        from diet_planner.services.recipe_pricing import price_recipe  # noqa
        from diet_planner.services.recipe_deals import recipe_deals  # noqa
        self.assertTrue(callable(_load_book))

    def test_price_recipe_runs(self):
        from diet_planner.services.recipe_pricing import price_recipe
        # Inject a deterministic book so the test does not depend on book contents.
        book = {"allspice": {"name_cs": "x", "unit": "g", "price_per_unit": 1.0, "pack": 15.0}}
        r = price_recipe(
            [{"name": "allspice", "quantity": 10, "unit": "g", "canonical": "allspice"}],
            servings=1, currency="CZK", book=book,
        )
        self.assertIsNotNone(r)

    def test_whole_plan_symbols_gone(self):
        import diet_planner.tasks as t
        import diet_planner.llm_service as l
        for sym in ("aggregate_ingredients_from_meals", "validate_shopping_item",
                    "calculate_package_aware_price", "convert_requirement_to_purchasable_units"):
            self.assertFalse(hasattr(t, sym), f"{sym} should be removed from tasks")
        for sym in ("generate_complete_plan_with_shopping_list", "generate_shopping_list_with_prices"):
            self.assertFalse(hasattr(getattr(l, "GeminiService", object), sym),
                             f"{sym} should be removed from GeminiService")
