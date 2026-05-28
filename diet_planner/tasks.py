"""
Diet Planner Tasks Module
=========================

This module handles the core dietary plan generation workflow using Celery tasks.

## Data Flow Overview:
1. User creates a DietaryGoal with preferences (days, meals, shop, country)
2. process_dietary_goal_task() is triggered as a Celery task
3. Available ingredients are fetched from shop scrapers
4. LLM generates meal plan with ingredients (NO prices - backend handles pricing)
5. Backend aggregates ingredients from all meals into shopping list
6. Backend matches ingredients with shop products and calculates prices
7. DietaryPlan is created with days, shopping_list, and total_price

## Key Functions:
- build_llm_prompt_json(): Creates prompt for meal plan generation (no pricing)
- aggregate_ingredients_from_meals(): Aggregates ingredients from all meals
- validate_shopping_item(): Validates quantities are reasonable
- calculate_package_aware_price(): Calculates price based on packages needed
- process_dietary_goal_task(): Main Celery task orchestrating the flow

## Unit Handling:
- Standard units: g, kg, ml, l, ks (pieces)
- Base units for calculation: g (mass), ml (volume), ks (count)
- Conversions: kg -> g (*1000), l -> ml (*1000)

## Debugging Tips:
- Check logs for "Shopping list validation" entries
- Look for "Price calculation" logs with item details
- If prices seem wrong, verify unit and package_size from shop data
"""

from llm_diet_planner_project.celery_compat import shared_task
from django.utils import timezone
from typing import Dict, Any, List, Optional, Tuple
import json
import logging
import re
import uuid
from decimal import Decimal
from collections import Counter

from .models import DietaryGoal, DietaryPlan, HistoricNutritionPlan
from .schemas import DietaryPlanResponse, MealIdea, ShoppingListItem
from .llm_service import GeminiService
from .scrapers.scraper_service import ScraperService

logger = logging.getLogger(__name__)


# =============================================================================
# INGREDIENT PACKAGE KNOWLEDGE BASE
# =============================================================================
# Information about how ingredients are typically sold, their average weights/sizes,
# and common package sizes. Used for unit conversion and package size inference.

INGREDIENT_PACKAGE_INFO = {
    # Fruits sold per piece
    'avokádo': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'avocado': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'banán': {'typical_unit': 'ks', 'avg_weight_g': 120, 'typical_packages': [1]},
    'banana': {'typical_unit': 'ks', 'avg_weight_g': 120, 'typical_packages': [1]},
    'jablko': {'typical_unit': 'ks', 'avg_weight_g': 180, 'typical_packages': [1]},
    'apple': {'typical_unit': 'ks', 'avg_weight_g': 180, 'typical_packages': [1]},
    'pomeranč': {'typical_unit': 'ks', 'avg_weight_g': 200, 'typical_packages': [1]},
    'orange': {'typical_unit': 'ks', 'avg_weight_g': 200, 'typical_packages': [1]},
    'citron': {'typical_unit': 'ks', 'avg_weight_g': 100, 'typical_packages': [1]},
    'lemon': {'typical_unit': 'ks', 'avg_weight_g': 100, 'typical_packages': [1]},
    'rajče': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'tomato': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'okurka': {'typical_unit': 'ks', 'avg_weight_g': 300, 'typical_packages': [1]},
    'cucumber': {'typical_unit': 'ks', 'avg_weight_g': 300, 'typical_packages': [1]},
    
    # Oils and liquids - common bottle sizes
    'olivový olej': {'typical_unit': 'ml', 'typical_packages': [250, 500, 700, 1000]},
    'olive oil': {'typical_unit': 'ml', 'typical_packages': [250, 500, 700, 1000]},
    'slunečnicový olej': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'sunflower oil': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'řepkový olej': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'canola oil': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    
    # Eggs - sold per piece (typically in packages of 6, 10, 15)
    'vejce': {'typical_unit': 'ks', 'avg_weight_g': 50, 'typical_packages': [6, 10, 15]},
    'egg': {'typical_unit': 'ks', 'avg_weight_g': 50, 'typical_packages': [6, 10, 15]},
    
    # Vegetables with typical package sizes
    'špenát': {'typical_unit': 'g', 'typical_packages': [150, 250, 300]},
    'spinach': {'typical_unit': 'g', 'typical_packages': [150, 250, 300]},
    'salát': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    'lettuce': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    'mix listové zeleniny': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    'leafy green mix': {'typical_unit': 'g', 'typical_packages': [150, 200, 300]},
    
    # Dairy products
    'mléko': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'milk': {'typical_unit': 'ml', 'typical_packages': [500, 1000]},
    'tvaroh': {'typical_unit': 'g', 'typical_packages': [250, 500]},
    'cottage cheese': {'typical_unit': 'g', 'typical_packages': [250, 500]},
    'jogurt': {'typical_unit': 'g', 'typical_packages': [150, 200, 250]},
    'yogurt': {'typical_unit': 'g', 'typical_packages': [150, 200, 250]},
    
    # Meat and fish - usually sold by weight but can have packages
    'kuřecí prsa': {'typical_unit': 'g', 'typical_packages': [500, 1000]},
    'chicken breast': {'typical_unit': 'g', 'typical_packages': [500, 1000]},
    'losos': {'typical_unit': 'g', 'typical_packages': [200, 300, 500]},
    'salmon': {'typical_unit': 'g', 'typical_packages': [200, 300, 500]},
    'tuňák': {'typical_unit': 'g', 'typical_packages': [100, 150, 200]},
    'tuna': {'typical_unit': 'g', 'typical_packages': [100, 150, 200]},
}


# =============================================================================
# QUANTITY VALIDATION CONSTANTS
# =============================================================================
# Maximum reasonable quantities per ingredient category for a weekly meal plan.
# These limits help catch LLM errors where quantities are wildly off.
# Format: 'category': {'max_<unit>': value, 'keywords': [...]}

QUANTITY_LIMITS = {
    'spices': {
        'max_g': 100,  # Max 100g of any spice for a week
        'keywords': ['salt', 'pepper', 'paprika', 'cumin', 'oregano', 'basil',
                     'thyme', 'rosemary', 'cinnamon', 'nutmeg', 'clove', 'ginger',
                     'sul', 'pepr', 'koření', 'sůl', 'pepř', 'kmín', 'bazalka']
    },
    'oils': {
        'max_ml': 500,  # Max 500ml of oil for a week
        'keywords': ['oil', 'olive', 'sunflower', 'canola', 'vegetable oil',
                     'olej', 'olivový', 'slunečnicový', 'řepkový']
    },
    'meat': {
        'max_g': 5000,  # Max 5kg of any single meat type
        'keywords': ['chicken', 'beef', 'pork', 'turkey', 'lamb', 'fish', 'salmon',
                     'kuře', 'hovězí', 'vepřové', 'krůta', 'jehně', 'ryba', 'losos',
                     'kuřecí', 'maso']
    },
    'eggs': {
        'max_ks': 30,  # Max 30 eggs for a week
        'keywords': ['egg', 'vejce', 'vajíčko', 'vajíčka']
    },
    'dairy': {
        'max_ml': 3000,  # Max 3L of milk/cream
        'max_g': 1000,  # Max 1kg of cheese/yogurt
        'keywords': ['milk', 'cream', 'yogurt', 'cheese', 'butter',
                     'mléko', 'smetana', 'jogurt', 'sýr', 'máslo', 'tvaroh']
    },
    'vegetables': {
        'max_g': 5000,  # Max 5kg of any vegetable
        'keywords': ['tomato', 'potato', 'carrot', 'onion', 'garlic', 'pepper',
                     'rajče', 'brambor', 'mrkev', 'cibule', 'česnek', 'paprika',
                     'salát', 'okurka', 'brokolice', 'špenát']
    },
    'fruits': {
        'max_g': 3000,  # Max 3kg of any fruit
        'keywords': ['apple', 'banana', 'orange', 'lemon', 'berry',
                     'jablko', 'banán', 'pomeranč', 'citron', 'jahoda', 'malina']
    },
    'grains': {
        'max_g': 2000,  # Max 2kg of rice/pasta/flour
        'keywords': ['rice', 'pasta', 'flour', 'bread', 'oat',
                     'rýže', 'těstoviny', 'mouka', 'chléb', 'ovesné']
    },
    'liquids': {
        'max_ml': 2000,  # Max 2L of sauces/vinegar/etc
        'keywords': ['sauce', 'vinegar', 'soy', 'broth', 'stock',
                     'omáčka', 'ocet', 'sójová', 'vývar', 'bujón']
    }
}


def transform_days_to_new_format(days_data: List[Dict[str, Any]], goal: DietaryGoal) -> List[Dict[str, Any]]:
    """
    Transform days data from old format (main_courses array) to new format (breakfast/lunch/dinner objects).
    Adds meal_identifier to each meal for recipe detail linking.
    """
    if not days_data or not isinstance(days_data, list):
        return []

    transformed_days = []
    wants_breakfast = getattr(goal, 'breakfast', True)
    wants_lunch = getattr(goal, 'lunch', True)
    wants_dinner = getattr(goal, 'dinner', True)

    for day in days_data:
        day_number = day.get('day_number', len(transformed_days) + 1)
        transformed_day = {
            'day_number': day_number,
            'small_meals': day.get('small_meals', []),
            'snacks': day.get('snacks', []),
        }

        if 'breakfast' in day or 'lunch' in day or 'dinner' in day:
            if wants_breakfast and day.get('breakfast'):
                meal = day['breakfast']
                meal['meal_identifier'] = f"{goal.id}:{day_number}:breakfast:0"
                transformed_day['breakfast'] = meal
            if wants_lunch and day.get('lunch'):
                meal = day['lunch']
                meal['meal_identifier'] = f"{goal.id}:{day_number}:lunch:0"
                transformed_day['lunch'] = meal
            if wants_dinner and day.get('dinner'):
                meal = day['dinner']
                meal['meal_identifier'] = f"{goal.id}:{day_number}:dinner:0"
                transformed_day['dinner'] = meal
        elif 'main_courses' in day:
            main_courses = day['main_courses']
            idx = 0
            if wants_breakfast and idx < len(main_courses):
                meal = main_courses[idx]
                meal['meal_identifier'] = f"{goal.id}:{day_number}:breakfast:0"
                transformed_day['breakfast'] = meal
                idx += 1
            if wants_lunch and idx < len(main_courses):
                meal = main_courses[idx]
                meal['meal_identifier'] = f"{goal.id}:{day_number}:lunch:0"
                transformed_day['lunch'] = meal
                idx += 1
            if wants_dinner and idx < len(main_courses):
                meal = main_courses[idx]
                meal['meal_identifier'] = f"{goal.id}:{day_number}:dinner:0"
                transformed_day['dinner'] = meal
                idx += 1

        transformed_days.append(transformed_day)
    return transformed_days


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def get_ingredient_category(ingredient_name: str) -> Optional[str]:
    """
    Determine the category of an ingredient based on its name.

    Args:
        ingredient_name: Name of the ingredient (can be in any language)

    Returns:
        Category name (e.g., 'spices', 'meat') or None if not categorized

    Example:
        >>> get_ingredient_category('salt')
        'spices'
        >>> get_ingredient_category('chicken breast')
        'meat'
    """
    name_lower = ingredient_name.lower()
    for category, config in QUANTITY_LIMITS.items():
        for keyword in config.get('keywords', []):
            if keyword.lower() in name_lower:
                return category
    return None


