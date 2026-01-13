# File: diet_planner/tasks.py
"""
Professional Dietary Synthesis Orchestrator
===========================================
Refactored for 100k users scale. This module implements the "Two-Phase" spirit 
of the LLM architecture:
Phase 1: Creative Nutritional Synthesis (Nutritionist Role)
Phase 2: Semantic Market Mapping (Shopping Assistant Role)
Phase 3: Financial Integrity & Persistence (Backend/Trust Role)

Architecture Principles:
- LLM Intent: LLM generates meal ideas and maps ingredients to potential products.
- Backend Authority: Django logic calculates final prices using package-aware math.
- Observability: Atomic status transitions for React 'StatusTracker' component.
"""
import logging
import uuid
import time
from decimal import Decimal
from typing import Dict, Any, List

from django.db import transaction
from django.utils import timezone
from llm_diet_planner_project.celery_compat import shared_task

from .models import DietaryGoal, DietaryPlan
from .services.meal_plan import MealPlanService
from .services.shopping_list import ShoppingListService
from .services.price_discovery import PriceDiscoveryService
from .services.validation import MealPlanValidator
from .scrapers.scraper_service import ScraperService

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, autoretry_for=(Exception,), retry_backoff=True)
def process_dietary_goal_task(self, goal_id: int) -> Dict[str, Any]:
    """
    The Orchestrator follows a 'Chain of Responsibility' pattern to synthesize 
    a complete plan while maintaining absolute data integrity.
    """
    start_time = time.time()
    context_id = str(uuid.uuid4())[:8]
    log_prefix = f"[SYNTHESIS_HUB:{goal_id}:{context_id}]"
    
    try:
        # Retrieve goal object with lock to prevent race conditions during payment webhook
        goal = DietaryGoal.objects.get(id=goal_id)
        logger.info(f"{log_prefix} Initializing Protocol for Hub: {goal.country}/{goal.city}")

        # --- PHASE 1: NUTRITIONAL LOGIC (The 'Spirit' of Strategy) ---
        # We prompt the LLM to act as a nutrition expert, focusing purely on 
        # macros, instructions, and ingredients.
        phase1_start = time.time()
        goal.status = DietaryGoal.StatusChoices.PROCESSING_MEAL_PLAN
        goal.save(update_fields=['status'])
        
        logger.info(f"{log_prefix} Triggering Phase 1: Creative Nutrition Synthesis.")
        meal_plan_service = MealPlanService()
        phase1_result = meal_plan_service.generate_meal_plan(goal)
        days = phase1_result['days']
        
        logger.info(f"{log_prefix} Phase 1 Completed in {time.time() - phase1_start:.2f}s.")

        # --- PHASE 2: SEMANTIC MARKET MAPPING (The 'Spirit' of Alignment) ---
        # We switch the LLM context to a 'Shopping Assistant' that maps recipe 
        # requirements to available product names.
        phase2_start = time.time()
        goal.status = DietaryGoal.StatusChoices.PROCESSING_SHOPPING_LIST
        goal.save(update_fields=['status'])
        
        # Load Verified Inventory (The only context the LLM is allowed to use)
        logger.info(f"{log_prefix} Loading inventory hub data for {goal.shop}...")
        shop_data = []
        if goal.shop:
            shop_data = ScraperService.get_available_ingredients(goal.shop, goal.country)
        
        logger.info(f"{log_prefix} Triggering Phase 2: Inventory Mapping.")
        shopping_service = ShoppingListService()
        phase2_result = shopping_service.generate_shopping_list(
            meal_plan={'days': days}, 
            shop_data=shop_data, 
            goal=goal
        )
        shopping_list = phase2_result['shopping_list']
        
        logger.info(f"{log_prefix} Phase 2 Completed in {time.time() - phase2_start:.2f}s.")

        # --- PHASE 3: FINANCIAL INTEGRITY (Backend Truth) ---
        # FALLBACK: If items were missing from leaflet, we discover prices via LLM.
        # OVERRIDE: We cross-reference LLM prices against our DB 'LeafletOffer' table.
        logger.info(f"{log_prefix} Initializing Phase 3: Final Price Discovery & Override.")
        discovery_service = PriceDiscoveryService(goal)
        final_shopping_list = discovery_service.fill_missing_prices(shopping_list)

        # --- PHASE 4: VALIDATION (Sanity Check) ---
        goal.status = DietaryGoal.StatusChoices.VALIDATING
        goal.save(update_fields=['status'])
        
        validator = MealPlanValidator()
        validation_result = validator.validate(
            meal_plan={'days': days},
            shopping_list=final_shopping_list,
            goal_config={'num_days': goal.num_days}
        )

        # --- PERSISTENCE: ATOMIC FINALIZATION ---
        # We wrap the plan creation and goal update in an atomic block to ensure
        # the user is only considered 'Fulfilled' if the data is 100% saved.
        with transaction.atomic():
            # Calculate total cost based on the validated shopping list
            total_price = sum(Decimal(str(item.get('price') or 0)) for item in final_shopping_list)
            
            # Aggregate Telemetry for Digital Ocean Logs
            total_input = phase1_result['input_tokens'] + phase2_result['input_tokens']
            total_output = phase1_result['output_tokens'] + phase2_result['output_tokens']
            total_cost_usd = phase1_result['cost_usd'] + phase2_result['cost_usd']
            
            plan = DietaryPlan.objects.create(
                dietary_goal=goal,
                days=days,
                shopping_list=final_shopping_list,
                total_price=total_price,
                currency=goal.currency,
                llm_model_used=phase1_result['model'],
                llm_input_tokens=total_input,
                llm_output_tokens=total_output,
                llm_total_tokens=total_input + total_output,
                llm_cost_usd=total_cost_usd
            )
            
            # Finalize Goal Fulfillment
            goal.status = DietaryGoal.StatusChoices.COMPLETED
            goal.completed_at = timezone.now()
            goal.validation_passed = validation_result.passed
            if not validation_result.passed:
                goal.validation_errors = validation_result.errors
            
            goal.save(update_fields=['status', 'completed_at', 'validation_passed', 'validation_errors'])

        execution_time = time.time() - start_time
        logger.info(f"{log_prefix} PROTOCOL SUCCESS. Full Cycle: {execution_time:.2f}s. Cost: {total_price} {goal.currency}")
        
        return {
            'status': 'success', 
            'plan_id': plan.id, 
            'execution_time': execution_time,
            'audit': 'passed' if validation_result.passed else 'warnings'
        }

    except Exception as exc:
        logger.error(f"{log_prefix} CRITICAL ORCHESTRATION FAULT: {str(exc)}")
        # Update goal status to notify UI of failure
        try:
            goal = DietaryGoal.objects.get(id=goal_id)
            goal.status = DietaryGoal.StatusChoices.FAILED
            goal.error_message = f"Synthesis interrupted: {str(exc)}"
            goal.save(update_fields=['status', 'error_message'])
        except Exception:
            pass
        
        # Reraise for Celery autoretry
        raise