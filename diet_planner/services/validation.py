"""
Meal Plan Validation Service - Validates generated meal plans before completion.
Ensures quality and prevents charging users for failed/nonsensical generations.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of meal plan validation."""
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


class MealPlanValidator:
    """
    Validates generated meal plans to ensure quality.
    Used before marking a goal as completed.
    """

    # Configuration
    MIN_PRICED_ITEMS_RATIO = 0.5  # At least 50% of items must have prices
    MIN_TOTAL_PRICE = 1.0  # Minimum sensible total (in any currency)
    MAX_TOTAL_PRICE = 1000.0  # Maximum sensible total (in any currency)
    MAX_SINGLE_ITEM_PRICE = 200.0  # Flag items over this price

    def validate(
        self,
        meal_plan: Dict[str, Any],
        shopping_list: List[Dict[str, Any]],
        goal_config: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """
        Validate a generated meal plan and shopping list.

        Args:
            meal_plan: The generated meal plan (days structure)
            shopping_list: The generated shopping list with prices
            goal_config: Optional goal configuration (num_days, meal preferences)

        Returns:
            ValidationResult with passed status and any errors/warnings
        """
        errors = []
        warnings = []
        stats = {}

        # Validate meal plan structure
        meal_errors, meal_warnings, meal_stats = self._validate_meal_plan_structure(
            meal_plan, goal_config
        )
        errors.extend(meal_errors)
        warnings.extend(meal_warnings)
        stats.update(meal_stats)

        # Validate shopping list
        shopping_errors, shopping_warnings, shopping_stats = self._validate_shopping_list(
            shopping_list
        )
        errors.extend(shopping_errors)
        warnings.extend(shopping_warnings)
        stats.update(shopping_stats)

        # Validate coherence between meal plan and shopping list
        coherence_warnings = self._validate_coherence(meal_plan, shopping_list)
        warnings.extend(coherence_warnings)

        passed = len(errors) == 0

        logger.info(
            f"Validation result: passed={passed}, errors={len(errors)}, warnings={len(warnings)}"
        )

        return ValidationResult(
            passed=passed,
            errors=errors,
            warnings=warnings,
            stats=stats
        )

    def _validate_meal_plan_structure(
        self,
        meal_plan: Dict[str, Any],
        goal_config: Optional[Dict[str, Any]] = None
    ) -> tuple:
        """Validate the meal plan structure."""
        errors = []
        warnings = []
        stats = {'total_meals': 0, 'days_with_meals': 0}

        # Check for days
        days = meal_plan.get('days', [])
        if not days:
            errors.append("No meal days generated in the meal plan")
            return errors, warnings, stats

        stats['total_days'] = len(days)

        expected_days = goal_config.get('num_days', 7) if goal_config else 7

        if len(days) < expected_days:
            warnings.append(
                f"Expected {expected_days} days but only {len(days)} were generated"
            )

        # Check each day
        for i, day in enumerate(days):
            day_num = day.get('day_number', i + 1)

            # Check for at least one meal type
            has_meal = False
            meal_types = ['breakfast', 'lunch', 'dinner', 'small_meals', 'snacks']

            for meal_type in meal_types:
                meals = day.get(meal_type)
                if meals:
                    if isinstance(meals, list):
                        stats['total_meals'] += len(meals)
                        has_meal = True
                    elif isinstance(meals, dict):
                        stats['total_meals'] += 1
                        has_meal = True

            if has_meal:
                stats['days_with_meals'] = stats.get('days_with_meals', 0) + 1
            else:
                warnings.append(f"Day {day_num} has no meals")

        # Check minimum meals
        if stats['total_meals'] < 3:
            errors.append(f"Too few meals generated: {stats['total_meals']}")

        return errors, warnings, stats

    def _validate_shopping_list(
        self,
        shopping_list: List[Dict[str, Any]]
    ) -> tuple:
        """Validate the shopping list."""
        errors = []
        warnings = []
        stats = {}

        if not shopping_list:
            errors.append("Empty shopping list")
            return errors, warnings, stats

        stats['total_items'] = len(shopping_list)

        # Count items with prices
        priced_items = [
            item for item in shopping_list
            if item.get('price') is not None and float(item.get('price', 0)) > 0
        ]
        stats['priced_items'] = len(priced_items)

        # Check price coverage
        price_ratio = len(priced_items) / len(shopping_list) if shopping_list else 0
        stats['price_coverage_ratio'] = round(price_ratio, 2)

        if price_ratio < self.MIN_PRICED_ITEMS_RATIO:
            errors.append(
                f"Too many items without prices: {len(shopping_list) - len(priced_items)} "
                f"out of {len(shopping_list)} ({round((1 - price_ratio) * 100)}%)"
            )

        # Calculate and validate total price
        total_price = sum(
            float(item.get('price', 0))
            for item in shopping_list
            if item.get('price') is not None
        )
        stats['total_price'] = round(total_price, 2)

        if total_price < self.MIN_TOTAL_PRICE:
            errors.append(f"Suspiciously low total price: {total_price}")

        if total_price > self.MAX_TOTAL_PRICE:
            errors.append(f"Suspiciously high total price: {total_price}")

        # Check for unreasonable individual prices
        expensive_items = []
        for item in shopping_list:
            price = float(item.get('price', 0)) if item.get('price') else 0
            if price > self.MAX_SINGLE_ITEM_PRICE:
                expensive_items.append(
                    f"{item.get('ingredient', 'Unknown')}: {price}"
                )

        if expensive_items:
            warnings.append(
                f"Items with unusually high prices: {', '.join(expensive_items[:5])}"
            )

        # Count by price type
        price_types = {}
        for item in shopping_list:
            pt = item.get('price_type', 'UNKNOWN')
            price_types[pt] = price_types.get(pt, 0) + 1
        stats['price_types'] = price_types

        # Check for LLM-estimated items (just informational)
        llm_estimated = price_types.get('LLM_ESTIMATED', 0)
        if llm_estimated > len(shopping_list) * 0.5:
            warnings.append(
                f"Many prices are estimates ({llm_estimated} of {len(shopping_list)}). "
                "Actual prices may vary."
            )

        return errors, warnings, stats

    def _validate_coherence(
        self,
        meal_plan: Dict[str, Any],
        shopping_list: List[Dict[str, Any]]
    ) -> List[str]:
        """Check coherence between meal plan and shopping list."""
        warnings = []

        # Extract ingredients from meal plan
        meal_ingredients = set()
        days = meal_plan.get('days', [])

        for day in days:
            for meal_type in ['breakfast', 'lunch', 'dinner', 'small_meals', 'snacks']:
                meals = day.get(meal_type, [])
                if isinstance(meals, dict):
                    meals = [meals]
                if not isinstance(meals, list):
                    continue

                for meal in meals:
                    ingredients = meal.get('ingredients', [])
                    for ing in ingredients:
                        if isinstance(ing, dict):
                            name = ing.get('name', ing.get('ingredient', ''))
                        else:
                            name = str(ing)
                        if name:
                            meal_ingredients.add(name.lower().strip())

        # Check shopping list coverage
        shopping_ingredients = set()
        for item in shopping_list:
            name = item.get('ingredient', item.get('name', ''))
            if name:
                shopping_ingredients.add(name.lower().strip())

        # Look for major mismatches
        if meal_ingredients and shopping_ingredients:
            # Check if most meal ingredients are in shopping list
            # (Not all will match due to naming differences)
            coverage = len(meal_ingredients.intersection(shopping_ingredients)) / len(meal_ingredients)
            if coverage < 0.3:
                warnings.append(
                    "Shopping list may not fully cover all recipe ingredients. "
                    "Some items might be missing."
                )

        return warnings

    def is_valid_for_checkout(self, validation_result: ValidationResult) -> bool:
        """
        Determine if the meal plan is valid enough for checkout.
        More lenient than full validation - allows minor issues.

        Args:
            validation_result: Result from validate()

        Returns:
            True if ok to proceed with checkout
        """
        # Must have no critical errors
        if not validation_result.passed:
            return False

        # Check stats for minimum quality
        stats = validation_result.stats
        if stats.get('total_meals', 0) < 3:
            return False
        if stats.get('priced_items', 0) < 1:
            return False

        return True