def validate_shopping_item(item: Dict[str, Any], num_days: int = 7, context_id: str = "", goal_id: int = 0) -> Dict[str, Any]:
    """
    Validate and potentially adjust unreasonable quantities in a shopping item.

    This function catches common LLM errors where quantities are wildly off,
    such as 5000g of salt or 100 eggs for a week.

    Args:
        item: Shopping item dict with keys: ingredient, quantity, unit
        num_days: Number of days in the meal plan (affects limits)
        context_id: Context ID for logging
        goal_id: Goal ID for logging

    Returns:
        Validated item with potentially adjusted quantity and a 'validation_note' if adjusted

    Example:
        >>> validate_shopping_item({'ingredient': 'salt', 'quantity': 5000, 'unit': 'g'})
        {'ingredient': 'salt', 'quantity': 100, 'unit': 'g', 'validation_note': 'Quantity reduced from 5000g to 100g (max for spices)'}
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    ingredient = item.get('ingredient', '')
    quantity = parse_numeric(item.get('quantity'))
    unit = normalize_unit(item.get('unit', ''))
    
    if log_prefix:
        logger.debug(f"{log_prefix} DETAIL: Validating '{ingredient}' - input: {item.get('quantity')}{item.get('unit', '')}")

    if quantity is None:
        warning_msg = f"Shopping list validation: No quantity for '{ingredient}'"
        if log_prefix:
            logger.warning(f"{log_prefix} WARNING: {warning_msg}")
        else:
            logger.warning(warning_msg)
        return item

    # Scale limits based on number of days (base is 7 days)
    day_factor = Decimal(str(num_days)) / Decimal('7')

    category = get_ingredient_category(ingredient)
    if log_prefix:
        logger.debug(f"{log_prefix} DETAIL: '{ingredient}' category: {category or 'unknown'}, day_factor: {day_factor}")
    
    if not category:
        # Unknown category - apply general sanity check
        # Max 10kg of anything or 100 pieces
        max_g = Decimal('10000') * day_factor
        max_ks = Decimal('100') * day_factor

        base_qty = convert_to_base_value(quantity, unit)
        if unit in ['g', 'kg'] and base_qty > max_g:
            warning_msg = (
                f"Shopping list validation: '{ingredient}' quantity {quantity}{unit} "
                f"exceeds general max {max_g}g, capping"
            )
            if log_prefix:
                logger.warning(f"{log_prefix} WARNING: {warning_msg}")
            else:
                logger.warning(warning_msg)
            item = item.copy()
            item['quantity'] = float(max_g)
            item['unit'] = 'g'
            item['validation_note'] = f"Quantity reduced from {quantity}{unit} to {max_g}g (general max)"
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' adjusted: {quantity}{unit} → {max_g}g")
        elif unit == 'ks' and quantity > max_ks:
            warning_msg = (
                f"Shopping list validation: '{ingredient}' quantity {quantity}{unit} "
                f"exceeds general max {max_ks}ks, capping"
            )
            if log_prefix:
                logger.warning(f"{log_prefix} WARNING: {warning_msg}")
            else:
                logger.warning(warning_msg)
            item = item.copy()
            item['quantity'] = float(max_ks)
            item['validation_note'] = f"Quantity reduced from {quantity}ks to {max_ks}ks (general max)"
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' adjusted: {quantity}ks → {max_ks}ks")
        else:
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' - quantity: {quantity}{unit}, category: unknown, within limits ✓")
        return item

    config = QUANTITY_LIMITS[category]
    max_g = Decimal(str(config.get('max_g', 10000))) * day_factor
    max_ml = Decimal(str(config.get('max_ml', 5000))) * day_factor
    max_ks = Decimal(str(config.get('max_ks', 50))) * day_factor

    if log_prefix:
        logger.debug(
            f"{log_prefix} DETAIL: '{ingredient}' limits (category: {category}, {num_days} days): "
            f"max_g={max_g}g, max_ml={max_ml}ml, max_ks={max_ks}ks"
        )

    # Check against category-specific limits
    if unit in ['g', 'kg']:
        base_qty_g = convert_to_base_value(quantity, unit)  # Convert to grams

        if base_qty_g > max_g:
            warning_msg = (
                f"Shopping list validation: '{ingredient}' ({category}) quantity "
                f"{quantity}{unit} ({base_qty_g}g) exceeds max {max_g}g, capping"
            )
            if log_prefix:
                logger.warning(f"{log_prefix} WARNING: {warning_msg}")
            else:
                logger.warning(warning_msg)
            item = item.copy()
            item['quantity'] = float(max_g)
            item['unit'] = 'g'
            item['validation_note'] = f"Quantity reduced from {quantity}{unit} to {max_g}g (max for {category})"
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' adjusted: {quantity}{unit} ({base_qty_g}g) → {max_g}g")
        else:
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' - quantity: {quantity}{unit} ({base_qty_g}g), category: {category}, within limits ✓")

    elif unit in ['ml', 'l']:
        base_qty_ml = convert_to_base_value(quantity, unit)  # Convert to ml

        if base_qty_ml > max_ml:
            warning_msg = (
                f"Shopping list validation: '{ingredient}' ({category}) quantity "
                f"{quantity}{unit} ({base_qty_ml}ml) exceeds max {max_ml}ml, capping"
            )
            if log_prefix:
                logger.warning(f"{log_prefix} WARNING: {warning_msg}")
            else:
                logger.warning(warning_msg)
            item = item.copy()
            item['quantity'] = float(max_ml)
            item['unit'] = 'ml'
            item['validation_note'] = f"Quantity reduced from {quantity}{unit} to {max_ml}ml (max for {category})"
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' adjusted: {quantity}{unit} ({base_qty_ml}ml) → {max_ml}ml")
        else:
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' - quantity: {quantity}{unit} ({base_qty_ml}ml), category: {category}, within limits ✓")

    elif unit == 'ks':
        if quantity > max_ks:
            warning_msg = (
                f"Shopping list validation: '{ingredient}' ({category}) quantity "
                f"{quantity}ks exceeds max {max_ks}ks, capping"
            )
            if log_prefix:
                logger.warning(f"{log_prefix} WARNING: {warning_msg}")
            else:
                logger.warning(warning_msg)
            item = item.copy()
            item['quantity'] = float(max_ks)
            item['validation_note'] = f"Quantity reduced from {quantity}ks to {max_ks}ks (max for {category})"
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' adjusted: {quantity}ks → {max_ks}ks")
        else:
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: '{ingredient}' - quantity: {quantity}ks, category: {category}, within limits ✓")

    return item


def aggregate_ingredients_from_meals(days: List[Dict[str, Any]], context_id: str = "", goal_id: int = 0) -> List[Dict[str, Any]]:
    """
    Aggregate all ingredients from all meals across all days into a shopping list.

    This function provides backend-side ingredient aggregation as a backup/validation
    for LLM-generated shopping lists. It extracts ingredients from breakfast, lunch,
    dinner, small_meals, and snacks, combining quantities for the same ingredient.

    Args:
        days: List of day objects from the meal plan, each containing meal data
        context_id: Context ID for logging
        goal_id: Goal ID for logging

    Returns:
        List of aggregated shopping items with structure:
        [{'ingredient': str, 'quantity': float, 'unit': str, 'occurrences': int}, ...]

    Example:
        >>> days = [{'day_number': 1, 'breakfast': {'ingredients': [{'name': 'eggs', 'quantity': 2, 'unit': 'ks'}]}}]
        >>> aggregate_ingredients_from_meals(days)
        [{'ingredient': 'eggs', 'quantity': 2.0, 'unit': 'ks', 'occurrences': 1}]
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    
    if log_prefix:
        logger.info(f"{log_prefix} Aggregating ingredients from {len(days)} days of meals...")
    
    # Aggregation map: normalized_name -> {quantity_g/ml/ks: Decimal, unit_type: str, original_name: str, occurrences: int, quantities: List}
    aggregated = {}

    # Track per-day ingredient extraction for logging
    day_ingredient_counts = {}

    for day_idx, day in enumerate(days, 1):
        day_num = day.get('day_number', day_idx)
        day_ingredient_counts[day_num] = {}
        
        # Process all meal types
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            meal = day.get(meal_type)
            if meal and isinstance(meal, dict):
                meal_ingredients = _aggregate_meal_ingredients(meal, aggregated, context_id, goal_id, day_num, meal_type)
                if meal_ingredients:
                    day_ingredient_counts[day_num][meal_type] = len(meal_ingredients)

        # Process arrays of meals (small_meals, snacks)
        for meal_type in ['small_meals', 'snacks']:
            meals = day.get(meal_type, [])
            if isinstance(meals, list):
                total_ingredients = 0
                for meal in meals:
                    if isinstance(meal, dict):
                        meal_ingredients = _aggregate_meal_ingredients(meal, aggregated, context_id, goal_id, day_num, meal_type)
                        if meal_ingredients:
                            total_ingredients += len(meal_ingredients)
                if total_ingredients > 0:
                    day_ingredient_counts[day_num][meal_type] = total_ingredients
        
        # Log per-day summary
        if log_prefix and day_ingredient_counts[day_num]:
            meal_summary = ", ".join([f"{mt}: {count} ingredients" for mt, count in day_ingredient_counts[day_num].items()])
            logger.debug(f"{log_prefix} DETAIL: Day {day_num} - {meal_summary}")

    # Convert aggregated map to list
    result = []
    for normalized_name, data in aggregated.items():
        # Determine best unit for display (use larger unit if quantity is large)
        quantity = data['quantity']
        unit_type = data['unit_type']
        quantities_list = data.get('quantities', [])

        if unit_type == 'mass':
            # If >= 1000g, display as kg
            if quantity >= 1000:
                display_qty = float(quantity / 1000)
                display_unit = 'kg'
            else:
                display_qty = float(quantity)
                display_unit = 'g'
        elif unit_type == 'volume':
            # If >= 1000ml, display as l
            if quantity >= 1000:
                display_qty = float(quantity / 1000)
                display_unit = 'l'
            else:
                display_qty = float(quantity)
                display_unit = 'ml'
        else:  # count
            display_qty = float(quantity)
            display_unit = 'ks'

        result.append({
            'ingredient': data['original_name'],
            'quantity': display_qty,
            'unit': display_unit,
            'occurrences': data['occurrences']
        })

        # Log aggregation details for each ingredient
        if log_prefix:
            quantities_str = f"quantities {quantities_list}" if quantities_list else f"total {display_qty}{display_unit}"
            logger.debug(
                f"{log_prefix} DETAIL: Found '{data['original_name']}' in {data['occurrences']} meals: "
                f"{quantities_str} → total {display_qty}{display_unit}"
            )

    if log_prefix:
        logger.info(f"{log_prefix} Aggregated {len(result)} unique ingredients from meal plan")
    else:
        logger.info(f"Aggregated {len(result)} unique ingredients from meal plan")
    return result


