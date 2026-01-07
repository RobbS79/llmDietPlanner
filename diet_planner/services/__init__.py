"""
Services for the diet planner app.

Two-Phase LLM Architecture:
- Phase 1 (MealPlanService): Generate meal plan based on dietary requirements
- Phase 2 (ShoppingListService): Generate shopping list with actual shop data

Supporting Services:
- PriceDiscoveryService: Fill missing prices via LLM estimation
- MealPlanValidator: Validate generated plans before completion
"""
from .meal_plan import MealPlanService
from .shopping_list import ShoppingListService
from .price_discovery import PriceDiscoveryService
from .validation import MealPlanValidator

__all__ = [
    'MealPlanService',
    'ShoppingListService',
    'PriceDiscoveryService',
    'MealPlanValidator',
]
