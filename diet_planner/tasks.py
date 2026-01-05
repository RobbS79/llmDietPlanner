"""
Celery tasks for async LLM processing.
Handles dietary goal processing, meal idea generation, and shopping list creation.
"""
from celery import shared_task
from django.utils import timezone
from typing import Dict, Any, List, Optional
import json
import logging

from .models import DietaryGoal, DietaryPlan
from .schemas import DietaryPlanResponse, MealIdea, ShoppingListItem
from .llm_service import OpenAIService
from .scrapers.scraper_service import ScraperService

logger = logging.getLogger(__name__)


def transform_days_to_new_format(days_data: List[Dict[str, Any]], goal: DietaryGoal) -> List[Dict[str, Any]]:
    """
    Transform days data from old format (main_courses array) to new format (breakfast/lunch/dinner objects).
    
    Args:
        days_data: List of day dictionaries from LLM response
        goal: DietaryGoal instance with breakfast/lunch/dinner flags
        
    Returns:
        Transformed days data with breakfast/lunch/dinner as separate objects
    """
    if not days_data or not isinstance(days_data, list):
        logger.warning(f"Invalid days_data passed to transform_days_to_new_format: {type(days_data)}")
        return []
    
    if goal is None:
        logger.warning("Goal is None in transform_days_to_new_format")
        return days_data
    
    transformed_days = []
    
    # Safely get breakfast/lunch/dinner flags (handle cases where migration hasn't run)
    try:
        wants_breakfast = getattr(goal, 'breakfast', True)
        wants_lunch = getattr(goal, 'lunch', True)
        wants_dinner = getattr(goal, 'dinner', True)
    except (AttributeError, TypeError) as e:
        # Fallback if fields don't exist yet or goal is invalid
        logger.warning(f"Could not get meal flags from goal: {e}, using defaults")
        wants_breakfast = wants_lunch = wants_dinner = True
    
    for day in days_data:
        if not isinstance(day, dict):
            logger.warning(f"Skipping invalid day entry: {day}")
            continue
            
        transformed_day = {
            'day_number': day.get('day_number', len(transformed_days) + 1),
            'small_meals': day.get('small_meals', []),
            'snacks': day.get('snacks', []),
        }
        
        # If new format already exists, use it
        if 'breakfast' in day or 'lunch' in day or 'dinner' in day:
            if wants_breakfast and 'breakfast' in day and day['breakfast']:
                transformed_day['breakfast'] = day['breakfast']
            if wants_lunch and 'lunch' in day and day['lunch']:
                transformed_day['lunch'] = day['lunch']
            if wants_dinner and 'dinner' in day and day['dinner']:
                transformed_day['dinner'] = day['dinner']
        # Otherwise, convert from old main_courses format
        elif 'main_courses' in day and isinstance(day['main_courses'], list):
            main_courses = day['main_courses']
            # Distribute main courses to breakfast/lunch/dinner based on user selection
            meal_index = 0
            if wants_breakfast and meal_index < len(main_courses):
                transformed_day['breakfast'] = main_courses[meal_index]
                meal_index += 1
            if wants_lunch and meal_index < len(main_courses):
                transformed_day['lunch'] = main_courses[meal_index]
                meal_index += 1
            if wants_dinner and meal_index < len(main_courses):
                transformed_day['dinner'] = main_courses[meal_index]
                meal_index += 1
        
        transformed_days.append(transformed_day)
    
    return transformed_days