def _log_item_details(item: Dict[str, Any]) -> str:
    """
    Format item details for logging.
    
    Args:
        item: Shopping list item dictionary
        
    Returns:
        Formatted string with item details
    """
    parts = []
    
    # Ingredient name
    ingredient = item.get('ingredient', 'unknown')
    parts.append(f"'{ingredient}'")
    
    # Quantity
    quantity = item.get('quantity')
    unit = item.get('unit', '')
    if quantity is not None:
        parts.append(f"{quantity}{unit}")
    
    # Price information
    price = item.get('price')
    price_total = item.get('price_total')
    currency = item.get('currency', '')
    
    if price_total is not None:
        parts.append(f"{price_total} {currency}")
        if price != price_total:
            parts.append(f"(per unit: {price} {currency})")
    elif price is not None:
        parts.append(f"{price} {currency}")
    
    # Source/status
    if item.get('estimated'):
        parts.append("[ESTIMATED]")
    else:
        parts.append("[FROM LEAFLET]")
    
    # Matched product name if available
    matched_name = item.get('matched_product_name')
    if matched_name and matched_name != ingredient:
        parts.append(f"-> '{matched_name}'")
    
    return " | ".join(parts)


def _aggregate_meal_ingredients(meal: Dict[str, Any], aggregated: Dict[str, Any], context_id: str = "", goal_id: int = 0, day_num: int = 0, meal_type: str = "") -> List[str]:
    """
    Helper function to aggregate ingredients from a single meal into the aggregated dict.

    Args:
        meal: Meal object with 'ingredients' list
        aggregated: Dict to accumulate ingredients into (modified in place)
        context_id: Context ID for logging
        goal_id: Goal ID for logging
        day_num: Day number for logging
        meal_type: Meal type for logging
        
    Returns:
        List of ingredient names found in this meal
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    ingredients = meal.get('ingredients', [])
    found_ingredients = []

    for ing in ingredients:
        # Handle both dict and string formats
        if isinstance(ing, dict):
            name = ing.get('name', ing.get('ingredient', ''))
            quantity = ing.get('quantity')
            unit = ing.get('unit', '')
        elif isinstance(ing, str):
            # Try to parse "500g chicken" format
            match = re.match(r'^(\d+(?:\.\d+)?)\s*(g|kg|ml|l|ks)?\s*(.+)$', ing.strip())
            if match:
                quantity = match.group(1)
                unit = match.group(2) or ''
                name = match.group(3)
            else:
                name = ing
                quantity = None
                unit = ''
        else:
            continue

        if not name:
            continue

        # Normalize the ingredient name for grouping
        normalized = name.lower().strip()

        # Parse quantity
        qty = parse_numeric(quantity) if quantity else Decimal('1')
        if qty is None:
            qty = Decimal('1')

        # Normalize unit and determine type
        norm_unit = normalize_unit(unit)
        if norm_unit in ['g', 'kg']:
            unit_type = 'mass'
            base_qty = convert_to_base_value(qty, norm_unit)  # to grams
        elif norm_unit in ['ml', 'l']:
            unit_type = 'volume'
            base_qty = convert_to_base_value(qty, norm_unit)  # to ml
        else:
            unit_type = 'count'
            base_qty = qty  # pieces/units

        # Log ingredient parsing details
        if log_prefix:
            logger.debug(
                f"{log_prefix} DETAIL: Parsed ingredient '{name}': "
                f"raw qty={quantity}, raw unit='{unit}' → parsed qty={qty}, "
                f"normalized unit='{norm_unit}', base qty={base_qty} ({unit_type})"
            )

        # Aggregate
        if normalized not in aggregated:
            aggregated[normalized] = {
                'quantity': base_qty,
                'unit_type': unit_type,
                'original_name': name,
                'occurrences': 1,
                'quantities': [f"{qty}{norm_unit}"]
            }
            found_ingredients.append(name)
        else:
            # Add to existing (only if same unit type)
            existing = aggregated[normalized]
            if existing['unit_type'] == unit_type:
                existing['quantity'] += base_qty
                existing['occurrences'] += 1
                existing['quantities'].append(f"{qty}{norm_unit}")
                found_ingredients.append(name)
            else:
                # Unit type mismatch - log warning and keep first
                warning_msg = (
                    f"Ingredient '{name}' has mixed unit types: "
                    f"{existing['unit_type']} vs {unit_type}, keeping first"
                )
                if log_prefix:
                    logger.warning(f"{log_prefix} WARNING: {warning_msg}")
                else:
                    logger.warning(warning_msg)
                existing['occurrences'] += 1
    
    return found_ingredients


def build_llm_prompt_json(goal: DietaryGoal, available_ingredients: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Build a structured JSON prompt for the LLM to generate a meal plan.

    IMPORTANT: This prompt is for meal plan generation ONLY.
    The LLM should NOT generate shopping lists or prices - the backend handles that.

    Args:
        goal: DietaryGoal with user preferences
        available_ingredients: Optional list of available shop ingredients (for context only)

    Returns:
        Dict prompt structure for LLM

    Data Flow:
        1. This prompt generates meal plan with ingredients per meal
        2. Backend aggregates ingredients using aggregate_ingredients_from_meals()
        3. Backend matches with shop data and calculates prices
    """
    prompt_data = {
        "task": "generate_personalised_meal_plan",
        "user_requirements": {
            "dietary_prompt": goal.prompt,
            "dietary_restrictions": goal.dietary_restrictions or None,
        },
        "localisation": {
            "language_code": goal.language_code,
            "country": goal.country,
            "city": goal.city,
        },
        "meal_plan_configuration": {
            "num_days": goal.num_days,
            "include_breakfast": goal.breakfast,
            "include_lunch": goal.lunch,
            "include_dinner": goal.dinner,
            "small_meals_per_day": goal.small_meals_per_day,
            "snacks_per_day": goal.snacks_per_day
        },
        "instructions": [
            "Generate a 'days' array with exactly {num_days} day objects".format(num_days=goal.num_days),
            "Each day must have 'day_number' (1, 2, 3, ...)",
            "Include breakfast/lunch/dinner as single meal objects (not arrays) based on configuration",
            "Include 'small_meals' and 'snacks' as arrays of meal objects",
            "Each meal must include: name, description, preparation_time (minutes), nutritional_info",
            "Each meal must include 'ingredients' as an array of objects with: name, quantity (number), unit (g/kg/ml/l/ks)",
            "Use metric units only: g for grams, kg for kilograms, ml for milliliters, l for liters, ks for pieces",
            "Quantities should be realistic per-meal amounts (e.g., 200g chicken, 2 eggs, 50ml oil)",
            "DO NOT generate a shopping_list - the backend will create it from ingredients",
            "DO NOT include prices - the backend handles pricing",
            "All text content (names, descriptions) must be in the specified language"
        ],
        "output_format": {
            "type": "json",
            "structure": {
                "days": [
                    {
                        "day_number": 1,
                        "breakfast": {"name": "...", "description": "...", "preparation_time": 15, "ingredients": [{"name": "eggs", "quantity": 2, "unit": "ks"}], "nutritional_info": {"calories": 300, "protein": "20g", "carbs": "5g", "fat": "22g"}},
                        "lunch": "...(same structure)...",
                        "dinner": "...(same structure)...",
                        "small_meals": ["...(array of meal objects)..."],
                        "snacks": ["...(array of meal objects)..."]
                    }
                ]
            }
        }
    }

    # Add available ingredients as context (helps LLM use realistic ingredient names)
    if available_ingredients:
        # Limit to prevent token overflow
        limited_ingredients = available_ingredients[:100]
        prompt_data["context"] = {
            "available_at_shop": goal.shop,
            "sample_ingredients": [
                {"name": ing.get('ingredient_name', ing.get('display_name', '')), "unit": ing.get('unit', '')}
                for ing in limited_ingredients
                if ing.get('ingredient_name') or ing.get('display_name')
            ][:50],  # Further limit the actual list
            "note": "Use ingredient names similar to these when possible for better matching"
        }

    return prompt_data


