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

from celery import shared_task
from django.utils import timezone
from typing import Dict, Any, List, Optional, Tuple
import json
import logging
import re
import uuid
from decimal import Decimal

from .models import DietaryGoal, DietaryPlan
from .schemas import DietaryPlanResponse, MealIdea, ShoppingListItem
from .llm_service import OpenAIService
from .scrapers.scraper_service import ScraperService

logger = logging.getLogger(__name__)


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
    """
    if not days_data or not isinstance(days_data, list):
        return []
    
    transformed_days = []
    wants_breakfast = getattr(goal, 'breakfast', True)
    wants_lunch = getattr(goal, 'lunch', True)
    wants_dinner = getattr(goal, 'dinner', True)
    
    for day in days_data:
        transformed_day = {
            'day_number': day.get('day_number', len(transformed_days) + 1),
            'small_meals': day.get('small_meals', []),
            'snacks': day.get('snacks', []),
        }
        
        if 'breakfast' in day or 'lunch' in day or 'dinner' in day:
            if wants_breakfast: transformed_day['breakfast'] = day.get('breakfast')
            if wants_lunch: transformed_day['lunch'] = day.get('lunch')
            if wants_dinner: transformed_day['dinner'] = day.get('dinner')
        elif 'main_courses' in day:
            main_courses = day['main_courses']
            idx = 0
            if wants_breakfast and idx < len(main_courses):
                transformed_day['breakfast'] = main_courses[idx]; idx += 1
            if wants_lunch and idx < len(main_courses):
                transformed_day['lunch'] = main_courses[idx]; idx += 1
            if wants_dinner and idx < len(main_courses):
                transformed_day['dinner'] = main_courses[idx]; idx += 1
        
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
        1. Convert required quantity to base unit (g/ml/ks)
        2. Convert package size to base unit
        3. Calculate packages needed: ceil(required / package_size)
        4. Total price = packages * price_per_package

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
        # No package size specified - assume per-unit pricing
        # For kg/l, assume price is per kg/l (1000g/ml)
        # For ks/g/ml, assume price is per unit
        if off_unit in ['kg', 'l']:
            pkg_base = Decimal('1000')
        elif off_unit in ['g', 'ml']:
            pkg_base = Decimal('1')
        else:
            pkg_base = Decimal('1')
        if log_prefix:
            logger.debug(f"{log_prefix} DETAIL: No package_size specified, assuming pkg_base={pkg_base} for unit '{off_unit}'")

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

    # Sanity check on total price (max 1000 per item for reasonable meal plan)
    if total_price > Decimal('1000'):
        warning_msg = (
            f"Price calculation: Excessive price ({total_price}) for '{ingredient}', "
            f"something may be wrong with units or quantities"
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
    Main Celery task for processing a dietary goal and generating a meal plan.

    This task orchestrates the complete flow:
    1. Fetch available ingredients from shop scraper
    2. Call LLM to generate meal plan (days with meals and ingredients)
    3. Aggregate ingredients from all meals into shopping list (backend logic)
    4. Validate quantities to catch LLM errors
    5. Match ingredients with shop products
    6. Calculate prices using package-aware logic
    7. Create DietaryPlan with all data

    Args:
        goal_id: ID of the DietaryGoal to process

    Returns:
        Dict with 'status' and 'plan_id' on success

    Debugging:
        - Check logs for "Shopping list validation" entries
        - Check logs for "Price calculation" entries
        - Look for "Aggregated X unique ingredients" log
    """
    try:
        # Generate unique context ID for tracing this shopping list creation
        context_id = str(uuid.uuid4())[:8]
        log_prefix = f"[SHOPPING_LIST:{goal_id}:{context_id}]"
        
        goal = DietaryGoal.objects.get(id=goal_id)
        goal.status = DietaryGoal.StatusChoices.PROCESSING
        goal.save(update_fields=['status'])
        logger.info(f"{log_prefix} Processing dietary goal {goal_id} for {goal.num_days} days")

        # Step 1: Fetch available ingredients from shop
        available_ingredients = []
        if goal.shop:
            logger.info(f"{log_prefix} Step 1: Fetching ingredients from {goal.shop} ({goal.country})")
            available_ingredients = ScraperService.get_available_ingredients(
                goal.shop, goal.country, force_refresh=True
            )
            logger.info(f"{log_prefix} Found {len(available_ingredients)} available ingredients")
            if available_ingredients:
                sample_ingredients = [ing.get('name', 'unknown') for ing in available_ingredients[:5]]
                logger.debug(f"{log_prefix} DETAIL: Sample ingredients: {sample_ingredients}")

        # Step 2: Generate meal plan via LLM
        llm_service = OpenAIService()
        logger.info(f"{log_prefix} Step 2: Calling LLM to generate meal plan")
        llm_result = llm_service.generate_dietary_plan(
            prompt_text=json.dumps(build_llm_prompt_json(goal, available_ingredients), ensure_ascii=False),
            language_code=goal.language_code
        )

        llm_response = llm_result['response']
        days = llm_response.get('days', [])
        total_meals = sum(
            len([m for m in [day.get('breakfast'), day.get('lunch'), day.get('dinner')] if m]) +
            len(day.get('small_meals', [])) + len(day.get('snacks', []))
            for day in days
        )
        logger.info(f"{log_prefix} LLM generated {len(days)} days with {total_meals} meals total")

        # Step 3: Transform days to standard format
        logger.info(f"{log_prefix} Step 3: Transforming days to standard format")
        transformed_days = transform_days_to_new_format(days, goal)
        logger.debug(f"{log_prefix} DETAIL: Transformed {len(transformed_days)} days")

        # Step 4: Aggregate ingredients from all meals (backend logic, not LLM)
        # This replaces trusting LLM's shopping_list with our own aggregation
        logger.info(f"{log_prefix} Step 4: Aggregating ingredients from all meals")
        shopping_list = aggregate_ingredients_from_meals(transformed_days, context_id, goal_id)
        logger.info(f"{log_prefix} Aggregated {len(shopping_list)} items for shopping list")

        # Step 5: Validate quantities to catch unreasonable values
        logger.info(f"{log_prefix} Step 5: Validating shopping list items")
        validated_shopping_list = []
        validation_adjustments = []
        for item in shopping_list:
            validated_item = validate_shopping_item(item, num_days=goal.num_days, context_id=context_id, goal_id=goal_id)
            if validated_item.get('validation_note'):
                validation_adjustments.append({
                    'ingredient': validated_item.get('ingredient'),
                    'note': validated_item.get('validation_note')
                })
            validated_shopping_list.append(validated_item)
        
        if validation_adjustments:
            logger.warning(f"{log_prefix} WARNING: {len(validation_adjustments)} items were adjusted during validation")
            for adj in validation_adjustments:
                logger.debug(f"{log_prefix} DETAIL: Validation adjustment - {adj['ingredient']}: {adj['note']}")

        # Step 6: Match with shop products and calculate prices
        # Use ScraperService.match_ingredient_price() which queries the database directly
        # and has better matching logic with multiple strategies
        logger.info(f"{log_prefix} Step 6: Matching prices for {len(validated_shopping_list)} items")
        total_sum = Decimal('0')
        matched_count = 0
        estimated_count = 0
        not_found_count = 0
        
        for item in validated_shopping_list:
            ingredient_name = item.get('ingredient', '')
            
            # Try to find matching product from database using improved matching
            logger.debug(f"{log_prefix} DETAIL: Matching '{ingredient_name}' in {goal.shop} ({goal.country})")
            matched_product = ScraperService.match_ingredient_price(
                ingredient_name,
                goal.shop,
                goal.country
            )

            if matched_product:
                # Update item with product info for price calculation
                # Store base price per package for calculation
                base_price = float(matched_product.get('price'))
                item['product_unit'] = matched_product.get('unit', '')
                item['package_size'] = matched_product.get('package_size')
                item['matched_product_name'] = matched_product.get('display_name', '')
                item['currency'] = matched_product.get('currency', goal.currency)
                item['price_type'] = matched_product.get('price_type', 'REGULAR')
                if matched_product.get('original_price'):
                    item['original_price'] = float(matched_product.get('original_price'))
                if matched_product.get('discount_percentage') is not None:
                    item['discount_percentage'] = matched_product.get('discount_percentage')
                item['estimated'] = False
                item['price_source'] = 'leaflet_offer'
                
                logger.debug(
                    f"{log_prefix} DETAIL: Matched '{ingredient_name}' → '{item['matched_product_name']}' "
                    f"({base_price} {item['currency']}, package: {item['package_size']}{item['product_unit']}, "
                    f"type: {item['price_type']})"
                )
                
                # Set base price for package-aware calculation
                item['price'] = base_price
                
                # Calculate price using package-aware logic (accounts for quantity needed)
                calculated_price = calculate_package_aware_price(item, context_id, goal_id)
                
                if calculated_price:
                    item['price_total'] = float(calculated_price)
                    item['price'] = float(calculated_price)  # Update to total calculated price for display
                    total_sum += calculated_price
                    matched_count += 1
                    logger.debug(
                        f"{log_prefix} DETAIL: '{ingredient_name}' final price: {calculated_price} {goal.currency} "
                        f"(from {base_price} base price)"
                    )
                else:
                    # If calculation fails but we have a base price from leaflet, use it as fallback
                    # This is better than LLM estimation since we have a real price
                    logger.warning(
                        f"{log_prefix} WARNING: Price calculation failed for '{ingredient_name}' "
                        f"(base: {base_price}), using base price as fallback"
                    )
                    item['price_total'] = base_price
                    item['price'] = base_price
                    total_sum += Decimal(str(base_price))
                    matched_count += 1
                    # Mark as estimated since we couldn't calculate the exact total for the quantity needed
                    item['estimated'] = True
                    item['price_source'] = 'leaflet_offer_estimated_quantity'
            else:
                # No match found in database - fallback to LLM price estimation
                logger.debug(f"{log_prefix} DETAIL: No price match in database for '{ingredient_name}', using LLM estimation")
                est = llm_service.estimate_product_price(
                    ingredient_name,
                    item.get('quantity'),
                    item.get('unit'),
                    goal.shop,
                    goal.country
                )
                if est:
                    item.update({
                        'price': float(est['price']),
                        'price_total': float(est['price']),
                        'currency': est.get('currency', goal.currency),
                        'matched_product_name': est.get('display_name', ingredient_name),
                        'estimated': True,
                        'price_source': 'llm_estimation_service',
                        'price_type': 'LLM_ESTIMATED',
                    })
                    total_sum += Decimal(str(est['price']))
                    estimated_count += 1
                    logger.debug(
                        f"{log_prefix} DETAIL: LLM estimated '{ingredient_name}': {est['price']} {est.get('currency', goal.currency)}"
                    )
                else:
                    item['price'] = None
                    item['price_total'] = None
                    item['price_source'] = 'not_found'
                    item['estimated'] = True
                    not_found_count += 1
                    logger.warning(f"{log_prefix} WARNING: Could not estimate price for '{ingredient_name}'")

        logger.info(
            f"{log_prefix} Price matching complete: {matched_count} matched from leaflet, "
            f"{estimated_count} estimated, {not_found_count} not found, total: {total_sum} {goal.currency}"
        )

        # Step 7: Create DietaryPlan
        plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            days=transformed_days,
            shopping_list=validated_shopping_list,
            total_price=total_sum,
            currency=goal.currency,
            llm_model_used=llm_result.get('model'),
            llm_input_tokens=llm_result.get('input_tokens'),
            llm_output_tokens=llm_result.get('output_tokens'),
            llm_total_tokens=llm_result.get('total_tokens'),
            llm_cost_usd=llm_result.get('cost_usd')
        )

        goal.status = DietaryGoal.StatusChoices.COMPLETED
        goal.completed_at = timezone.now()
        goal.save(update_fields=['status', 'completed_at'])

        # Final Summary Log
        logger.info(f"{log_prefix} SUMMARY: Shopping list creation complete")
        logger.info(f"{log_prefix} SUMMARY: Plan ID: {plan.id}, Total items: {len(validated_shopping_list)}")
        logger.info(f"{log_prefix} SUMMARY: Price breakdown - Matched: {matched_count}, Estimated: {estimated_count}, Not found: {not_found_count}")
        logger.info(f"{log_prefix} SUMMARY: Total price: {total_sum} {goal.currency}")
        
        # Log sample items with full details
        sample_items = validated_shopping_list[:5]  # First 5 items
        logger.debug(f"{log_prefix} SUMMARY: Sample items:")
        for item in sample_items:
            logger.debug(f"{log_prefix} SUMMARY:   - {_log_item_details(item)}")
        
        if validation_adjustments:
            logger.warning(f"{log_prefix} SUMMARY: {len(validation_adjustments)} items were adjusted during validation")
        
        logger.info(f"{log_prefix} Successfully created plan {plan.id} for goal {goal_id}")
        return {'status': 'success', 'plan_id': plan.id}

    except Exception as exc:
        logger.error(f"Task failed for goal {goal_id}: {str(exc)}", exc_info=True)
        try:
            goal = DietaryGoal.objects.get(id=goal_id)
            goal.status = DietaryGoal.StatusChoices.FAILED
            goal.save(update_fields=['status'])
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=30)


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
