"""
Celery tasks for async LLM processing.
Handles dietary goal processing, meal idea generation, and shopping list creation.
"""
from celery import shared_task
from django.utils import timezone
from typing import Dict, Any, List
import json
import logging

from .models import DietaryGoal, DietaryPlan
from .schemas import DietaryPlanResponse, MealIdea, ShoppingListItem

logger = logging.getLogger(__name__)


def build_llm_prompt_json(goal: DietaryGoal) -> Dict[str, Any]:
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
        "instructions": {
            "output_format": "json",
            "required_outputs": ["meal_ideas", "shopping_list"],
            ...
        }
    }
    
    Args:
        goal: DietaryGoal instance with user input
        
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
        "instructions": {
            "output_format": "json",
            "required_outputs": [
                "meal_ideas",
                "shopping_list"
            ],
            "meal_ideas_requirements": {
                "include": [
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
                    "notes"
                ],
                "notes": "Quantities are optional but recommended. Use metric units (g, kg, ml, l)."
            },
            "context_notes": [
                "Ingredients should be available in local supermarkets (Lidl, Biedronka, Kaufland, etc.)",
                "Consider local cuisine preferences for the specified country",
                "Prices will be calculated separately by the system - do not include prices",
                "Focus on creating practical, achievable meal plans"
            ]
        }
    }
    
    return prompt_data


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
        
        # Build structured JSON prompt for LLM
        llm_prompt_json = build_llm_prompt_json(goal)
        
        # Convert JSON to string for LLM prompt (with pretty formatting for readability)
        llm_prompt_text = json.dumps(llm_prompt_json, indent=2, ensure_ascii=False)
        
        # Log the JSON prompt for debugging (can be viewed in Celery logs)
        logger.info(f"LLM Prompt JSON for goal {goal_id}:\n{llm_prompt_text}")
        
        # TODO: Integrate with LLM API (OpenAI, Anthropic, etc.)
        # Example usage:
        # llm_response = call_llm_api(
        #     system_prompt="You are a nutrition expert creating personalised diet plans...",
        #     user_prompt=llm_prompt_text,
        #     response_format="json"
        # )
        # For now, using mock data
        llm_response = generate_mock_llm_response()
        
        # Parse LLM response and create dietary plan
        meal_ideas_data = llm_response.get('meal_ideas', [])
        shopping_list_data = llm_response.get('shopping_list', [])
        
        # Create dietary plan
        dietary_plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            meal_ideas=meal_ideas_data,
            shopping_list=shopping_list_data,
            currency=goal.currency
        )
        
        # TODO: Trigger price calculation task (separate Celery task)
        # calculate_prices_task.delay(dietary_plan.id)
        
        # Update goal status to completed
        goal.status = DietaryGoal.StatusChoices.COMPLETED
        goal.completed_at = timezone.now()
        goal.save(update_fields=['status', 'completed_at'])
        
        return {
            'status': 'success',
            'goal_id': goal_id,
            'plan_id': dietary_plan.id
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
        'meal_ideas': [
            {
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
            {
                'name': 'Vegetable Stir Fry',
                'description': 'Mixed vegetables with tofu',
                'ingredients': ['tofu', 'broccoli', 'bell peppers', 'carrots', 'soy sauce'],
                'preparation_time': 20,
                'nutritional_info': {
                    'calories': 320,
                    'protein': '20g',
                    'carbs': '35g',
                    'fat': '12g'
                }
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