@shared_task(bind=True, max_retries=3)
def scrape_leaflet_task(self, shop: str, country: str) -> Dict[str, Any]:
    """
    Async Celery task to scrape leaflet data for a shop/country.
    
    Checks cache first, scrapes if needed.
    
    Args:
        shop: Shop code (e.g., 'LIDL_CZ')
        country: Country code (e.g., 'CZ')
        
    Returns:
        Dict with scraping result information
    """
    try:
        logger.info(f"Scraping leaflet task started for {shop} ({country})")
        
        # Use ScraperService to get available ingredients (handles caching)
        ingredients = ScraperService.get_available_ingredients(shop, country)
        
        return {
            'status': 'success',
            'shop': shop,
            'country': country,
            'ingredient_count': len(ingredients),
        }
    except Exception as exc:
        logger.error(f"Error in scrape_leaflet_task for {shop} ({country}): {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=2)
def process_protocol_pdf_task(self, plan_id: int) -> Dict[str, Any]:
    try:
        from .services.protocol_processor import ProtocolProcessorService
        ProtocolProcessorService().process_protocol(plan_id)
        return {'status': 'success', 'plan_id': plan_id}
    except Exception as exc:
        logger.error(f"Error processing protocol PDF {plan_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)


def _build_protocol_prompt(goal: DietaryGoal) -> str:
    """Build user_prompt with protocol constraints prepended if a protocol is attached."""
    user_prompt = goal.prompt
    if goal.historic_plan_reference_id:
        try:
            protocol = HistoricNutritionPlan.objects.get(
                id=goal.historic_plan_reference_id,
                processing_status='completed',
            )
            constraints = protocol.structured_constraints
            if constraints:
                user_prompt = (
                    f"[PROFESSIONAL DIET PROTOCOL - PRIORITY]\n"
                    f"The user has a professional diet protocol from a specialist. "
                    f"The plan MUST respect these constraints:\n{constraints}\n\n"
                    f"[USER REQUIREMENTS]\n{goal.prompt}"
                )
        except HistoricNutritionPlan.DoesNotExist:
            pass
    return user_prompt


# =============================================================================
# UNIT CONVERSION FUNCTIONS
# =============================================================================

def normalize_unit(unit: str) -> str:
    """
    Standardize units for comparison across different languages and formats.

    Supported units:
    - Mass: g (grams), kg (kilograms)
    - Volume: ml (milliliters), l (liters)
    - Count: ks (pieces/kusy)

    Args:
        unit: Unit string in any format (e.g., 'kilogram', 'g.', 'kusů')

    Returns:
        Normalized unit code (g, kg, ml, l, ks) or original if unknown

    Examples:
        >>> normalize_unit('kilogramy')
        'kg'
        >>> normalize_unit('pcs')
        'ks'
    """
    if not unit:
        return ''
    u = str(unit).lower().strip()

    # Comprehensive mapping for multiple languages (Czech, Slovak, Polish, English)
    mapping = {
        # Mass - kilograms
        'kg': 'kg', 'kilogram': 'kg', 'kilogramy': 'kg', 'kilogramů': 'kg',
        'kilogramow': 'kg', 'kg.': 'kg',
        # Mass - grams
        'g': 'g', 'gram': 'g', 'gramy': 'g', 'gramů': 'g', 'gramow': 'g', 'g.': 'g',
        # Volume - liters
        'l': 'l', 'litr': 'l', 'litry': 'l', 'litrů': 'l', 'litrow': 'l',
        'liter': 'l', 'litre': 'l', 'l.': 'l',
        # Volume - milliliters
        'ml': 'ml', 'mililitr': 'ml', 'mililitry': 'ml', 'mililitrů': 'ml',
        'milliliter': 'ml', 'millilitre': 'ml', 'ml.': 'ml',
        # Count - pieces
        'ks': 'ks', 'kus': 'ks', 'kusy': 'ks', 'kusů': 'ks', 'kusow': 'ks',
        'piece': 'ks', 'pieces': 'ks', 'pcs': 'ks', 'pc': 'ks', 'szt': 'ks',
        'sztuk': 'ks', 'sztuki': 'ks',
    }
    return mapping.get(u, u)


def convert_to_base_value(val: Decimal, unit: str) -> Decimal:
    """
    Convert value to base metric unit for calculations.

    Base units:
    - Mass: grams (g)
    - Volume: milliliters (ml)
    - Count: pieces (ks) - no conversion

    Args:
        val: Numeric value to convert
        unit: Unit string (will be normalized)

    Returns:
        Value converted to base unit

    Examples:
        >>> convert_to_base_value(Decimal('1.5'), 'kg')
        Decimal('1500')  # 1.5kg = 1500g
        >>> convert_to_base_value(Decimal('2'), 'l')
        Decimal('2000')  # 2l = 2000ml
    """
    u = normalize_unit(unit)
    if u == 'kg':
        return val * 1000  # kg -> g
    if u == 'l':
        return val * 1000  # l -> ml
    return val  # g, ml, ks remain unchanged


# =============================================================================
# PACKAGE SIZE INFERENCE AND UNIT CONVERSION
# =============================================================================

def get_ingredient_package_info(ingredient_name: str) -> Optional[Dict[str, Any]]:
    """
    Lookup package information for an ingredient from knowledge base.
    
    Handles normalized names and aliases (e.g., 'avokádo' and 'avocado').
    
    Args:
        ingredient_name: Ingredient name (can be in any language)
        
    Returns:
        Dict with package info or None if not found:
        {
            'typical_unit': 'ks' | 'g' | 'ml',
            'avg_weight_g': float (for piece-based items),
            'typical_packages': [list of common package sizes]
        }
    """
    if not ingredient_name:
        return None
    
    name_lower = ingredient_name.lower().strip()
    
    # Direct lookup
    if name_lower in INGREDIENT_PACKAGE_INFO:
        return INGREDIENT_PACKAGE_INFO[name_lower]
    
    # Try normalized lookup (remove accents, special chars)
    normalized = re.sub(r'[^a-z0-9\s]', '', name_lower.lower())
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    if normalized in INGREDIENT_PACKAGE_INFO:
        return INGREDIENT_PACKAGE_INFO[normalized]
    
    # Try partial match (e.g., "avokádo bio" matches "avokádo")
    for key, info in INGREDIENT_PACKAGE_INFO.items():
        if key in name_lower or name_lower in key:
            return info
    
    return None


def infer_package_size(ingredient_name: str, product_unit: str, matched_offers: List[Dict[str, Any]], context_id: str = "", goal_id: int = 0) -> Optional[Decimal]:
    """
    Infer package size when it's missing from the matched product.
    
    Strategy:
    1. Check ingredient knowledge base
    2. Look at actual offers to see what packages exist
    3. Return most reasonable package size
    
    Args:
        ingredient_name: Name of the ingredient
        product_unit: Unit from the shop product (e.g., 'ks', 'g', 'ml')
        matched_offers: List of matched offers (can be empty)
        context_id: Context ID for logging
        goal_id: Goal ID for logging
        
    Returns:
        Decimal package size or None if can't infer
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    
    # Strategy 1: Check actual offers first - most reliable
    if matched_offers:
        package_sizes = []
        for offer in matched_offers:
            pkg_size = offer.get('package_size')
            unit = offer.get('unit', '')
            if pkg_size and normalize_unit(unit) == normalize_unit(product_unit):
                package_sizes.append(Decimal(str(pkg_size)))
        
        if package_sizes:
            # Return most common package size
            size_counts = Counter(package_sizes)
            most_common = size_counts.most_common(1)[0][0]
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: Inferred package_size={most_common} for '{ingredient_name}' from {len(package_sizes)} offers")
            return most_common
    
    # Strategy 2: Check knowledge base
    info = get_ingredient_package_info(ingredient_name)
    if info:
        typical_unit = info.get('typical_unit', '')
        if normalize_unit(typical_unit) == normalize_unit(product_unit):
            typical_packages = info.get('typical_packages', [])
            if typical_packages:
                # For piece-based items, return 1 piece
                if typical_unit == 'ks':
                    if log_prefix:
                        logger.debug(f"{log_prefix} DETAIL: Inferred package_size=1 piece for '{ingredient_name}' from knowledge base")
                    return Decimal('1')
                # For other units, return most common package size
                else:
                    most_common = Decimal(str(typical_packages[0]))
                    if log_prefix:
                        logger.debug(f"{log_prefix} DETAIL: Inferred package_size={most_common} for '{ingredient_name}' from knowledge base")
                    return most_common
    
    # Strategy 3: Default inference based on unit
    if normalize_unit(product_unit) == 'ks':
        # Piece-based items default to 1 piece
        if log_prefix:
            logger.debug(f"{log_prefix} DETAIL: Default inference: package_size=1 for piece-based '{ingredient_name}'")
        return Decimal('1')
    elif normalize_unit(product_unit) in ['g', 'ml']:
        # For g/ml without package size, assume it's per unit (1g or 1ml)
        # This is a fallback - ideally we'd have better data
        if log_prefix:
            logger.debug(f"{log_prefix} DETAIL: Default inference: package_size=1 for '{ingredient_name}' (unit: {product_unit})")
        return Decimal('1')
    
    if log_prefix:
        logger.warning(f"{log_prefix} WARNING: Could not infer package_size for '{ingredient_name}' (unit: {product_unit})")
    return None


def convert_requirement_to_purchasable_units(item: Dict[str, Any], matched_product: Dict[str, Any], ingredient_info: Optional[Dict[str, Any]] = None, context_id: str = "", goal_id: int = 0) -> Dict[str, Any]:
    """
    Convert recipe requirement to how item is actually sold.
    
    Examples:
    - Recipe: "200g avocado", Shop: "avocado 49 CZK/piece" → "2 pieces"
    - Recipe: "300ml olive oil", Shop: "oil 89 CZK/500ml" → "1 bottle (500ml)"
    
    Args:
        item: Shopping item with recipe requirement (quantity, unit)
        matched_product: Matched product from shop (unit, package_size)
        ingredient_info: Optional ingredient package info from knowledge base
        context_id: Context ID for logging
        goal_id: Goal ID for logging
        
    Returns:
        Updated item dict with converted quantity and unit
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    
    req_qty = parse_numeric(item.get('quantity'))
    req_unit = normalize_unit(item.get('unit', ''))
    product_unit = normalize_unit(matched_product.get('unit', ''))
    package_size = matched_product.get('package_size')
    
    if req_qty is None:
        return item
    
    # Get ingredient info if not provided
    if ingredient_info is None:
        ingredient_info = get_ingredient_package_info(item.get('ingredient', ''))
    
    # Case 1: Unit mismatch - recipe in weight/volume, product in pieces
    if req_unit in ['g', 'kg', 'ml', 'l'] and product_unit == 'ks':
        if ingredient_info and ingredient_info.get('avg_weight_g'):
            avg_weight = Decimal(str(ingredient_info['avg_weight_g']))
            req_base = convert_to_base_value(req_qty, req_unit)
            pieces_needed = (req_base / avg_weight).to_integral_value(rounding='ROUND_CEILING')
            
            if log_prefix:
                logger.debug(
                    f"{log_prefix} DETAIL: Converting {req_qty}{req_unit} ({req_base}g) "
                    f"→ {pieces_needed} pieces (avg {avg_weight}g/piece) for '{item.get('ingredient')}'"
                )
            
            item['quantity'] = float(pieces_needed)
            item['unit'] = 'ks'
            item['original_requirement'] = {'quantity': req_qty, 'unit': req_unit}
            return item
    
    # Case 2: Same unit type but need to select appropriate package size
    # This will be handled in find_appropriate_package_size()
    
    return item


def find_appropriate_package_size(required_qty: Decimal, required_unit: str, available_packages: List[Decimal], product_unit: str, context_id: str = "", goal_id: int = 0) -> Optional[Decimal]:
    """
    Find the smallest package size that satisfies the requirement.
    
    Always rounds UP - if need 450ml and packages are [250ml, 500ml, 700ml],
    returns 700ml (smallest that fits, since 500ml isn't enough).
    
    Args:
        required_qty: Required quantity
        required_unit: Unit of required quantity
        available_packages: List of available package sizes
        product_unit: Unit of product packages
        context_id: Context ID for logging
        goal_id: Goal ID for logging
        
    Returns:
        Decimal package size or None if no suitable package found
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    
    if not available_packages:
        return None
    
    # Convert required quantity to base unit
    req_base = convert_to_base_value(required_qty, required_unit)
    
    # Sort packages ascending
    sorted_packages = sorted(available_packages)
    
    # Find smallest package that satisfies requirement
    for pkg_size in sorted_packages:
        pkg_base = convert_to_base_value(pkg_size, product_unit)
        if pkg_base >= req_base:
            if log_prefix:
                logger.debug(
                    f"{log_prefix} DETAIL: Selected package {pkg_size}{product_unit} "
                    f"(need {required_qty}{required_unit} = {req_base} base units)"
                )
            return pkg_size
    
    # If no package is large enough, return largest available (user will need multiple)
    largest = sorted_packages[-1]
    if log_prefix:
        logger.debug(
            f"{log_prefix} DETAIL: No single package satisfies {required_qty}{required_unit}, "
            f"using largest available: {largest}{product_unit}"
        )
    return largest


def parse_numeric(val: Any) -> Optional[Decimal]:
    """
    Extract decimal number from various formats.

    Handles:
    - Numbers: int, float, Decimal
    - Strings: "123", "123.45", "123,45" (European format)
    - Mixed strings: "about 500g" -> 500

    Args:
        val: Value to parse (any type)

    Returns:
        Decimal value or None if parsing fails

    Examples:
        >>> parse_numeric(500)
        Decimal('500')
        >>> parse_numeric("123,45")
        Decimal('123.45')
        >>> parse_numeric("about 500g")
        Decimal('500')
    """
    if val is None or val == '':
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))

    # Try to extract number from string
    match = re.search(r'([\d,\.]+)', str(val))
    if match:
        try:
            # Handle European comma decimal separator
            num_str = match.group(1).replace(',', '.')
            # Handle cases like "1.500" (thousand separator) vs "1.5" (decimal)
            # If there are multiple dots, remove all but last
            parts = num_str.split('.')
            if len(parts) > 2:
                num_str = ''.join(parts[:-1]) + '.' + parts[-1]
            return Decimal(num_str)
        except Exception:
            return None
    return None


# =============================================================================
# PRICE CALCULATION FUNCTIONS
# =============================================================================

def calculate_package_aware_price(item: Dict[str, Any], context_id: str = "", goal_id: int = 0) -> Optional[Decimal]:
    """
    Calculate total price based on how many full packages are needed.

    This function determines the number of packages required to satisfy
    the requested quantity and returns the total price.

    Args:
        item: Shopping item dict with keys:
            - quantity: Required quantity (e.g., 400)
            - unit: Required unit (e.g., 'g')
            - price: Price per package/unit from shop
            - product_unit: Unit of the shop product (e.g., 'kg', 'g')
            - package_size: Size of package (e.g., 500 for 500g package)
        context_id: Context ID for logging
        goal_id: Goal ID for logging

    Returns:
        Total price as Decimal, or None if calculation not possible

    Algorithm:
        1. Infer package_size if missing
        2. Convert required quantity to base unit (g/ml/ks)
        3. Convert package size to base unit
        4. Calculate packages needed: ceil(required / package_size)
        5. Total price = packages * price_per_package

    Examples:
        Need 400g, package is 500g at 39 CZK:
        - packages = ceil(400/500) = 1
        - total = 1 * 39 = 39 CZK

        Need 800g, package is 500g at 39 CZK:
        - packages = ceil(800/500) = 2
        - total = 2 * 39 = 78 CZK

        Need 1.2kg, product is priced per kg at 89.90 CZK:
        - Convert 1.2kg to 1200g, per-kg = 1000g package
        - packages = ceil(1200/1000) = 2
        - total = 2 * 89.90 = 179.80 CZK

    Debugging:
        Check logs for "Price calculation" entries with full item details
    """
    log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]" if context_id and goal_id else ""
    
    # Extract and parse values
    req_qty = parse_numeric(item.get('quantity'))
    req_unit = normalize_unit(item.get('unit', ''))
    off_price = parse_numeric(item.get('price'))
    off_unit = normalize_unit(item.get('product_unit', ''))
    off_pkg_size = parse_numeric(item.get('package_size'))
    ingredient = item.get('ingredient', 'unknown')

    # Log input for debugging
    if log_prefix:
        logger.debug(
            f"{log_prefix} DETAIL: Price calculation for '{ingredient}': "
            f"need {req_qty}{req_unit}, product: {off_price} {item.get('currency', '')} per "
            f"{off_pkg_size or '?'}{off_unit} (package_size: {off_pkg_size}, product_unit: '{off_unit}')"
        )
    else:
        logger.debug(
            f"Price calculation for '{ingredient}': "
            f"need {req_qty}{req_unit}, "
            f"product: {off_price} per {off_pkg_size or '?'}{off_unit}"
        )

    # Validate required fields
    if req_qty is None:
        warning_msg = f"Price calculation: No quantity for '{ingredient}'"
        if log_prefix:
            logger.warning(f"{log_prefix} WARNING: {warning_msg}")
        else:
            logger.warning(warning_msg)
        return None
    if off_price is None:
        warning_msg = f"Price calculation: No price for '{ingredient}'"
        if log_prefix:
            logger.warning(f"{log_prefix} WARNING: {warning_msg}")
        else:
            logger.warning(warning_msg)
        return None

    # Infer package_size if missing
    if off_pkg_size is None or off_pkg_size <= 0:
        # Try to get all matching offers to see available packages
        ingredient_name = item.get('ingredient', '')
        shop = item.get('shop', '')
        country = item.get('country', '')
        
        matched_offers = []
        if ingredient_name and shop and country:
            try:
                from .scrapers.scraper_service import ScraperService
                matched_offers = ScraperService.find_all_matching_products(ingredient_name, shop, country)
            except Exception as e:
                if log_prefix:
                    logger.debug(f"{log_prefix} DETAIL: Could not fetch all offers for inference: {e}")
        
        inferred_pkg_size = infer_package_size(ingredient_name, off_unit, matched_offers, context_id, goal_id)
        if inferred_pkg_size:
            off_pkg_size = inferred_pkg_size
            item['package_size'] = float(inferred_pkg_size)
            if log_prefix:
                logger.debug(f"{log_prefix} DETAIL: Using inferred package_size: {off_pkg_size}{off_unit}")

    # Convert required quantity to base unit
    req_base = convert_to_base_value(req_qty, req_unit)
    if log_prefix:
        logger.debug(f"{log_prefix} DETAIL: Converted required quantity: {req_qty}{req_unit} → {req_base} base units")

    # Determine package size in base units
    if off_pkg_size and off_pkg_size > 0:
        pkg_base = convert_to_base_value(off_pkg_size, off_unit)
        if log_prefix:
            logger.debug(f"{log_prefix} DETAIL: Package size: {off_pkg_size}{off_unit} → {pkg_base} base units")
    else:
        # No package size specified and couldn't infer - assume per-unit pricing
        # For kg/l, assume price is per kg/l (1000g/ml)
        # For ks/g/ml, assume price is per unit
        if off_unit in ['kg', 'l']:
            pkg_base = Decimal('1000')
        elif off_unit in ['g', 'ml']:
            pkg_base = Decimal('1')
        else:
            pkg_base = Decimal('1')
        if log_prefix:
            logger.debug(f"{log_prefix} DETAIL: No package_size specified and inference failed, assuming pkg_base={pkg_base} for unit '{off_unit}'")

    # Guard against division by zero
    if pkg_base <= 0:
        warning_msg = f"Price calculation: Invalid package size for '{ingredient}'"
        if log_prefix:
            logger.warning(f"{log_prefix} WARNING: {warning_msg}")
        else:
            logger.warning(warning_msg)
        return off_price

    # Calculate whole packages needed (round up)
    num_packages = (req_base / pkg_base).to_integral_value(rounding='ROUND_CEILING')
    if log_prefix:
        logger.debug(
            f"{log_prefix} DETAIL: Packages calculation: {req_base} base units / {pkg_base} base units per package = "
            f"{req_base / pkg_base} → rounded up to {num_packages} packages"
        )

    # Check if we should look for better package options
    ingredient_name = item.get('ingredient', '')
    shop = item.get('shop', '')
    country = item.get('country', '')
    ingredient_info = get_ingredient_package_info(ingredient_name)
    
    # If we have multiple package options from knowledge base or offers, try to find better fit
    if ingredient_info and ingredient_info.get('typical_packages'):
        typical_packages = [Decimal(str(p)) for p in ingredient_info['typical_packages']]
        if typical_packages and off_pkg_size not in typical_packages:
            # Check if any typical package would be better
            better_package = find_appropriate_package_size(
                req_qty, req_unit, typical_packages, off_unit, context_id, goal_id
            )
            if better_package and better_package != off_pkg_size:
                # Note: We can't change the package size here as we're using the matched product's price
                # But we can log it for debugging
                if log_prefix:
                    logger.debug(
                        f"{log_prefix} DETAIL: Knowledge base suggests better package size {better_package}{off_unit} "
                        f"(current: {off_pkg_size}{off_unit}) for '{ingredient}', but using matched product price"
                    )

    # Sanity checks
    if num_packages > Decimal('100'):
        warning_msg = (
            f"Price calculation: Excessive packages ({num_packages}) for '{ingredient}', "
            f"capping at 10. Check quantity ({req_qty}{req_unit}) and package ({off_pkg_size}{off_unit})"
        )
        if log_prefix:
            logger.warning(f"{log_prefix} WARNING: {warning_msg}")
        else:
            logger.warning(warning_msg)
        num_packages = Decimal('10')

    total_price = num_packages * off_price

    # Enhanced price validation with per-unit calculation
    price_per_base_unit = None
    if pkg_base > 0 and off_price:
        price_per_base_unit = off_price / pkg_base
    
    # Calculate price per 100g or per piece for easier debugging
    price_per_100g = None
    price_per_piece = None
    if req_unit in ['g', 'kg'] and pkg_base > 0:
        # Convert price to per 100g
        price_per_100g = (off_price / pkg_base) * Decimal('100')
    elif req_unit == 'ks' or off_unit == 'ks':
        price_per_piece = off_price / num_packages if num_packages > 0 else off_price
    
    # Sanity check on total price (max 2000 per item for reasonable meal plan)
    if total_price > Decimal('2000'):
        warning_msg = (
            f"Price calculation: Excessive price ({total_price} {item.get('currency', '')}) for '{ingredient}'. "
            f"Quantity: {req_qty}{req_unit}, Packages: {num_packages} × {off_price} {item.get('currency', '')}, "
            f"Package size: {off_pkg_size}{off_unit}"
        )
        if price_per_100g:
            warning_msg += f", Price per 100g: {price_per_100g:.2f}"
        if log_prefix:
            logger.warning(f"{log_prefix} WARNING: {warning_msg}")
        else:
            logger.warning(warning_msg)
    elif price_per_100g and price_per_100g > Decimal('500'):
        # Warn if price per 100g seems very high (e.g., >500 CZK per 100g is unusual)
        warning_msg = (
            f"Price calculation: High price per 100g ({price_per_100g:.2f} {item.get('currency', '')}/100g) "
            f"for '{ingredient}'. Total: {total_price} {item.get('currency', '')} for {req_qty}{req_unit}"
        )
        if log_prefix:
            logger.warning(f"{log_prefix} WARNING: {warning_msg}")
        else:
            logger.warning(warning_msg)

    if log_prefix:
        logger.debug(
            f"{log_prefix} DETAIL: Price calculation result for '{ingredient}': "
            f"{num_packages} packages × {off_price} {item.get('currency', '')} = {total_price} {item.get('currency', '')}"
        )
    else:
        logger.debug(
            f"Price calculation result for '{ingredient}': "
            f"{num_packages} packages x {off_price} = {total_price}"
        )

    return total_price


@shared_task(bind=True, max_retries=3)
def process_dietary_goal_task(self, goal_id: int) -> Dict[str, Any]:
    """
    Main Celery task - SIMPLIFIED: Single LLM call does everything.
    
    This matches Gemini web UI approach:
    1. One LLM call generates meal plan + recipes + shopping list + prices
    2. Backend only validates and stores results
    
    Args:
        goal_id: ID of the DietaryGoal to process

    Returns:
        Dict with 'status' and 'plan_id' on success
    """
    try:
        # Generate unique context ID for tracing this shopping list creation
        context_id = str(uuid.uuid4())[:8]
        log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]"
        
        goal = DietaryGoal.objects.get(id=goal_id)
        goal.status = DietaryGoal.StatusChoices.PROCESSING
        goal.save(update_fields=['status'])
        logger.info(f"{log_prefix} Processing dietary goal {goal_id} for {goal.num_days} days")

        # Get shop URL for Gemini to browse
        shop_url = None
        if goal.shop:
            try:
                shop_url = ScraperService._get_shop_urls(goal.shop, goal.country)[0]
                logger.info(f"{log_prefix} Shop URL for Gemini browsing: {shop_url}")
            except Exception as e:
                logger.warning(f"{log_prefix} Could not get shop URL: {e}")
        
        # TWO LLM CALLS - Step 1: Meal plan, Step 2: Shopping list with prices
        # Split into two calls to avoid 8192 token limit truncation
        llm_service = GeminiService()
        user_prompt = _build_protocol_prompt(goal)
        logger.info(f"{log_prefix} Calling Gemini (2-step process: meal plan + shopping list)")

        llm_result = llm_service.generate_complete_plan_with_shopping_list(
            user_prompt=user_prompt,
            shop_url=shop_url,
            goal=goal
        )
        
        llm_response = llm_result['response']
        days = llm_response.get('days', [])
        shopping_list_from_llm = llm_response.get('shopping_list', [])
        total_cost_from_llm = llm_response.get('total_cost')
        
        total_meals = sum(
            len([m for m in [day.get('breakfast'), day.get('lunch'), day.get('dinner')] if m]) +
            len(day.get('small_meals', [])) + len(day.get('snacks', []))
            for day in days
        )
        logger.info(f"{log_prefix} Gemini generated {len(days)} days with {total_meals} meals and {len(shopping_list_from_llm)} shopping list items")
        
        # Transform days to standard format
        logger.info(f"{log_prefix} Transforming days to standard format")
        transformed_days = transform_days_to_new_format(days, goal)
        
        # Backend validation only - validate quantities and enhance with database prices where available
        logger.info(f"{log_prefix} Validating shopping list and enhancing with database prices")
        validated_shopping_list = []
        total_sum = Decimal('0')
        matched_count = 0
        estimated_count = 0
        
        for item in shopping_list_from_llm:
            # Validate quantities
            validated_item = validate_shopping_item(
                item, 
                num_days=goal.num_days, 
                context_id=context_id, 
                goal_id=goal_id
            )
            
            # Enhance with database price matching if available (for better package info)
            ingredient_name = validated_item.get('ingredient', '')
            if goal.shop:
                matched_product = ScraperService.match_ingredient_price(
                    ingredient_name,
                    goal.shop,
                    goal.country
                )
                if matched_product:
                    # Use database match for better package info and price validation
                    base_price = float(matched_product.get('price'))
                    validated_item['product_unit'] = matched_product.get('unit', validated_item.get('product_unit', ''))
                    validated_item['package_size'] = matched_product.get('package_size') or validated_item.get('package_size')
                    validated_item['matched_product_name'] = matched_product.get('display_name', validated_item.get('matched_product_name', ingredient_name))
                    validated_item['currency'] = matched_product.get('currency', validated_item.get('currency', goal.currency))
                    validated_item['price_type'] = matched_product.get('price_type', validated_item.get('price_type', 'REGULAR'))
                    
                    if matched_product.get('original_price'):
                        validated_item['original_price'] = float(matched_product.get('original_price'))
                    if matched_product.get('discount_percentage') is not None:
                        validated_item['discount_percentage'] = matched_product.get('discount_percentage')
                    
                    # Convert to purchasable units if needed
                    validated_item = convert_requirement_to_purchasable_units(
                        validated_item, matched_product, context_id=context_id, goal_id=goal_id
                    )
                    
                    # Recalculate price with package-aware logic
                    validated_item['price'] = base_price
                    calculated_price = calculate_package_aware_price(validated_item, context_id, goal_id)
                    
                    if calculated_price:
                        validated_item['price_total'] = float(calculated_price)
                        validated_item['price'] = float(calculated_price)
                        validated_item['estimated'] = False
                        validated_item['price_source'] = 'leaflet_offer'
                        total_sum += calculated_price
                        matched_count += 1
                    else:
                        # Use LLM price if calculation fails
                        llm_price = validated_item.get('price_total') or validated_item.get('price')
                        if llm_price:
                            validated_item['price_total'] = float(llm_price)
                            validated_item['price'] = float(llm_price)
                            total_sum += Decimal(str(llm_price))
                        else:
                            validated_item['price_total'] = base_price
                            validated_item['price'] = base_price
                            total_sum += Decimal(str(base_price))
                        validated_item['estimated'] = True
                        validated_item['price_source'] = 'leaflet_offer_estimated_quantity'
                        matched_count += 1
                else:
                    # No database match - use LLM-provided price
                    llm_price = validated_item.get('price_total') or validated_item.get('price')
                    if llm_price:
                        validated_item['price_total'] = float(llm_price)
                        validated_item['price'] = float(llm_price)
                        total_sum += Decimal(str(llm_price))
                        estimated_count += 1
                        validated_item['estimated'] = validated_item.get('estimated', True)
                        validated_item['price_source'] = validated_item.get('price_source', 'llm_from_shop_url')
                    else:
                        validated_item['price'] = None
                        validated_item['price_total'] = None
                        validated_item['estimated'] = True
                        validated_item['price_source'] = 'not_found'
            else:
                # No shop specified - use LLM prices as-is
                llm_price = validated_item.get('price_total') or validated_item.get('price')
                if llm_price:
                    validated_item['price_total'] = float(llm_price)
                    validated_item['price'] = float(llm_price)
                    total_sum += Decimal(str(llm_price))
                validated_item['estimated'] = validated_item.get('estimated', True)
            
            validated_shopping_list.append(validated_item)
        
        # Use calculated total (prefer our calculation over LLM)
        final_total = total_sum if total_sum > 0 else (Decimal(str(total_cost_from_llm)) if total_cost_from_llm else Decimal('0'))
        
        # Warn if totals differ significantly
        if total_cost_from_llm and total_sum > 0:
            diff_percent = abs(float(total_cost_from_llm) - float(total_sum)) / float(total_cost_from_llm) * 100
            if diff_percent > 20:
                logger.warning(
                    f"{log_prefix} Total cost mismatch: LLM={total_cost_from_llm} {goal.currency}, "
                    f"Calculated={total_sum} {goal.currency} ({diff_percent:.1f}% difference)"
                )
        
        # Create DietaryPlan
        plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            days=transformed_days,
            shopping_list=validated_shopping_list,
            total_price=final_total,
            currency=goal.currency,
            llm_model_used=llm_result.get('model'),
            llm_input_tokens=llm_result.get('input_tokens'),
            llm_output_tokens=llm_result.get('output_tokens'),
            llm_total_tokens=llm_result.get('total_tokens'),
            llm_cost_usd=llm_result.get('cost_usd')
        )
        
        # Mark as COMPLETED - meal plan successfully generated and rendered
        # This is when the user should be considered "charged" (fulfillment complete)
        goal.status = DietaryGoal.StatusChoices.COMPLETED
        goal.completed_at = timezone.now()
        goal.save(update_fields=['status', 'completed_at'])
        
        # Note: Shopify already charged the user when payment was received (webhook)
        # We mark as COMPLETED here to indicate fulfillment is complete
        # If this step fails, the order remains unfulfilled and can be refunded
        if goal.shopify_order_id:
            logger.info(
                f"{log_prefix} Meal plan completed for order {goal.shopify_order_id}. "
                f"Order fulfillment complete - user has received their meal plan."
            )
        
        logger.info(
            f"{log_prefix} Successfully created plan {plan.id} with {len(validated_shopping_list)} items, "
            f"total: {final_total} {goal.currency} (matched: {matched_count}, estimated: {estimated_count})"
        )
        return {'status': 'success', 'plan_id': plan.id}

    except Exception as exc:
        logger.error(f"Task failed for goal {goal_id}: {str(exc)}", exc_info=True)
        try:
            goal = DietaryGoal.objects.get(id=goal_id)
            goal.error_message = f"Meal plan generation failed: {str(exc)}"
            if goal.status == DietaryGoal.StatusChoices.PAYMENT_PENDING:
                goal.status = DietaryGoal.StatusChoices.REFUND_ELIGIBLE
                logger.warning(
                    f"Goal {goal_id} failed after payment - marked as REFUND_ELIGIBLE. "
                    f"Order {goal.shopify_order_id} should be refunded."
                )
            else:
                goal.status = DietaryGoal.StatusChoices.FAILED
            goal.save(update_fields=['status', 'error_message'])
        except Exception as inner_exc:
            logger.error(f"Failed to update goal {goal_id} status: {inner_exc}")

        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


# =============================================================================
# SCRAPING & FRESHNESS LIFECYCLE TASKS (Phase 3)
# =============================================================================

@shared_task(bind=True, max_retries=3)
def scrape_store_task(self, shop_code: str) -> Dict[str, Any]:
    """
    Proactive scraping task triggered by Celery Beat schedule.

    Scrapes a single store, stores results in LeafletOffer,
    and creates a ScrapeRun audit record.
    """
    import time
    from datetime import timedelta
    from .models import LeafletOffer, GroceryStore, ScrapeRun

    started = time.time()
    log_prefix = f"[SCRAPE:{shop_code}]"

    try:
        store = GroceryStore.objects.filter(code=shop_code, is_active=True).first()
        if not store:
            logger.warning(f"{log_prefix} Store not found or inactive, skipping")
            return {'status': 'skipped', 'reason': 'store_not_found'}

        scrape_run = ScrapeRun.objects.create(
            store=store,
            status=ScrapeRun.Status.RUNNING,
            method=ScrapeRun.Method.HYBRID,
        )

        logger.info(f"{log_prefix} Starting scrape (run {scrape_run.pk})")

        scraper = ScraperService.get_scraper(shop_code)
        products = scraper.scrape()

        if not products:
            logger.warning(f"{log_prefix} Structured scraping returned 0 products")

        # Store in LeafletOffer (same pattern as existing scrape_and_store)
        from .scrapers.utils import normalize_ingredient_name
        now = timezone.now()
        ttl_hours = store.default_price_ttl_hours or 168
        expires_at = now + timedelta(hours=ttl_hours)
        country = store.country
        currency = store.currency

        created = 0
        updated = 0
        for product in products:
            ingredient_name = normalize_ingredient_name(
                product.get('ingredient_name', product.get('display_name', ''))
            )
            if not ingredient_name:
                continue

            price = product.get('price')
            if not price or float(price) <= 0:
                continue

            _, was_created = LeafletOffer.objects.update_or_create(
                shop=shop_code,
                country=country,
                ingredient_name=ingredient_name,
                defaults={
                    'display_name': product.get('display_name', ingredient_name),
                    'price': price,
                    'currency': product.get('currency', currency),
                    'unit': product.get('unit', ''),
                    'price_type': product.get('price_type', 'REGULAR'),
                    'original_price': product.get('original_price'),
                    'discount_percentage': product.get('discount_percentage'),
                    'source_url': product.get('source_url', ''),
                    'expires_at': expires_at,
                    'freshness_state': 'fresh',
                    'stale_at': None,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        duration = time.time() - started
        scrape_run.status = ScrapeRun.Status.COMPLETED
        scrape_run.completed_at = timezone.now()
        scrape_run.duration_seconds = duration
        scrape_run.products_found = len(products)
        scrape_run.products_created = created
        scrape_run.products_updated = updated
        scrape_run.prices_recorded = created + updated
        scrape_run.save()

        logger.info(
            f"{log_prefix} Complete: {len(products)} found, {created} created, "
            f"{updated} updated in {duration:.1f}s"
        )
        return {
            'status': 'success',
            'products_found': len(products),
            'created': created,
            'updated': updated,
            'duration_seconds': round(duration, 1),
        }

    except Exception as exc:
        duration = time.time() - started
        logger.error(f"{log_prefix} Failed: {exc}", exc_info=True)

        try:
            if 'scrape_run' in locals():
                scrape_run.status = ScrapeRun.Status.FAILED
                scrape_run.completed_at = timezone.now()
                scrape_run.duration_seconds = duration
                scrape_run.error_log = str(exc)[:2000]
                scrape_run.errors_count = 1
                scrape_run.save()
        except Exception:
            pass

        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task
def update_freshness_states_task() -> Dict[str, Any]:
    """
    Transition LeafletOffer freshness states based on FRESHNESS_CONFIG TTLs.

    FRESH → STALE (past fresh_hours)
    STALE → EXPIRED (past stale_hours, set via expires_at)
    """
    from datetime import timedelta
    from django.conf import settings as django_settings
    from .models import LeafletOffer

    freshness_config = getattr(django_settings, 'FRESHNESS_CONFIG', {})
    now = timezone.now()
    total_staled = 0
    total_expired = 0

    for shop_code, config in freshness_config.items():
        fresh_hours = config.get('fresh_hours', 72)
        stale_cutoff = now - timedelta(hours=fresh_hours)

        # FRESH → STALE
        staled = LeafletOffer.objects.filter(
            shop=shop_code,
            freshness_state='fresh',
            scraped_at__lt=stale_cutoff,
        ).update(freshness_state='stale', stale_at=now)
        total_staled += staled

        # STALE → EXPIRED (using expires_at which is already set)
        expired = LeafletOffer.objects.filter(
            shop=shop_code,
            freshness_state='stale',
            expires_at__lt=now,
        ).update(freshness_state='expired')
        total_expired += expired

    if total_staled or total_expired:
        logger.info(f"Freshness update: {total_staled} → stale, {total_expired} → expired")

    return {'staled': total_staled, 'expired': total_expired}


@shared_task
def archive_expired_offers_task() -> Dict[str, Any]:
    """
    Delete expired LeafletOffer rows older than 30 days.
    Price history is preserved via PriceRecord (when populated).
    """
    from datetime import timedelta
    from .models import LeafletOffer

    cutoff = timezone.now() - timedelta(days=30)
    count, _ = LeafletOffer.objects.filter(
        freshness_state='expired',
        scraped_at__lt=cutoff,
    ).delete()

    if count:
        logger.info(f"Archived {count} expired offers older than 30 days")

    return {'archived': count}


@shared_task
def scraper_health_check_task() -> Dict[str, Any]:
    """
    Daily health check across all stores.
    Logs warnings and sends Slack alert if any store is stale or broken.
    """
    from datetime import timedelta
    from .models import GroceryStore, LeafletOffer, ScrapeRun

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    alerts = []

    stores = GroceryStore.objects.filter(is_active=True)
    for store in stores:
        # Check 1: successful scrape in last 48h
        latest = ScrapeRun.objects.filter(
            store=store, status='COMPLETED',
        ).order_by('-started_at').first()

        if not latest:
            alerts.append(f"CRITICAL: {store.code} has NEVER been scraped")
        elif (now - latest.started_at).total_seconds() > 48 * 3600:
            hours_ago = (now - latest.started_at).total_seconds() / 3600
            alerts.append(f"STALE: {store.code} last scraped {hours_ago:.0f}h ago")

        # Check 2: product count drop
        last_two = list(ScrapeRun.objects.filter(
            store=store, status__in=['COMPLETED', 'PARTIAL'],
        ).order_by('-started_at')[:2])

        if len(last_two) == 2 and last_two[1].products_found > 0:
            ratio = last_two[0].products_found / last_two[1].products_found
            if ratio < 0.3:
                alerts.append(
                    f"DROP: {store.code} products dropped from "
                    f"{last_two[1].products_found} to {last_two[0].products_found}"
                )

        # Check 3: weekly LLM cost spike
        from django.db.models import Sum as _Sum
        weekly_cost = ScrapeRun.objects.filter(
            store=store, started_at__gte=week_ago,
        ).aggregate(total=_Sum('llm_cost_usd'))['total'] or 0
        if float(weekly_cost) > 1.0:
            alerts.append(f"COST: {store.code} weekly LLM cost ${weekly_cost:.2f}")

    if alerts:
        alert_text = "Scraper Health Check:\n" + "\n".join(f"  - {a}" for a in alerts)
        logger.warning(alert_text)
        _send_slack_alert(alert_text)
    else:
        logger.info("Scraper health check: all stores healthy")

    return {'alerts': alerts, 'stores_checked': stores.count()}


def _send_slack_alert(message: str) -> None:
    """Best-effort Slack alert. Fails silently if Slack is not configured."""
    import os
    try:
        token = os.environ.get('SLACK_BOT_TOKEN')
        channel = os.environ.get('SLACK_ALERT_CHANNEL')
        if not token or not channel:
            return

        from slack_sdk import WebClient
        client = WebClient(token=token)
        client.chat_postMessage(channel=channel, text=message)
        logger.info("Slack alert sent")
    except Exception as e:
        logger.warning(f"Failed to send Slack alert: {e}")


# =============================================================================
# CATALOG-CONSTRAINED TASK (Phase 4)
# =============================================================================
# New flow: real catalog → constrained LLM → DB-only prices
# The old process_dietary_goal_task is kept for rollback safety.
# Set CATALOG_CONSTRAINED_GENERATION=True in settings to enable.

@shared_task(bind=True, max_retries=3)
def process_dietary_goal_catalog_task(self, goal_id: int) -> Dict[str, Any]:
    """
    Catalog-constrained meal plan generation.

    Flow:
    1. Load real product catalog from DB (LeafletOffer)
    2. Send catalog to Gemini — LLM uses ONLY those products
    3. Resolve all prices from DB — zero LLM price fabrication
    4. Every price carries its source label for user transparency
    """
    try:
        context_id = str(uuid.uuid4())[:8]
        log_prefix = f"[CATALOG:{goal_id}:{context_id}]"

        goal = DietaryGoal.objects.get(id=goal_id)
        goal.status = DietaryGoal.StatusChoices.PROCESSING
        goal.save(update_fields=['status'])
        logger.info(f"{log_prefix} Starting catalog-constrained generation for {goal.num_days} days")

        # ── Phase 1: Build catalog ──
        from diet_planner.services.catalog import CatalogService
        catalog_service = CatalogService()
        catalog = catalog_service.build_catalog_for_prompt(goal)
        catalog_text = catalog_service.build_compact_prompt_text(catalog, goal)

        if catalog['total_products'] < 10:
            logger.warning(
                f"{log_prefix} Very small catalog ({catalog['total_products']} products). "
                f"Falling back to old flow."
            )
            return process_dietary_goal_task(goal_id)

        logger.info(
            f"{log_prefix} Catalog ready: {catalog['total_products']} products, "
            f"{len(catalog['pantry_staples'])} pantry staples"
        )

        # ── Phase 2: Constrained LLM generation (single call) ──
        llm_service = GeminiService()
        user_prompt = _build_protocol_prompt(goal)
        llm_result = llm_service.generate_catalog_constrained_plan(
            user_prompt=user_prompt,
            catalog_text=catalog_text,
            goal=goal,
        )

        llm_response = llm_result['response']
        days = llm_response.get('days', [])
        logger.info(f"{log_prefix} LLM generated {len(days)} days")

        # Transform days to standard format
        transformed_days = transform_days_to_new_format(days, goal)

        # ── Phase 3: Aggregate ingredients into shopping list ──
        shopping_items = aggregate_ingredients_from_meals(
            transformed_days, context_id=context_id, goal_id=goal_id
        )

        # Carry catalog_id and pantry flags from LLM output into aggregated items
        catalog_id_map = _build_catalog_id_map(days)
        for item in shopping_items:
            ingredient_lower = item.get('ingredient', '').lower().strip()
            if ingredient_lower in catalog_id_map:
                item['catalog_id'] = catalog_id_map[ingredient_lower].get('catalog_id')
                item['pantry'] = catalog_id_map[ingredient_lower].get('pantry', False)

        # Validate quantities
        for i, item in enumerate(shopping_items):
            shopping_items[i] = validate_shopping_item(
                item, num_days=goal.num_days, context_id=context_id, goal_id=goal_id
            )

        # ── Phase 4: Resolve prices from DB ──
        store_mode = getattr(goal, 'store_mode', 'single')
        cross_store_data = None

        if store_mode in ('mix_cost', 'mix_trips'):
            from diet_planner.services.cross_store_optimizer import CrossStoreOptimizer
            optimizer = CrossStoreOptimizer(goal)
            cross_store_data = optimizer.optimize(shopping_items, strategy=store_mode)
            # Flatten all items from all stores for storage
            resolved_list = []
            for store_list in cross_store_data['shopping_lists_by_store']:
                for item in store_list['items']:
                    item['assigned_store'] = store_list['store']
                    item['assigned_store_name'] = store_list['store_name']
                    resolved_list.append(item)
            total_sum = Decimal(str(cross_store_data['total_price']))
            priced_count = sum(1 for i in resolved_list if i.get('price_total'))
        else:
            from diet_planner.services.price_resolver import PriceResolver
            resolver = PriceResolver(goal)
            resolved_list = resolver.resolve_shopping_list(shopping_items)
            total_sum = Decimal('0')
            priced_count = 0
            for item in resolved_list:
                if item.get('price_total'):
                    total_sum += Decimal(str(item['price_total']))
                    priced_count += 1

        unpriced_count = len(resolved_list) - priced_count
        unpriced_ratio = unpriced_count / max(len(resolved_list), 1)

        if unpriced_ratio > 0.30:
            logger.warning(
                f"{log_prefix} High unpriced ratio: {unpriced_count}/{len(resolved_list)} "
                f"({unpriced_ratio:.0%}) items without price"
            )

        # Build shopping_list payload (include cross-store metadata if applicable)
        shopping_list_payload = resolved_list
        if cross_store_data:
            shopping_list_payload = {
                'items': resolved_list,
                'by_store': cross_store_data['shopping_lists_by_store'],
                'savings_vs_single': cross_store_data['savings_vs_single'],
                'best_single_store': cross_store_data['best_single_store'],
                'best_single_store_total': cross_store_data['best_single_store_total'],
                'num_stores': cross_store_data['num_stores'],
                'strategy': cross_store_data['strategy'],
            }

        # ── Store results ──
        plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            days=transformed_days,
            shopping_list=shopping_list_payload,
            total_price=total_sum,
            currency=goal.currency,
            llm_model_used=llm_result.get('model'),
            llm_input_tokens=llm_result.get('input_tokens'),
            llm_output_tokens=llm_result.get('output_tokens'),
            llm_total_tokens=llm_result.get('total_tokens'),
            llm_cost_usd=llm_result.get('cost_usd'),
        )

        goal.status = DietaryGoal.StatusChoices.COMPLETED
        goal.completed_at = timezone.now()
        goal.save(update_fields=['status', 'completed_at'])

        if goal.shopify_order_id:
            logger.info(f"{log_prefix} Order {goal.shopify_order_id} fulfillment complete")

        logger.info(
            f"{log_prefix} Plan {plan.id} created: {len(resolved_list)} items, "
            f"{priced_count} priced, total={total_sum} {goal.currency}, "
            f"LLM cost=${llm_result.get('cost_usd', 0)}"
        )
        return {'status': 'success', 'plan_id': plan.id}

    except Exception as exc:
        logger.error(f"Catalog task failed for goal {goal_id}: {str(exc)}", exc_info=True)
        try:
            goal = DietaryGoal.objects.get(id=goal_id)
            goal.error_message = f"Meal plan generation failed: {str(exc)}"
            if goal.status == DietaryGoal.StatusChoices.PAYMENT_PENDING:
                goal.status = DietaryGoal.StatusChoices.REFUND_ELIGIBLE
                logger.warning(f"Goal {goal_id} marked REFUND_ELIGIBLE (order {goal.shopify_order_id})")
            else:
                goal.status = DietaryGoal.StatusChoices.FAILED
            goal.save(update_fields=['status', 'error_message'])
        except Exception as inner_exc:
            logger.error(f"Failed to update goal {goal_id} status: {inner_exc}")

        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))


def _build_catalog_id_map(days: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Extract catalog_id and pantry flags from LLM-generated days.
    Returns a map of normalized ingredient name -> {catalog_id, pantry}.
    """
    result = {}
    for day in days:
        for meal_type in ['breakfast', 'lunch', 'dinner']:
            meal = day.get(meal_type)
            if meal and isinstance(meal, dict):
                for ing in meal.get('ingredients', []):
                    if isinstance(ing, dict):
                        name = (ing.get('name') or '').lower().strip()
                        if name:
                            result[name] = {
                                'catalog_id': ing.get('catalog_id'),
                                'pantry': ing.get('pantry', False),
                            }
        for meal_type in ['small_meals', 'snacks']:
            meals = day.get(meal_type, [])
            if isinstance(meals, list):
                for meal in meals:
                    if isinstance(meal, dict):
                        for ing in meal.get('ingredients', []):
                            if isinstance(ing, dict):
                                name = (ing.get('name') or '').lower().strip()
                                if name:
                                    result[name] = {
                                        'catalog_id': ing.get('catalog_id'),
                                        'pantry': ing.get('pantry', False),
                                    }
    return result


def _find_matching_product(
    ingredient_name: str,
    available_ingredients: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Find the best matching product for an ingredient from available shop products.

    Uses simple fuzzy matching based on ingredient name containment.

    Args:
        ingredient_name: Name of the ingredient to match
        available_ingredients: List of available products from shop scraper

    Returns:
        Matching product dict or None if no match found
    """
    if not ingredient_name or not available_ingredients:
        return None

    name_lower = ingredient_name.lower().strip()

    # First pass: exact match on ingredient_name
    for product in available_ingredients:
        product_name = (product.get('ingredient_name') or product.get('display_name') or '').lower()
        if product_name == name_lower:
            return product

    # Second pass: substring match (ingredient in product or product in ingredient)
    for product in available_ingredients:
        product_name = (product.get('ingredient_name') or product.get('display_name') or '').lower()
        if name_lower in product_name or product_name in name_lower:
            return product

    # Third pass: word-based matching (any word matches)
    ingredient_words = set(name_lower.split())
    best_match = None
    best_score = 0

    for product in available_ingredients:
        product_name = (product.get('ingredient_name') or product.get('display_name') or '').lower()
        product_words = set(product_name.split())

        # Count matching words
        matches = len(ingredient_words & product_words)
        if matches > best_score and matches >= 1:
            best_score = matches
            best_match = product

    return best_match


def generate_mock_llm_response() -> Dict[str, Any]:
    """
    Placeholder function for LLM response.
    Replace this with actual LLM API integration.
    """
    return {
        'days': [
            {
                'day_number': 1,
                'breakfast': {
                    'name': 'Greek Yogurt with Berries',
                    'description': 'Protein-rich breakfast option',
                    'ingredients': ['greek yogurt', 'mixed berries', 'honey'],
                    'preparation_time': 5,
                    'nutritional_info': {
                        'calories': 200,
                        'protein': '15g',
                        'carbs': '25g',
                        'fat': '5g'
                    }
                },
                'lunch': {
                    'name': 'Grilled Chicken Salad',
                    'description': 'Healthy salad with grilled chicken breast',
                    'ingredients': ['chicken breast', 'lettuce', 'tomatoes', 'cucumber', 'olive oil'],
                    'preparation_time': 30,
                    'nutritional_info': {
                        'calories': 450,
                        'protein': '35g',
                        'carbs': '15g',
                        'fat': '25g'
                    }
                },
                'dinner': {
                    'name': 'Baked Salmon with Vegetables',
                    'description': 'Nutritious dinner with omega-3 rich salmon',
                    'ingredients': ['salmon fillet', 'broccoli', 'sweet potato', 'lemon', 'olive oil'],
                    'preparation_time': 35,
                    'nutritional_info': {
                        'calories': 500,
                        'protein': '40g',
                        'carbs': '30g',
                        'fat': '22g'
                    }
                },
                'small_meals': [
                    {
                        'name': 'Protein Smoothie',
                        'description': 'Quick protein boost',
                        'ingredients': ['protein powder', 'banana', 'almond milk'],
                        'preparation_time': 3,
                        'nutritional_info': {
                            'calories': 180,
                            'protein': '20g',
                            'carbs': '15g',
                            'fat': '3g'
                        }
                    }
                ],
                'snacks': [
                    {
                        'name': 'Apple with Almonds',
                        'description': 'Healthy afternoon snack',
                        'ingredients': ['apple', 'almonds'],
                        'preparation_time': 2,
                        'nutritional_info': {
                            'calories': 150,
                            'protein': '5g',
                            'carbs': '20g',
                            'fat': '8g'
                        }
                    }
                ]
            }
        ],
        'shopping_list': [
            {
                'ingredient': 'chicken breast',
                'quantity': '500',
                'unit': 'g',
                'notes': 'Fresh, skinless'
            },
            {
                'ingredient': 'lettuce',
                'quantity': '1',
                'unit': 'head',
                'notes': None
            },
            {
                'ingredient': 'tomatoes',
                'quantity': '300',
                'unit': 'g',
                'notes': None
            },
            {
                'ingredient': 'tofu',
                'quantity': '400',
                'unit': 'g',
                'notes': 'Firm tofu'
            },
            {
                'ingredient': 'broccoli',
                'quantity': '500',
                'unit': 'g',
                'notes': None
            }
        ]
    }


@shared_task(bind=True, max_retries=1, default_retry_delay=30, time_limit=180, soft_time_limit=150)
def optimize_plan_discounts_task(self, goal_id: int, shops: Optional[List[str]] = None, force_scrape: bool = False) -> Dict[str, Any]:
    """
    Post-generation discount optimization.

    Loads the existing plan, fetches currently discounted products from one or
    more shops, and asks the LLM to suggest ingredient swaps that save money.
    Stores suggestions on DietaryPlan.discount_optimization for user review.

    Args:
        goal_id: DietaryGoal ID.
        shops: Optional list of shop codes to query. Defaults to all active stores
               for the goal's country (multi-shop sweep). Pass a single-element
               list to restrict to one shop.
        force_scrape: When True, ignore cached leaflet data and re-scrape every
                      target shop. Use sparingly — this re-runs the LLM extraction.
    """
    try:
        from diet_planner.models import LeafletOffer, GroceryStore
        goal = DietaryGoal.objects.get(id=goal_id)
        plan = goal.dietary_plan

        country = goal.country
        active_shop_codes = list(
            GroceryStore.objects.filter(country=country, is_active=True)
            .values_list('code', flat=True)
        )

        if shops:
            target_shops = [s for s in shops if s in active_shop_codes]
            if not target_shops:
                target_shops = [goal.shop] if goal.shop in active_shop_codes else active_shop_codes
        else:
            target_shops = active_shop_codes or [goal.shop]

        now = timezone.now()
        scrape_attempted_at = None
        for shop_code in target_shops:
            if not force_scrape and ScraperService.is_cache_valid(shop_code, country):
                continue
            scrape_attempted_at = timezone.now().isoformat()
            logger.info(
                f"[optimize_plan_discounts] No fresh cache for {shop_code}/{country}, "
                f"running inline scrape (goal={goal_id})"
            )
            try:
                scrape_store_task(shop_code)
            except Exception as scrape_exc:
                logger.warning(
                    f"[optimize_plan_discounts] Inline scrape failed for {shop_code}: {scrape_exc}"
                )

        now = timezone.now()
        # Include ALL fresh leaflet offers, not just rows pre-tagged DISCOUNTED.
        # kupi.cz renders prices in image overlays, so most rows arrive without
        # an explicit original_price and can't be reliably labelled DISCOUNTED
        # at scrape time. The downstream LLM compares each candidate's price
        # against the user's current shopping-list price and only proposes
        # swaps where the per-unit cost actually drops — let it judge savings.
        # We still surface BS4-detected original_price/discount_percentage to
        # the LLM when present so it has the stronger signal.
        leaflet_offers = LeafletOffer.objects.filter(
            shop__in=target_shops,
            country=country,
            expires_at__gt=now,
            price__gt=0,
        ).exclude(price_type='LLM_ESTIMATED').order_by('-discount_percentage', '-scraped_at')[:150]

        if not leaflet_offers.exists():
            plan.discount_optimization = {
                'swaps': [],
                'total_saving': 0,
                'message': 'no_discounts',
                'shops_queried': target_shops,
                'scrape_attempted_at': scrape_attempted_at,
            }
            plan.save(update_fields=['discount_optimization'])
            return {'status': 'no_discounts', 'goal_id': goal_id, 'shops_queried': target_shops}

        lines = []
        for offer in leaflet_offers:
            disc_pct = f" (-{offer.discount_percentage}%)" if offer.discount_percentage else ""
            orig = f" (původně {offer.original_price} {goal.currency})" if offer.original_price else ""
            lines.append(
                f"#{offer.id} [{offer.shop}] {offer.ingredient_name} — {offer.price} {goal.currency}{disc_pct}{orig}"
            )
        discounted_text = "\n".join(lines)

        shopping_list = plan.shopping_list
        if isinstance(shopping_list, dict):
            items_for_llm = shopping_list.get('items', [])
        else:
            items_for_llm = shopping_list or []

        llm_service = GeminiService()
        result = llm_service.generate_discount_optimization(
            current_plan_days=plan.days,
            current_shopping_list=items_for_llm,
            discounted_products=discounted_text,
            goal=goal,
        )

        optimization = result['response']
        optimization['llm_cost_usd'] = str(result.get('cost_usd', 0))
        optimization['generated_at'] = now.isoformat()
        optimization['shops_queried'] = target_shops
        if scrape_attempted_at:
            optimization['scrape_attempted_at'] = scrape_attempted_at

        plan.discount_optimization = optimization
        plan.save(update_fields=['discount_optimization'])

        logger.info(
            f"Discount optimization for goal {goal_id} across shops {target_shops}: "
            f"{len(optimization.get('swaps', []))} swaps, "
            f"saving {optimization.get('total_saving', 0)} {goal.currency}"
        )
        return {'status': 'success', 'goal_id': goal_id, 'swaps': len(optimization.get('swaps', [])), 'shops_queried': target_shops}

    except Exception as exc:
        logger.error(f"Discount optimization failed for goal {goal_id}: {exc}", exc_info=True)
        raise self.retry(exc=exc)
