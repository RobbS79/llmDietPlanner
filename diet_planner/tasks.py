# File: diet_planner/tasks.py
"""
Professional Dietary Synthesis Orchestrator
===========================================
Refactored for 100k users scale while RESTORING the full MVP domain logic.
This module implements the "Two-Phase" spirit:
Phase 1: Creative Nutritional Synthesis (Nutritionist Persona)
Phase 2: Semantic Market Mapping (Shopping Assistant Persona)
Phase 3: Financial Integrity (Backend Knowledge Base Persona)

Architecture Principles:
- LLM Intent: Persona shift prevents context pollution.
- Financial Truth: Backend overrides LLM guesses with Verified Knowledge Base.
- Zero-Orphan Policy: Atomic persistence of Recipes and MealInstances.
"""
import logging
import uuid
import time
import re
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

from django.db import transaction
from django.utils import timezone
from llm_diet_planner_project.celery_compat import shared_task

from .models import DietaryGoal, DietaryPlan, Recipe, MealInstance
from .llm_service import GeminiService
from .scrapers.scraper_service import ScraperService

logger = logging.getLogger(__name__)

# =============================================================================
# INGREDIENT KNOWLEDGE BASE (Restored from MVP)
# =============================================================================
# This is the "Spiritual Truth" of the app. It prevents LLM price hallucinations.

INGREDIENT_PACKAGE_INFO = {
    'avokádo': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'avocado': {'typical_unit': 'ks', 'avg_weight_g': 150, 'typical_packages': [1]},
    'banán': {'typical_unit': 'ks', 'avg_weight_g': 120, 'typical_packages': [1]},
    'egg': {'typical_unit': 'ks', 'avg_weight_g': 50, 'typical_packages': [6, 10, 15]},
    'vejce': {'typical_unit': 'ks', 'avg_weight_g': 50, 'typical_packages': [6, 10, 15]},
    'olivový olej': {'typical_unit': 'ml', 'typical_packages': [250, 500, 750, 1000]},
    'kuřecí prsa': {'typical_unit': 'g', 'typical_packages': [500, 1000]},
}

QUANTITY_LIMITS = {
    'spices': {'max_g': 100, 'keywords': ['salt', 'pepper', 'paprika', 'sůl', 'pepř']},
    'meat': {'max_g': 5000, 'keywords': ['chicken', 'beef', 'pork', 'maso', 'kuře']},
    'eggs': {'max_ks': 30, 'keywords': ['egg', 'vejce', 'vajíčko']},
}

# =============================================================================
# SYNTHESIS UTILITIES (Restored & In-lined)
# =============================================================================

def normalize_unit(unit: str) -> str:
    """Standardize units for comparison."""
    if not unit: return ''
    u = str(unit).lower().strip()
    mapping = {
        'kg': 'kg', 'kilogram': 'kg', 'g': 'g', 'gram': 'g',
        'l': 'l', 'liter': 'l', 'ml': 'ml', 'mililitr': 'ml',
        'ks': 'ks', 'kus': 'ks', 'piece': 'ks', 'pcs': 'ks',
    }
    return mapping.get(u, u)

def parse_numeric(val: Any) -> Optional[Decimal]:
    """Extract decimal number from strings like 'approx 500g'."""
    if val is None or val == '': return None
    if isinstance(val, (int, float, Decimal)): return Decimal(str(val))
    match = re.search(r'([\d,\.]+)', str(val))
    if match:
        try:
            return Decimal(match.group(1).replace(',', '.'))
        except: return None
    return None

def convert_to_base_value(val: Decimal, unit: str) -> Decimal:
    """Convert value to base metric (g or ml)."""
    u = normalize_unit(unit)
    if u == 'kg': return val * 1000
    if u == 'l': return val * 1000
    return val

