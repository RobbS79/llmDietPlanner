"""
Meal Plan Validation Service - Validates generated meal plans before completion.
Ensures quality and prevents charging users for failed/nonsensical generations.
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from decimal import Decimal

from .recipe_coherence import find_coherence_issues
from .recipe_human_judge import judge_plan_coherence

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

        # Whole-plan shopping-list pricing has been removed (shopping/pricing
        # live per-recipe now), so there is no shopping list to price-validate.

        # Validate coverage coherence between meal plan and shopping list.
        coherence_warnings = self._validate_coherence(meal_plan, shopping_list)
        warnings.extend(coherence_warnings)

        # Hard coherence: recipe text says an ingredient is "already
        # prepared / leftover / from yesterday" but the shopping list
        # still charges the user for it. This is the production-blocker
        # class of bug — refuse to publish self-contradictory plans.
        recipe_conflicts = find_coherence_issues(
            meal_plan.get('days', []), shopping_list
        )
        if recipe_conflicts:
            stats['recipe_shopping_conflicts'] = len(recipe_conflicts)
            stats['recipe_shopping_conflicts_sample'] = recipe_conflicts[:5]
            for issue in recipe_conflicts[:10]:
                errors.append(
                    "Recipe / shopping list mismatch: meal "
                    f"\"{issue.get('meal_name', '')}\" (day "
                    f"{issue.get('day_number')}, {issue.get('meal_type')}) "
                    f"describes ingredient \"{issue.get('ingredient', '')}\" "
                    "as already prepared, yet it is on the shopping list."
                )

        # Semantic "simulated human" coherence judge (advisory).
        # A different model family (Gemini writes the plan, Claude grades it)
        # reads the plan, recipes, and shopping list the way a paying
        # customer would and flags what a regex can't: recipes that don't
        # explain how to cook, "eat 1 piece of chocolate bar" non-meals,
        # absurd quantities, ingredients missing from / orphaned on the
        # shopping list. Findings are surfaced as WARNINGS only for now so
        # we can measure the false-positive rate before promoting any of it
        # to a hard checkout gate (see docs/qa-recipe-shopping-coherence.md
        # §7). Fail-open: a disabled/keyless/erroring judge changes nothing.
        judge_language = goal_config.get('language') if goal_config else None
        verdict = judge_plan_coherence(
            meal_plan, shopping_list, language=judge_language
        )
        if verdict.ran:
            stats['human_judge'] = verdict.as_stats()
            stats['human_judge_summary'] = verdict.summary
            for issue in verdict.issues[:15]:
                warnings.append(
                    "Human-judge ({sev}/{cat}) at {loc}: {expl} [quote: \"{quote}\"]".format(
                        sev=issue.get('severity', '?'),
                        cat=issue.get('category', '?'),
                        loc=issue.get('location', '?'),
                        expl=issue.get('explanation', ''),
                        quote=issue.get('quote', ''),
                    )
                )

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
