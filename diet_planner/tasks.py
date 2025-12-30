"""
Celery tasks for async LLM processing.
Handles dietary goal processing, meal idea generation, and shopping list creation.
"""
from celery import shared_task
from django.utils import timezone
from typing import Dict, Any, List
import json

from .models import DietaryGoal, DietaryPlan
from .schemas import DietaryPlanResponse, MealIdea, ShoppingListItem


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
        
        # TODO: Integrate with LLM API (OpenAI, Anthropic, etc.)
        # For now, using placeholder logic
        # This is where you would call your LLM service
        
        # Example LLM prompt structure (following XML tag pattern from .cursorrules)
        llm_prompt = f"""
        Generate a personalised diet plan based on the following user requirements:
        
        <user_prompt>
        {goal.prompt}
        </user_prompt>
        
        <dietary_restrictions>
        {goal.dietary_restrictions or 'None specified'}
        </dietary_restrictions>
        
        <currency>
        {goal.currency}
        </currency>
        
        <language>
        {goal.language_code}
        </language>
        
        Please provide:
        1. Meal ideas with ingredients
        2. A shopping list with ingredients (quantities are optional)
        
        Return the response in this XML structure:
        <meal_ideas>
            <meal>
                <name>Meal name</name>
                <description>Description</description>
                <ingredients>
                    <ingredient>Ingredient 1</ingredient>
                    <ingredient>Ingredient 2</ingredient>
                </ingredients>
                <preparation_time>30</preparation_time>
                <nutritional_info>
                    <calories>500</calories>
                    <protein>30g</protein>
                </nutritional_info>
            </meal>
        </meal_ideas>
        
        <shopping_list>
            <item>
                <ingredient>Ingredient name</ingredient>
                <quantity>500</quantity>
                <unit>g</unit>
                <notes>Optional notes</notes>
            </item>
        </shopping_list>
        """
        
        # Placeholder: Replace this with actual LLM API call
        # llm_response = call_llm_api(llm_prompt)
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