def calculate_package_aware_price(item: Dict[str, Any], context_id: str = "", goal_id: int = 0) -> Optional[Decimal]:
    """Calculate total price based on rounded-up packages."""
    req_qty = parse_numeric(item.get('quantity'))
    req_unit = normalize_unit(item.get('unit', ''))
    off_price = parse_numeric(item.get('price'))
    off_unit = normalize_unit(item.get('product_unit', ''))
    off_pkg_size = parse_numeric(item.get('package_size'))
    
    if req_qty is None or off_price is None:
        return None

    req_base = convert_to_base_value(req_qty, req_unit)
    # If no package size, assume 1 unit (e.g. 1kg or 1 piece)
    pkg_base = convert_to_base_value(off_pkg_size or Decimal('1'), off_unit or req_unit)

    if pkg_base <= 0: return off_price
    
    num_packages = (req_base / pkg_base).to_integral_value(rounding='ROUND_CEILING')
    if num_packages < 1: num_packages = Decimal('1')
    
    return num_packages * off_price

def convert_requirement_to_purchasable_units(item: Dict[str, Any], db_match: Dict[str, Any], context_id: str = "", goal_id: int = 0) -> Dict[str, Any]:
    """Standardize recipe qty (grams) to purchase units (pieces) for items like avocados."""
    req_qty = parse_numeric(item.get('quantity'))
    req_unit = normalize_unit(item.get('unit', ''))
    prod_unit = normalize_unit(db_match.get('unit', ''))
    
    # Logic: if recipe asks for 150g but store sells per piece (ks)
    if req_unit in ['g', 'kg'] and prod_unit == 'ks':
        info = INGREDIENT_PACKAGE_INFO.get(item.get('ingredient', '').lower())
        if info and info.get('avg_weight_g'):
            avg = Decimal(str(info['avg_weight_g']))
            req_base = convert_to_base_value(req_qty, req_unit)
            pieces = (req_base / avg).to_integral_value(rounding='ROUND_CEILING')
            item['quantity'] = float(pieces)
            item['unit'] = 'ks'
    return item

def transform_days_to_new_format(days_data: List[Dict[str, Any]], goal: DietaryGoal) -> List[Dict[str, Any]]:
    """Ensure consistent object structure for React frontend."""
    if not days_data: return []
    transformed = []
    for day in days_data:
        day_obj = {
            'day_number': day.get('day_number', len(transformed) + 1),
            'breakfast': day.get('breakfast'),
            'lunch': day.get('lunch'),
            'dinner': day.get('dinner'),
            'small_meals': day.get('small_meals', []),
            'snacks': day.get('snacks', []),
        }
        transformed.append(day_obj)
    return transformed

