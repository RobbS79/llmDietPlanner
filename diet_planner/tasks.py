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
from .llm_service import OpenAIService

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
            "meal_plan_type": "day_by_day_meal_plan",
            "meal_plan_configuration": {
                "num_days": goal.num_days,
                "main_courses_per_day": goal.main_courses_per_day,
                "small_meals_per_day": goal.small_meals_per_day,
                "snacks_per_day": goal.snacks_per_day
            },
            "required_outputs": [
                "days",
                "shopping_list"
            ],
            "day_plan_requirements": {
                "structure": "Each day must have exactly:",
                "main_courses": {
                    "count_per_day": goal.main_courses_per_day,
                    "description": "Main courses/recipes for each day"
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
                    "notes"
                ],
                "notes": "Quantities are optional but recommended. Use metric units (g, kg, ml, l). Aggregate quantities for the entire meal plan across all days."
            },
            "context_notes": [
                f"This is a {goal.num_days}-day meal plan. Generate exactly {goal.main_courses_per_day} main course(s), {goal.small_meals_per_day} small meal(s), and {goal.snacks_per_day} snack(s) for EACH day.",
                "Structure the output as a 'days' array, where each day has 'day_number', 'main_courses', 'small_meals', and 'snacks' arrays.",
                "Ingredients should be available in local supermarkets (Lidl, Biedronka, Kaufland, etc.)",
                "Consider local cuisine preferences for the specified country",
                "Prices will be calculated separately by the system - do not include prices",
                "Focus on creating practical, achievable meal plans that can be prepared by someone with basic cooking skills",
                "Ensure variety across days to prevent meal fatigue",
                f"Generate recipes in {goal.language_code} language"
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
            llm_result = {
                'input_tokens': None,
                'output_tokens': None,
                'total_tokens': None,
                'cost_usd': None,
                'model': None,
            }
        
        # Create dietary plan with LLM usage tracking
        dietary_plan = DietaryPlan.objects.create(
            dietary_goal=goal,
            days=days_data,
            shopping_list=shopping_list_data,
            currency=goal.currency,
            llm_input_tokens=llm_result.get('input_tokens'),
            llm_output_tokens=llm_result.get('output_tokens'),
            llm_total_tokens=llm_result.get('total_tokens'),
            llm_cost_usd=llm_result.get('cost_usd'),
            llm_model_used=llm_result.get('model'),
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
                'main_courses': [
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
                    }
                ],
                'small_meals': [
                    {
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
