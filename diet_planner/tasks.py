# File: diet_planner/tasks.py
"""
Professional Dietary Synthesis Orchestrator
===========================================
Refactored for 100k users scale. This module implements the "Two-Phase" spirit 
of the LLM architecture:
Phase 1: Creative Nutritional Synthesis (Nutritionist Role - Recipe focus)
Phase 2: Semantic Market Mapping (Shopping Assistant Role - Browsing focus)
Phase 3: Financial Integrity & Persistence (Backend/Trust Role - DB Validation)

Architecture Principles:
- LLM Intent: Shift personas between steps to avoid context pollution.
- Browsing Spirit: Use Gemini's URL browsing for real-time market alignment.
- Financial Truth: Backend overrides LLM price guesses with DB leaflet data.
- Full Persistence: Generates Plan, Recipes, and MealInstances in one atomic transaction.
"""
import logging
import uuid
import time
from decimal import Decimal
from typing import Dict, Any, List

from django.db import transaction
from django.utils import timezone
from llm_diet_planner_project.celery_compat import shared_task

from .models import DietaryGoal, DietaryPlan, Recipe, MealInstance
from .llm_service import GeminiService
from .scrapers.scraper_service import ScraperService
from .tasks_utils import (
    calculate_package_aware_price, 
    convert_requirement_to_purchasable_units,
    transform_days_to_new_format
)

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def process_dietary_goal_task(self, goal_id: int) -> Dict[str, Any]:
    """
    The Orchestrator coordinates the 2-step LLM persona shift and enforces
    Backend Financial Truth before finalizing the roadmap.
    """
    start_time = time.time()
    context_id = str(uuid.uuid4())[:8]
    log_prefix = f"[PROTOCOL_ORCHESTRATOR:{goal_id}:{context_id}]"
    
    try:
        goal = DietaryGoal.objects.get(id=goal_id)
        llm_service = GeminiService()
        
        # Determine Shop URL for Gemini's 'Browsing' spirit
        shop_url = None
        if goal.shop:
            try:
                shop_url = ScraperService._get_shop_urls(goal.shop, goal.country)[0]
            except: pass

        # --- PHASE 1: NUTRITIONAL LOGIC (Spirit: The Nutritionist) ---
        # persona: Expert Dietitian generating instructions and macros.
        phase1_start = time.time()
        goal.status = DietaryGoal.StatusChoices.PROCESSING_MEAL_PLAN
        goal.save(update_fields=['status'])
        
        logger.info(f"{log_prefix} Phase 1: Initiating Nutritionist Persona.")
        phase1_result = llm_service.generate_meal_plan_only(
            user_prompt=goal.prompt, 
            shop_url=shop_url, 
            goal=goal
        )
        days = phase1_result['response'].get('days', [])
        
        logger.info(f"{log_prefix} Phase 1 Complete ({time.time() - phase1_start:.2f}s).")

        # --- PHASE 2: MARKET MAPPING (Spirit: The Shopping Assistant) ---
        # persona: Practical Shopper browsing URLs to find real items and prices.
        phase2_start = time.time()
        goal.status = DietaryGoal.StatusChoices.PROCESSING_SHOPPING_LIST
        goal.save(update_fields=['status'])
        
        logger.info(f"{log_prefix} Phase 2: Initiating Shopping Assistant Persona (Browsing Hub).")
        phase2_result = llm_service.generate_shopping_list_with_prices(
            meal_plan_days=days, 
            shop_url=shop_url, 
            goal=goal
        )
        llm_shopping_list = phase2_result['response'].get('shopping_list', [])
        
        logger.info(f"{log_prefix} Phase 2 Complete ({time.time() - phase2_start:.2f}s).")

        # --- PHASE 3: FINANCIAL INTEGRITY (Spirit: Backend Trust) ---
        # We enforce "Backend Truth" by matching LLM names against our LeafletOffer DB.
        # This prevents the LLM from hallucinating prices or unavailable items.
        logger.info(f"{log_prefix} Phase 3: Enforcing Financial Truth via DB Cross-Reference.")
        final_shopping_list = []
        calculated_total = Decimal('0')
        
        for item in llm_shopping_list:
            ingredient_name = item.get('ingredient', '')
            # Try to match against our verified scraped data
            db_match = ScraperService.match_ingredient_price(ingredient_name, goal.shop, goal.country)
            
            if db_match:
                # OVERRIDE: Use DB truth over LLM guess
                item['price'] = float(db_match['price'])
                item['matched_product_name'] = db_match['display_name']
                item['currency'] = db_match['currency']
                item['package_size'] = db_match['package_size']
                item['product_unit'] = db_match['unit']
                item['estimated'] = False
                item['price_source'] = 'leaflet_db'
            else:
                item['estimated'] = True
                item['price_source'] = 'llm_browsing_fallback'

            # Standardize pricing using our package-aware math
            final_price = calculate_package_aware_price(item, context_id, goal.id)
            if final_price:
                item['price_total'] = float(final_price)
                calculated_total += final_price
            else:
                # Fallback to LLM suggested total if calculation fails
                item['price_total'] = item.get('price_total') or item.get('price')
                calculated_total += Decimal(str(item['price_total'] or 0))
                
            final_shopping_list.append(item)

        # --- PHASE 4: ATOMIC PERSISTENCE & FULFILLMENT ---
        logger.info(f"{log_prefix} Finalizing Protocol: Creating full object graph.")
        with transaction.atomic():
            # 1. Create the synthesized Plan
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
            
            # 2. Persist Recipes and MealInstances for UI tracking
            for day in days:
                day_num = day.get('day_number')
                for meal_type in ['breakfast', 'lunch', 'dinner']:
                    meal_data = day.get(meal_type)
                    if meal_data:
                        meal_id = f"{goal.id}:{day_num}:{meal_type}:0"
                        
                        recipe = Recipe.objects.create(
                            meal_identifier=meal_id,
                            dietary_goal=goal,
                            name=meal_data.get('name', 'Unnamed Meal'),
                            description=meal_data.get('description', ''),
                            instructions=meal_data.get('instructions', []),
                            ingredients=meal_data.get('ingredients', []),
                            preparation_time=meal_data.get('preparation_time'),
                            nutritional_info=meal_data.get('nutritional_info', {})
                        )
                        
                        MealInstance.objects.create(
                            user=goal.user,
                            dietary_goal=goal,
                            recipe=recipe,
                            meal_identifier=meal_id,
                            meal_name=recipe.name,
                            day_number=day_num,
                            meal_type=meal_type
                        )

            # 3. Finalize Goal State
            goal.status = DietaryGoal.StatusChoices.COMPLETED
            goal.completed_at = timezone.now()
            goal.save(update_fields=['status', 'completed_at'])

        execution_time = time.time() - start_time
        logger.info(f"{log_prefix} PROTOCOL SUCCESS. Roadmap active. ID: {plan.id}")
        return {'status': 'success', 'plan_id': plan.id}

    except Exception as exc:
        logger.error(f"{log_prefix} SYNTHESIS ABORTED: {str(exc)}")
        try:
            goal = DietaryGoal.objects.get(id=goal_id)
            goal.status = DietaryGoal.StatusChoices.FAILED
            goal.error_message = f"Protocol mapping fault: {str(exc)}"
            goal.save(update_fields=['status', 'error_message'])
        except: pass
        raise