def build_llm_prompt_json(goal: DietaryGoal, available_ingredients: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Build a structured JSON prompt for the LLM based on user input.
    
    This JSON structure serves as the prompt context for the LLM to generate
    meal ideas and shopping lists. The structure is designed to be clear and
    comprehensive for LLM processing.
    
    Example output structure:
    {
        "task": "generate_personalised_diet_plan",
        "user_requirements": {
            "dietary_prompt": "I want to lose 5kg in 2 months...",
            "dietary_restrictions": "No gluten, lactose intolerant"
        },
        "location": {
            "country_code": "CZ",
            "country_name": "Czech Republic",
            "city": "Prague"
        },
        "localisation": {
            "currency": "CZK",
            "language_code": "cs"
        },
        "available_ingredients": {
            "shop": "LIDL_CZ",
            "ingredients": [...],
            ...
        },
        "instructions": {
            "output_format": "json",
            "required_outputs": ["meal_ideas", "shopping_list"],
            ...
        }
    }
    
    Args:
        goal: DietaryGoal instance with user input
        available_ingredients: Optional list of available ingredients from scraped leaflet data
        
    Returns:
        Dict containing structured prompt data for LLM
    """
    prompt_data = {
        "task": "generate_personalised_diet_plan",
        "user_requirements": {
            "dietary_prompt": goal.prompt,
            "dietary_restrictions": goal.dietary_restrictions if goal.dietary_restrictions else None,
        },
        "location": {
            "country_code": goal.country,
            "country_name": dict(DietaryGoal._meta.get_field('country').choices).get(goal.country, goal.country),
            "city": goal.city,
        },
        "localisation": {
            "currency": goal.currency,
            "language_code": goal.language_code,
        },
        "available_ingredients": {
            "shop": goal.shop if goal.shop else None,
            "ingredients": available_ingredients or [],
            "source": f"Current leaflet offers from {goal.shop}" if goal.shop else None,
            "note": f"You MUST match shopping list ingredients with products from this list. Each product includes price, currency, and unit. Use the exact product details when creating the shopping list." if (goal.shop and available_ingredients) else "No specific shop selected - use common ingredients available in local supermarkets.",
        },
        "instructions": {
            "output_format": "json",
            "meal_plan_type": "day_by_day_meal_plan",
            "meal_plan_configuration": {
                "num_days": goal.num_days,
                "breakfast": goal.breakfast,
                "lunch": goal.lunch,
                "dinner": goal.dinner,
                "small_meals_per_day": goal.small_meals_per_day,
                "snacks_per_day": goal.snacks_per_day
            },
            "required_outputs": [
                "days",
                "shopping_list"
            ],
            "day_plan_requirements": {
                "structure": "Each day must have:",
                "main_meals": {
                    "breakfast": goal.breakfast,
                    "lunch": goal.lunch,
                    "dinner": goal.dinner,
                    "description": "Main meals (breakfast, lunch, dinner) - include only the meals that are set to true"
                },
                "small_meals": {
                    "count_per_day": goal.small_meals_per_day,
                    "description": "Small meals (breakfast, lunch, etc.) for each day"
                },
                "snacks": {
                    "count_per_day": goal.snacks_per_day,
                    "description": "Snacks for each day"
                },
                "each_meal_must_include": [
                    "name",
                    "description",
                    "ingredients",
                    "preparation_time",
                    "nutritional_info"
                ],
                "nutritional_info_should_include": [
                    "calories",
                    "protein",
                    "carbs",
                    "fat"
                ]
            },
            "shopping_list_requirements": {
                "include": [
                    "ingredient",
                    "quantity",
                    "unit",
                    "notes",
                    "matched_product_name",
                    "price",
                    "currency",
                    "product_unit",
                    "package_size"
                ],
                "matching_instructions": "For EVERY ingredient in the shopping list, you MUST find a matching product from the available_ingredients list. Match ingredients ONLY if they are the SAME or VERY SIMILAR ingredient type. Examples of GOOD matches: 'chicken' matches 'chicken breast' or 'chicken meat', 'eggs' matches 'chicken eggs' or 'eggs', 'spinach' matches 'fresh spinach' or 'spinach', 'tomatoes' matches 'cherry tomatoes' or 'tomatoes'. Examples of BAD matches (DO NOT match these): 'pepper' should NOT match 'peppermint' or 'bell pepper' unless it's actually black/white pepper spice, 'salt' should NOT match 'sea salt flakes' unless it's actually salt, 'olive oil' should match 'olive oil' but NOT 'sunflower oil'. If the ingredient is NOT in the available_ingredients list, set price to null - do NOT match to unrelated products. For each matched product, include: matched_product_name (use display_name from available_ingredients), price (numeric value - use the EXACT price from available_ingredients, this is the TOTAL price for the product/package as listed), currency (3-letter code), product_unit (unit from available_ingredients), and package_size (package_size from available_ingredients if present). CRITICAL: Only match if the ingredient types are the same - if unsure, set price to null.",
                "notes": "Quantities are optional but recommended. Use metric units (g, kg, ml, l). Aggregate quantities for the entire meal plan across all days."
            },
            "context_notes": [
                f"This is a {goal.num_days}-day meal plan. For each day, you MUST include:",
                f"- Breakfast: {'YES - include a breakfast meal object' if goal.breakfast else 'NO - do not include breakfast'}",
                f"- Lunch: {'YES - include a lunch meal object' if goal.lunch else 'NO - do not include lunch'}",
                f"- Dinner: {'YES - include a dinner meal object' if goal.dinner else 'NO - do not include dinner'}",
                f"- {goal.small_meals_per_day} small meal(s) per day (as an array)",
                f"- {goal.snacks_per_day} snack(s) per day (as an array)",
                "",
                "CRITICAL: The output structure MUST be a JSON object with a 'days' array.",
                "Each day object must have:",
                "- 'day_number': integer (1, 2, 3, ...)",
                "- 'breakfast': single meal object (ONLY if breakfast is requested)",
                "- 'lunch': single meal object (ONLY if lunch is requested)",
                "- 'dinner': single meal object (ONLY if dinner is requested)",
                "- 'small_meals': array of meal objects",
                "- 'snacks': array of meal objects",
                "",
                "Example structure for a day (when all meals are requested):",
                "{",
                "  'day_number': 1,",
                "  'breakfast': {'name': '...', 'description': '...', 'ingredients': [...], 'preparation_time': 15, 'instructions': ['Step 1...', 'Step 2...'], 'nutritional_info': {'calories': 300, 'protein': 20, 'carbs': 30, 'fat': 10}},",
                "  'lunch': {'name': '...', 'description': '...', 'ingredients': [...], 'preparation_time': 30, 'instructions': ['Step 1...', 'Step 2...'], 'nutritional_info': {...}},",
                "  'dinner': {'name': '...', 'description': '...', 'ingredients': [...], 'preparation_time': 45, 'instructions': ['Step 1...', 'Step 2...'], 'nutritional_info': {...}},",
                "  'small_meals': [...],",
                "  'snacks': [...]",
                "}",
                "",
                "IMPORTANT RULES:",
                "- Each main meal (breakfast, lunch, dinner) is a SINGLE object, NOT an array",
                "- Only include breakfast/lunch/dinner fields if they are requested (true)",
                "- Do NOT use 'main_courses' field - use 'breakfast', 'lunch', 'dinner' instead",
                "- **CRITICAL**: Each meal object MUST include an 'instructions' array with detailed, step-by-step cooking instructions",
                "- Instructions must be specific cooking steps, NOT generic placeholders",
                "- Each instruction should be a clear action (e.g., 'Heat 1 tablespoon of olive oil in a pan over medium heat', 'Beat 3 eggs in a bowl', 'Add spinach and cook for 2 minutes until wilted')",
                "- Provide 4-8 detailed steps that guide the user through the entire cooking process",
                "- Instructions should be in the same language as the meal name and description",
                "- Ingredients should be available in local supermarkets (Lidl, Biedronka, Kaufland, etc.)",
                f"- {'CRITICAL: Match shopping list ingredients ONLY to products from available_ingredients that are the SAME ingredient type. Do NOT match unrelated products. If an ingredient is not in the list (e.g., pepper, salt for seasoning), set price to null. It is BETTER to have no price than to match incorrectly. Include matched_product_name, price, currency, product_unit, and package_size for matched items.' if goal.shop and available_ingredients else '- Use common ingredients that are typically available in local supermarkets.'}",
                "- Consider local cuisine preferences for the specified country",
                "- MATCHING REQUIREMENT: For each shopping list item, search the available_ingredients list and find a matching product ONLY if it's the SAME ingredient type. Do NOT match to unrelated products just to fill in a price. If no match exists, set price to null. It's better to show 'Price N/A' than to show an incorrect price from a wrong product.",
                "- Focus on creating practical, achievable meal plans",
                "- Ensure variety across days to prevent meal fatigue",
                f"- Generate ALL text (meal names, descriptions, ingredients, instructions) in {goal.language_code} language"
            ]
        }
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


@shared_task(bind=True, max_retries=3)
def process_dietary_goal_task(self, goal_id: int) -> Dict[str, Any]:
    """
    Async Celery task to process a dietary goal using LLM.
    
    This task:
    1. Retrieves the dietary goal
    2. Calls LLM to generate meal ideas and shopping list
    3. Creates a DietaryPlan with LLM-generated content
    4. Updates goal status
    
    Note: Price calculation and availability checks are handled separately
    by Django (not the LLM) using database queries.
    
    Args:
        goal_id: ID of the DietaryGoal to process
        
    Returns:
        Dict with task result information
    """
    try:
        # Retrieve the goal
        goal = DietaryGoal.objects.get(id=goal_id)
        
        # Update status to processing
        goal.status = DietaryGoal.StatusChoices.PROCESSING
        goal.save(update_fields=['status'])
        
        # Get available ingredients from scraped leaflet data (if shop is selected)
        available_ingredients = []
        if goal.shop:
            try:
                logger.info(f"Fetching available ingredients for {goal.shop} ({goal.country}) - forcing refresh (cache disabled for debugging)")
                available_ingredients = ScraperService.get_available_ingredients(
                    shop=goal.shop,
                    country=goal.country,
                    force_refresh=True  # Force refresh every time until debugging is complete
                )
                logger.info(f"Found {len(available_ingredients)} available ingredients")
            except Exception as e:
                logger.warning(f"Error fetching available ingredients for goal {goal_id}: {e}", exc_info=True)
                # Continue without available ingredients if scraping fails
                available_ingredients = []
        
        # Build structured JSON prompt for LLM
        llm_prompt_json = build_llm_prompt_json(goal, available_ingredients)
        
        # Convert JSON to string for LLM prompt (with pretty formatting for readability)
        llm_prompt_text = json.dumps(llm_prompt_json, indent=2, ensure_ascii=False)
        
        # Log the JSON prompt for debugging (can be viewed in Celery logs)
        logger.info(f"LLM Prompt JSON for goal {goal_id}:\n{llm_prompt_text}")
        
        # Call OpenAI API
        try:
            llm_service = OpenAIService()
            llm_result = llm_service.generate_dietary_plan(
                prompt_text=llm_prompt_text,
                language_code=goal.language_code
            )
            
            # Extract response data
            llm_response = llm_result['response']
            days_data = llm_response.get('days', [])
            shopping_list_data = llm_response.get('shopping_list', [])
            
            # Validate days structure
            if not days_data or not isinstance(days_data, list):
                raise ValueError(f"Invalid days structure: expected list, got {type(days_data)}")
            
            # Transform old format (main_courses array) to new format (breakfast/lunch/dinner objects)
            try:
                days_data = transform_days_to_new_format(days_data, goal)
            except Exception as transform_error:
                logger.error(f"Error transforming days data for goal {goal_id}: {transform_error}", exc_info=True)
                # Continue with original data if transformation fails
                logger.warning(f"Using original days data structure for goal {goal_id}")
            
            # Log cost information
            logger.info(
                f"OpenAI API call for goal {goal_id}: "
                f"Input tokens: {llm_result['input_tokens']}, "
                f"Output tokens: {llm_result['output_tokens']}, "
                f"Total tokens: {llm_result['total_tokens']}, "
                f"Cost: ${llm_result['cost_usd']}, "
                f"Model: {llm_result['model']}"
            )
            
        except Exception as e:
            logger.error(f"OpenAI API error for goal {goal_id}: {e}", exc_info=True)
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Fall back to mock data if API fails
            logger.warning(f"Falling back to mock data for goal {goal_id}")
            llm_response = generate_mock_llm_response()
            days_data = llm_response.get('days', [])
            shopping_list_data = llm_response.get('shopping_list', [])
            
            # Transform mock data to new format
            try:
                days_data = transform_days_to_new_format(days_data, goal)
            except Exception as transform_error:
                logger.error(f"Error transforming mock days data for goal {goal_id}: {transform_error}", exc_info=True)
                # Continue with original mock data if transformation fails
                logger.warning(f"Using original mock days data structure for goal {goal_id}")
            llm_result = {
                'input_tokens': None,
                'output_tokens': None,
                'total_tokens': None,
                'cost_usd': None,
                'model': None,
            }
        
        # Use shopping list directly from LLM (with matched prices)
        enhanced_shopping_list = shopping_list_data
        
        # Log diagnostic information about LLM matching
        if shopping_list_data:
            items_with_price = [item for item in shopping_list_data if item.get('price') is not None and item.get('price') != '']
            items_without_price = [item for item in shopping_list_data if item.get('price') is None or item.get('price') == '']
            logger.info(f"LLM shopping list matching: {len(items_with_price)}/{len(shopping_list_data)} items have prices")
            if items_without_price:
                unmatched_ingredients = [item.get('ingredient', 'unknown') for item in items_without_price]
                logger.warning(f"LLM failed to match prices for {len(items_without_price)} items: {', '.join(unmatched_ingredients[:10])}{'...' if len(unmatched_ingredients) > 10 else ''}")
        
        # Fallback 1: Use backend matching for items LLM failed to match (if shop is selected)
        if goal.shop and enhanced_shopping_list:
            try:
                items_needing_fallback = [item for item in enhanced_shopping_list if item.get('price') is None or item.get('price') == '']
                if items_needing_fallback:
                    logger.info(f"Attempting backend fallback matching for {len(items_needing_fallback)} unmatched items")
                    for item in items_needing_fallback:
                        ingredient_name = item.get('ingredient', '')
                        if ingredient_name:
                            price_info = ScraperService.match_ingredient_price(ingredient_name, goal.shop, goal.country)
                            if price_info:
                                # Log the match for debugging - this helps identify false matches
                                logger.info(f"Backend fallback matched '{ingredient_name}' -> '{price_info['display_name']}' ({price_info['price']} {price_info['currency']})")
                                item['price'] = float(price_info['price'])
                                item['currency'] = price_info['currency']
                                item['product_unit'] = price_info['unit']
                                item['matched_product_name'] = price_info['display_name']
            except Exception as e:
                logger.warning(f"Error in backend fallback matching: {e}", exc_info=True)
        
        # Fallback 2: Use LLM to estimate prices for items still without prices
        items_still_needing_price = [item for item in enhanced_shopping_list if item.get('price') is None or item.get('price') == '']
        if items_still_needing_price and goal.shop:
            try:
                logger.info(f"Attempting LLM price estimation for {len(items_still_needing_price)} items not found in leaflet")
                llm_service = OpenAIService()
                
                for item in items_still_needing_price:
                    ingredient_name = item.get('ingredient', '')
                    if ingredient_name:
                        quantity = item.get('quantity')
                        unit = item.get('unit')
                        
                        price_estimate = llm_service.estimate_product_price(
                            ingredient_name=ingredient_name,
                            quantity=quantity,
                            unit=unit,
                            shop=goal.shop,
                            country=goal.country
                        )
                        
                        if price_estimate:
                            item['price'] = float(price_estimate['price'])
                            item['currency'] = price_estimate['currency']
                            item['product_unit'] = price_estimate.get('unit')
                            item['matched_product_name'] = price_estimate['display_name']
                            item['price_estimated'] = True  # Flag to indicate this is an estimate
                            item['price_source'] = 'llm_estimate'
                            logger.info(f"LLM estimated price for '{ingredient_name}': {price_estimate['price']} {price_estimate['currency']} (estimated)")
                        else:
                            logger.info(f"LLM could not estimate price for '{ingredient_name}' - leaving as null")
            except Exception as e:
                logger.warning(f"Error in LLM price estimation: {e}", exc_info=True)
        
        # Calculate total price per item based on quantity and unit price
        # The price from LLM/leaflet is typically a unit price, so we need to multiply by quantity
        if enhanced_shopping_list:
            try:
                from decimal import Decimal
                import re
                
                def parse_quantity(quantity_str: str, unit_str: str = None) -> Optional[Decimal]:
                    """Parse quantity string (e.g., '33 ks', '1650 g') into Decimal value."""
                    if not quantity_str:
                        return None
                    # Extract numeric value from quantity string
                    match = re.search(r'([\d,\.]+)', str(quantity_str))
                    if match:
                        try:
                            # Replace comma with dot for decimal parsing
                            num_str = match.group(1).replace(',', '.')
                            return Decimal(num_str)
                        except (ValueError, Exception):
                            return None
                    return None
                
                def normalize_unit(unit: str) -> str:
                    """Normalize unit strings for comparison (kg, g, l, ml, ks, etc.)."""
                    if not unit:
                        return ''
                    unit_lower = str(unit).lower().strip()
                    # Normalize common unit variations
                    unit_map = {
                        'kg': 'kg', 'kilogram': 'kg', 'kilogramme': 'kg',
                        'g': 'g', 'gram': 'g', 'gramme': 'g',
                        'l': 'l', 'litre': 'l', 'liter': 'l',
                        'ml': 'ml', 'millilitre': 'ml', 'milliliter': 'ml',
                        'ks': 'ks', 'piece': 'ks', 'pieces': 'ks', 'pcs': 'ks', 'pc': 'ks',
                    }
                    return unit_map.get(unit_lower, unit_lower)
                
                def extract_package_size(item: Dict[str, Any]) -> Optional[Decimal]:
                    """
                    Try to extract package size from item data.
                    First checks if LLM provided package_size, then falls back to parsing product name.
                    Returns the numeric package size if found, None otherwise.
                    """
                    # First, check if LLM provided package_size directly
                    package_size = item.get('package_size')
                    if package_size is not None:
                        try:
                            if isinstance(package_size, (int, float)):
                                return Decimal(str(package_size))
                            elif isinstance(package_size, str):
                                return Decimal(str(package_size).replace(',', '.'))
                            else:
                                return Decimal(str(package_size))
                        except (ValueError, Exception):
                            pass
                    
                    # Fallback: try to extract from product name
                    product_name = item.get('matched_product_name', '')
                    if not product_name:
                        return None
                    
                    offer_unit = item.get('product_unit', '')
                    
                    # Pattern: number + unit (e.g., "10 ks", "500 g", "1kg", "0.5 l")
                    patterns = [
                        r'(\d+[\.,]?\d*)\s*(ks|piece|pieces|pcs|pc|bal|balíček)',  # Pieces
                        r'(\d+[\.,]?\d*)\s*(kg|kilogram)',  # Kilograms
                        r'(\d+[\.,]?\d*)\s*(g|gram)',  # Grams
                        r'(\d+[\.,]?\d*)\s*(l|litre|liter)',  # Liters
                        r'(\d+[\.,]?\d*)\s*(ml|millilitre|milliliter)',  # Milliliters
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, product_name, re.I)
                        if match:
                            try:
                                size_str = match.group(1).replace(',', '.')
                                return Decimal(size_str)
                            except (ValueError, Exception):
                                continue
                    
                    return None
                
                def calculate_item_total_price(item: Dict[str, Any]) -> Optional[Decimal]:
                    """
                    Calculate total price for a shopping list item.
                    
                    The item contains:
                    - price: price from leaflet (could be per unit or per package)
                    - matched_product_name: product name that might contain package size
                    - product_unit: unit from the offer
                    - quantity: required quantity (e.g., '33 ks')
                    - unit: unit of required quantity (e.g., 'ks')
                    
                    Logic:
                    1. Try to extract package size from product name (e.g., "Eggs 10 pieces" -> 10)
                    2. If package size found, calculate per-unit price: price / package_size
                    3. Multiply per-unit price by required quantity
                    4. Handle unit conversions for weight/volume
                    """
                    price = item.get('price')
                    if price is None:
                        return None
                    
                    try:
                        offer_price = Decimal(str(price))
                        if offer_price <= 0:
                            return None
                    except (ValueError, TypeError):
                        return None
                    
                    quantity_str = item.get('quantity', '')
                    quantity_unit = item.get('unit', '')
                    offer_unit = item.get('product_unit', '')
                    product_name = item.get('matched_product_name', '')
                    
                    # Parse required quantity
                    required_qty = parse_quantity(quantity_str, quantity_unit)
                    if required_qty is None or required_qty <= 0:
                        # If no quantity specified, assume we need 1 unit
                        required_qty = Decimal('1')
                    
                    # Try to extract package size from item data (LLM-provided or from name)
                    package_size = extract_package_size(item)
                    
                    # Normalize units for comparison
                    norm_quantity_unit = normalize_unit(quantity_unit)
                    norm_offer_unit = normalize_unit(offer_unit)
                    
                    # Log for debugging - ALWAYS log all input data
                    logger.info(f"=== PRICE CALCULATION DEBUG for {item.get('ingredient')} ===")
                    logger.info(f"  offer_price: {offer_price}")
                    logger.info(f"  package_size: {package_size}")
                    logger.info(f"  offer_unit (raw): '{offer_unit}' -> normalized: '{norm_offer_unit}'")
                    logger.info(f"  quantity: {required_qty} {norm_quantity_unit}")
                    logger.info(f"  matched_product_name: {product_name}")
                    logger.info(f"  item data: price={item.get('price')}, product_unit={item.get('product_unit')}, package_size_field={item.get('package_size')}")
                    
                    # Calculate per-unit price based on package size
                    # CRITICAL: If package_size is provided, the price is FOR THAT PACKAGE
                    # We need to figure out what the package_size unit is (g, kg, ks, etc.)
                    if package_size and package_size > 0 and package_size != 1:
                        # Price is for a package, calculate per-unit price
                        # BUT: We need to know what unit the package_size represents
                        # If offer_unit is "kg" and package_size is 500, it's likely 500g package
                        # If offer_unit is "g" and package_size is 500, it's 500g package
                        # If offer_unit is "ks" and package_size is 10, it's 10 pieces
                        
                        # For now, assume package_size is in the same unit as offer_unit
                        # Calculate per-unit price: price / package_size
                        per_unit_price = offer_price / package_size
                        logger.info(f"  Package detected: {offer_price} for {package_size} {norm_offer_unit}")
                        logger.info(f"  Calculated per-unit price: {per_unit_price} per {norm_offer_unit}")
                    else:
                        # Price is already per unit (per kg, per piece, etc.)
                        per_unit_price = offer_price
                        logger.info(f"  No package size or package_size=1, using price as per-unit: {per_unit_price} per {norm_offer_unit or 'unit'}")
                    
                    # Now calculate total based on required quantity and units
                    # CRITICAL: Handle unit conversions FIRST before multiplying
                    
                    # If units match exactly, multiply directly
                    # BUT: Check if this makes sense for pieces (ks)
                    # If we need multiple pieces and price seems high, it might be a package price
                    if norm_quantity_unit == norm_offer_unit:
                        total = per_unit_price * required_qty
                        
                        # Special check for pieces: if price per piece seems too high (> 15 CZK per piece) 
                        # and we need multiple pieces, it's likely a package price we didn't detect
                        if norm_quantity_unit == 'ks' and required_qty > 1 and per_unit_price > Decimal('15'):
                            # This looks like a package price - try to infer package size
                            # Common package sizes: 6, 10, 12, 15, 20 pieces
                            # Try dividing by common sizes and see if we get reasonable per-piece prices
                            common_package_sizes = [6, 10, 12, 15, 20, 30]
                            best_match = None
                            best_price = None
                            
                            for pkg_size in common_package_sizes:
                                inferred_per_piece = offer_price / Decimal(str(pkg_size))
                                # Reasonable price per piece: between 1-15 CZK (for eggs, fruit, etc.)
                                if Decimal('1') <= inferred_per_piece <= Decimal('15'):
                                    if best_match is None or abs(inferred_per_piece - Decimal('6')) < abs(best_price - Decimal('6')):
                                        # Prefer prices around 5-7 CZK per piece (typical for eggs)
                                        best_match = pkg_size
                                        best_price = inferred_per_piece
                            
                            if best_match:
                                recalculated_total = best_price * required_qty
                                logger.warning(f"  ⚠ SMART FIX for pieces: Price {offer_price} CZK seems high per piece ({per_unit_price} CZK/piece).")
                                logger.warning(f"  → Inferring package of {best_match} pieces → {best_price} CZK per piece")
                                logger.info(f"  → Recalculated total: {recalculated_total} = {best_price} * {required_qty} pieces")
                                return recalculated_total
                            else:
                                logger.warning(f"  ⚠ Price {offer_price} CZK seems high ({per_unit_price} CZK/piece) but couldn't infer package size. Using direct multiplication.")
                        
                        logger.info(f"  ✓ Units match ({norm_quantity_unit}): {total} = {per_unit_price} * {required_qty}")
                        return total
                    
                    # Handle unit conversions (kg <-> g, l <-> ml)
                    # CRITICAL: Most prices in leaflets are per kg, but quantities are often in grams!
                    if norm_offer_unit == 'kg' and norm_quantity_unit == 'g':
                        # Offer is per kg, quantity is in grams: convert g to kg
                        quantity_kg = required_qty / Decimal('1000')
                        total = per_unit_price * quantity_kg
                        logger.info(f"  ✓ Unit conversion (kg->g): {total} = {per_unit_price} * ({required_qty}g / 1000) = {per_unit_price} * {quantity_kg}kg")
                        return total
                    elif norm_offer_unit == 'g' and norm_quantity_unit == 'kg':
                        # Offer is per g, quantity is in kg: convert kg to g
                        quantity_g = required_qty * Decimal('1000')
                        total = per_unit_price * quantity_g
                        logger.info(f"  ✓ Unit conversion (g->kg): {total} = {per_unit_price} * ({required_qty}kg * 1000) = {per_unit_price} * {quantity_g}g")
                        return total
                    elif norm_offer_unit == 'l' and norm_quantity_unit == 'ml':
                        # Offer is per l, quantity is in ml: convert ml to l
                        quantity_l = required_qty / Decimal('1000')
                        total = per_unit_price * quantity_l
                        logger.info(f"  ✓ Unit conversion (l->ml): {total} = {per_unit_price} * ({required_qty}ml / 1000) = {per_unit_price} * {quantity_l}l")
                        return total
                    elif norm_offer_unit == 'ml' and norm_quantity_unit == 'l':
                        # Offer is per ml, quantity is in l: convert l to ml
                        quantity_ml = required_qty * Decimal('1000')
                        total = per_unit_price * quantity_ml
                        logger.info(f"  ✓ Unit conversion (ml->l): {total} = {per_unit_price} * ({required_qty}l * 1000) = {per_unit_price} * {quantity_ml}ml")
                        return total
                    elif norm_offer_unit == 'ks' and norm_quantity_unit == 'ks':
                        # Both are pieces, should have matched above, but just in case
                        total = per_unit_price * required_qty
                        logger.info(f"  ✓ Pieces match: {total} = {per_unit_price} * {required_qty}")
                        return total
                    
                    # CRITICAL FIX: If offer_unit is null/empty and quantity is in grams, assume price is per kg
                    # This is the MOST COMMON case - leaflets show prices per kg, but LLM might not extract the unit
                    if not norm_offer_unit or norm_offer_unit == '':
                        if norm_quantity_unit == 'g':
                            # Most common: price is per kg, quantity in grams
                            quantity_kg = required_qty / Decimal('1000')
                            total = per_unit_price * quantity_kg
                            logger.warning(f"  ⚠ WARNING: No offer unit but quantity in grams. Assuming price is per kg.")
                            logger.info(f"  → Calculated: {total} = {per_unit_price} * ({required_qty}g / 1000) = {per_unit_price} * {quantity_kg}kg")
                            return total
                        elif norm_quantity_unit == 'kg':
                            # Quantity is in kg, assume price is per kg
                            total = per_unit_price * required_qty
                            logger.warning(f"  ⚠ WARNING: No offer unit but quantity in kg. Assuming price is per kg.")
                            logger.info(f"  → Calculated: {total} = {per_unit_price} * {required_qty}kg")
                            return total
                        elif norm_quantity_unit == 'ks':
                            # Quantity is in pieces, assume price is per piece
                            total = per_unit_price * required_qty
                            logger.warning(f"  ⚠ WARNING: No offer unit but quantity in pieces. Assuming price is per piece.")
                            logger.info(f"  → Calculated: {total} = {per_unit_price} * {required_qty} pieces")
                            return total
                    
                    # Last resort: if we still can't match, try to be smart about it
                    # If quantity is in grams and the result seems too high, assume price is per kg
                    if norm_quantity_unit == 'g':
                        # Try assuming price is per kg - if result is more reasonable, use that
                        quantity_kg = required_qty / Decimal('1000')
                        alternative_total = per_unit_price * quantity_kg
                        direct_total = per_unit_price * required_qty
                        
                        # If direct multiplication gives > 1000 CZK and alternative is < 1000, use alternative
                        # This catches cases where price is per kg but unit wasn't set correctly
                        if direct_total > Decimal('1000') and alternative_total < Decimal('1000'):
                            logger.warning(f"  ⚠ SMART FIX: Direct multiplication gives {direct_total}, but assuming per-kg gives {alternative_total}. Using per-kg assumption.")
                            logger.info(f"  → Calculated: {alternative_total} = {per_unit_price} * ({required_qty}g / 1000) = {per_unit_price} * {quantity_kg}kg")
                            return alternative_total
                    
                    # Last resort: if we still can't match, log error and use direct multiplication
                    # This will likely be wrong, but better than crashing
                    total = per_unit_price * required_qty
                    logger.error(f"  ✗ ERROR: Cannot convert units for {item.get('ingredient')}: "
                               f"quantity_unit={norm_quantity_unit}, offer_unit={norm_offer_unit}.")
                    logger.error(f"  → Using direct multiplication (likely WRONG): {total} = {per_unit_price} * {required_qty}")
                    return total
                
                # Calculate total price for each item and update the item
                total_price_sum = Decimal('0')
                items_with_price_count = 0
                
                for item in enhanced_shopping_list:
                    item_total = calculate_item_total_price(item)
                    if item_total is not None:
                        # Store both unit price and total price
                        item['unit_price'] = str(item.get('price'))  # Keep original unit price
                        item['price'] = float(item_total)  # Update to total price for display
                        item['price_total'] = float(item_total)  # Explicitly store total
                        total_price_sum += item_total
                        items_with_price_count += 1
                
                total_price = total_price_sum if items_with_price_count > 0 else None
                logger.info(f"Calculated total price: {total_price} {goal.currency} ({items_with_price_count} items with calculated prices)")
                
            except Exception as e:
                logger.warning(f"Error calculating total price: {e}", exc_info=True)
                total_price = None
        else:
            total_price = None
        
        # Create dietary plan with LLM usage tracking
        dietary_plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            days=days_data,
            shopping_list=enhanced_shopping_list,
            currency=goal.currency,
            total_price=total_price,
            llm_input_tokens=llm_result.get('input_tokens'),
            llm_output_tokens=llm_result.get('output_tokens'),
            llm_total_tokens=llm_result.get('total_tokens'),
            llm_cost_usd=llm_result.get('cost_usd'),
            llm_model_used=llm_result.get('model'),
        )
        
        # Update goal status to completed
        goal.status = DietaryGoal.StatusChoices.COMPLETED
        goal.completed_at = timezone.now()
        goal.save(update_fields=['status', 'completed_at'])
        
        return {
            'status': 'success',
            'goal_id': goal_id,
            'plan_id': dietary_plan.id,
            'llm_usage': {
                'input_tokens': llm_result.get('input_tokens'),
                'output_tokens': llm_result.get('output_tokens'),
                'total_tokens': llm_result.get('total_tokens'),
                'cost_usd': str(llm_result.get('cost_usd')) if llm_result.get('cost_usd') else None,
                'model': llm_result.get('model'),
            }
        }
        
    except DietaryGoal.DoesNotExist:
        return {
            'status': 'error',
            'error': f'Dietary goal {goal_id} not found'
        }
    except Exception as exc:
        # Retry on failure
        goal = DietaryGoal.objects.get(id=goal_id)
        goal.status = DietaryGoal.StatusChoices.FAILED
        goal.save(update_fields=['status'])
        
        raise self.retry(exc=exc, countdown=60)


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