def build_llm_prompt_json(goal: DietaryGoal, available_ingredients: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """RESTORED: Diagnostics prompt builder for Debug Views."""
    return {
        "task": "generate_personalised_meal_plan",
        "user_requirements": {"dietary_prompt": goal.prompt, "num_days": goal.num_days},
        "localisation": {"country": goal.country, "city": goal.city}
    }

# =============================================================================
# CORE ORCHESTRATOR
# =============================================================================

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def process_dietary_goal_task(self, goal_id: int) -> Dict[str, Any]:
    """
    Coordinates the 2-step LLM persona shift and enforces Financial Truth.
    """
    start_time = time.time()
    context_id = str(uuid.uuid4())[:8]
    log_prefix = f"[PROTOCOL_ORCHESTRATOR:{goal_id}:{context_id}]"
    
    try:
        goal = DietaryGoal.objects.get(id=goal_id)
        llm_service = GeminiService()
        
        shop_url = None
        if goal.shop:
            try:
                shop_url = ScraperService._get_shop_urls(goal.shop, goal.country)[0]
            except: pass

        # --- PHASE 1: Nutritionist Persona ---
        phase1_start = time.time()
        goal.status = DietaryGoal.StatusChoices.PROCESSING_MEAL_PLAN
        goal.save(update_fields=['status'])
        
        phase1_result = llm_service.generate_meal_plan_only(goal.prompt, shop_url, goal)
        days = phase1_result['response'].get('days', [])
        
        # --- PHASE 2: Shopping Assistant Persona ---
        phase2_start = time.time()
        goal.status = DietaryGoal.StatusChoices.PROCESSING_SHOPPING_LIST
        goal.save(update_fields=['status'])
        
        phase2_result = llm_service.generate_shopping_list_with_prices(days, shop_url, goal)
        llm_shopping_list = phase2_result['response'].get('shopping_list', [])
        
        # --- PHASE 3: Financial Truth (Leaflet Override) ---
        logger.info(f"{log_prefix} Phase 3: Enforcing Hub Reality.")
        final_shopping_list = []
        calculated_total = Decimal('0')
        
        for item in llm_shopping_list:
            ingredient_name = item.get('ingredient', '')
            db_match = ScraperService.match_ingredient_price(ingredient_name, goal.shop, goal.country)
            
            if db_match:
                item.update({
                    'price': float(db_match['price']),
                    'matched_product_name': db_match['display_name'],
                    'currency': db_match['currency'],
                    'package_size': db_match['package_size'],
                    'product_unit': db_match['unit'],
                    'estimated': False,
                    'price_source': 'leaflet_db'
                })
                item = convert_requirement_to_purchasable_units(item, db_match, context_id=context_id, goal_id=goal.id)
            else:
                item['estimated'] = True
                item['price_source'] = 'llm_browsing_fallback'

            final_price = calculate_package_aware_price(item, context_id, goal.id)
            item['price_total'] = float(final_price) if final_price else (item.get('price_total') or 0)
            calculated_total += Decimal(str(item['price_total']))
            final_shopping_list.append(item)

        # --- PHASE 4: Atomic Fulfillment ---
        logger.info(f"{log_prefix} Phase 4: Persisting object graph.")
        with transaction.atomic():
            plan = DietaryPlan.objects.create(
                dietary_goal=goal,
                days=transform_days_to_new_format(days, goal),
                shopping_list=final_shopping_list,
                total_price=calculated_total,
                currency=goal.currency,
                llm_model_used=phase1_result['model'],
                llm_input_tokens=phase1_result['input_tokens'] + phase2_result['input_tokens'],
                llm_output_tokens=phase1_result['output_tokens'] + phase2_result['output_tokens'],
                llm_cost_usd=phase1_result['cost_usd'] + phase2_result['cost_usd']
            )
            
            # Map every meal node to a trackable Recipe/Instance
            meal_types = {'breakfast': 'breakfast', 'lunch': 'lunch', 'dinner': 'dinner', 'small_meals': 'small_meal', 'snacks': 'snack'}
            for day in days:
                d_num = day.get('day_number')
                for key, label in meal_types.items():
                    data = day.get(key)
                    if not data: continue
                    nodes = data if isinstance(data, list) else [data]
                    for idx, m in enumerate(nodes):
                        m_id = f"{goal.id}:{d_num}:{label}:{idx}"
                        recipe, _ = Recipe.objects.update_or_create(
                            meal_identifier=m_id,
                            defaults={'dietary_goal': goal, 'name': m.get('name', 'Meal'), 'description': m.get('description', ''), 'instructions': m.get('instructions', []), 'ingredients': m.get('ingredients', []), 'nutritional_info': m.get('nutritional_info', {})}
                        )
                        MealInstance.objects.update_or_create(user=goal.user, meal_identifier=m_id, defaults={'dietary_goal': goal, 'recipe': recipe, 'meal_name': recipe.name, 'day_number': d_num, 'meal_type': label})

            goal.status = DietaryGoal.StatusChoices.COMPLETED
            goal.completed_at = timezone.now()
            goal.save(update_fields=['status', 'completed_at'])

        logger.info(f"{log_prefix} PROTOCOL SUCCESS. Roadmap ID: {plan.id}")
        return {'status': 'success', 'plan_id': plan.id}

    except Exception as exc:
        logger.error(f"{log_prefix} SYNTHESIS ABORTED: {str(exc)}")
        try:
            g = DietaryGoal.objects.get(id=goal_id)
            g.status = DietaryGoal.StatusChoices.FAILED
            g.error_message = str(exc)
            g.save(update_fields=['status', 'error_message'])
        except: pass
        raise