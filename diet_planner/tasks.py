from celery import shared_task
from django.utils import timezone
from typing import Dict, Any, List, Optional
import json
import logging
import re
from decimal import Decimal

from .models import DietaryGoal, DietaryPlan
from .schemas import DietaryPlanResponse, MealIdea, ShoppingListItem
from .llm_service import OpenAIService
from .scrapers.scraper_service import ScraperService

logger = logging.getLogger(__name__)


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


def build_llm_prompt_json(goal: DietaryGoal, available_ingredients: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Build a structured JSON prompt for the LLM.
    """
    prompt_data = {
        "task": "generate_personalised_diet_plan",
        "user_requirements": {
            "dietary_prompt": goal.prompt,
            "dietary_restrictions": goal.dietary_restrictions or None,
        },
        "localisation": {
            "currency": goal.currency,
            "language_code": goal.language_code,
        },
        "available_ingredients": {
            "shop": goal.shop,
            "ingredients": available_ingredients or [],
            "note": "MATCH ingredients only by name. DO NOT CALCULATE TOTAL PRICES. Only provide the raw quantity needed for the recipe.",
        },
        "instructions": {
            "output_format": "json",
            "meal_plan_configuration": {
                "num_days": goal.num_days,
                "breakfast": goal.breakfast,
                "lunch": goal.lunch,
                "dinner": goal.dinner,
                "small_meals_per_day": goal.small_meals_per_day,
                "snacks_per_day": goal.snacks_per_day
            },
            "shopping_list_requirements": {
                "matching_instructions": "Identify the best matching product from available_ingredients. Provide the exact quantity (e.g., 400) and unit (e.g., g) needed for the recipes. DO NOT perform any price math yourself; the backend handles package logic.",
                "fields": ["ingredient", "quantity", "unit", "matched_product_name", "price", "currency", "product_unit", "package_size"]
            }
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



def normalize_unit(unit: str) -> str:
    """Standardize units for comparison."""
    if not unit: return ''
    u = str(unit).lower().strip()
    mapping = {
        'kg': 'kg', 'kilogram': 'kg', 'kilogramy': 'kg', 'kg.': 'kg',
        'g': 'g', 'gram': 'g', 'gramy': 'g', 'g.': 'g',
        'l': 'l', 'litr': 'l', 'litry': 'l', 'litrů': 'l',
        'ml': 'ml', 'mililitr': 'ml', 'ml.': 'ml',
        'ks': 'ks', 'kus': 'ks', 'kusy': 'ks', 'kusů': 'ks', 'piece': 'ks', 'pcs': 'ks'
    }
    return mapping.get(u, u)



def convert_to_base_value(val: Decimal, unit: str) -> Decimal:
    """Convert value to base metric unit (g, ml, ks)."""
    u = normalize_unit(unit)
    if u == 'kg': return val * 1000
    if u == 'l': return val * 1000
    return val



def parse_numeric(val: Any) -> Optional[Decimal]:
    """Extract decimal from various formats."""
    if val is None or val == '': return None
    if isinstance(val, (int, float, Decimal)): return Decimal(str(val))
    match = re.search(r'([\d,\.]+)', str(val))
    if match:
        try:
            return Decimal(match.group(1).replace(',', '.'))
        except: return None
    return None


def calculate_package_aware_price(item: Dict[str, Any]) -> Optional[Decimal]:
    """
    Logic: Determine how many full packages are needed to satisfy the required quantity.
    """
    req_qty = parse_numeric(item.get('quantity'))
    req_unit = normalize_unit(item.get('unit'))
    off_price = parse_numeric(item.get('price'))
    off_unit = normalize_unit(item.get('product_unit'))
    off_pkg_size = parse_numeric(item.get('package_size'))

    if req_qty is None or off_price is None:
        return None

    req_base = convert_to_base_value(req_qty, req_unit)
    
    if off_pkg_size and off_pkg_size > 0:
        pkg_base = convert_to_base_value(off_pkg_size, off_unit)
    else:
        pkg_base = Decimal('1000') if off_unit in ['kg', 'l'] else Decimal('1')

    # Guard against division by zero
    if pkg_base <= 0: return off_price

    # Calculate whole packages needed (e.g., needing 400g from 500g pkg = 1 pkg)
    num_packages = (req_base / pkg_base).to_integral_value(rounding='ROUND_CEILING')
    
    # Sanity check to prevent massive numbers
    if num_packages > 100: num_packages = Decimal('10')

    return num_packages * off_price


@shared_task(bind=True, max_retries=3)
def process_dietary_goal_task(self, goal_id: int) -> Dict[str, Any]:
    try:
        goal = DietaryGoal.objects.get(id=goal_id)
        goal.status = DietaryGoal.StatusChoices.PROCESSING
        goal.save(update_fields=['status'])

        available_ingredients = []
        if goal.shop:
            available_ingredients = ScraperService.get_available_ingredients(goal.shop, goal.country, force_refresh=True)

        llm_service = OpenAIService()
        llm_result = llm_service.generate_dietary_plan(
            prompt_text=json.dumps(build_llm_prompt_json(goal, available_ingredients), ensure_ascii=False),
            language_code=goal.language_code
        )

        llm_response = llm_result['response']
        # CRITICAL: Preserve the shopping list from LLM response
        shopping_list = llm_response.get('shopping_list', [])
        
        total_sum = Decimal('0')
        for item in shopping_list:
            # 1. Try our new backend math first
            calculated_price = calculate_package_aware_price(item)
            
            if calculated_price:
                item['price_total'] = float(calculated_price)
                item['price'] = float(calculated_price)
                total_sum += calculated_price
                item['price_source'] = 'backend_package_logic'
            else:
                # 2. If backend logic fails, try LLM's own price estimation fallback
                est = llm_service.estimate_product_price(
                    item.get('ingredient'), 
                    item.get('quantity'), 
                    item.get('unit'), 
                    goal.shop, 
                    goal.country
                )
                if est:
                    item.update({
                        'price': float(est['price']),
                        'currency': est['currency'],
                        'matched_product_name': est['display_name'],
                        'estimated': True,
                        'price_source': 'llm_estimation_service'
                    })
                    total_sum += est['price']

        plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            days=transform_days_to_new_format(llm_response.get('days', []), goal),
            shopping_list=shopping_list, # Now explicitly passed here
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

        return {'status': 'success', 'plan_id': plan.id}

    except Exception as exc:
        logger.error(f"Task failed for goal {goal_id}: {str(exc)}", exc_info=True)
        goal = DietaryGoal.objects.get(id=goal_id)
        goal.status = DietaryGoal.StatusChoices.FAILED
        goal.save(update_fields=['status'])
        raise self.retry(exc=exc, countdown=30)


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
