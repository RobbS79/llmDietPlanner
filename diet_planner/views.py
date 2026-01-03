"""
API Views for dietary goals and plans.
Uses DRF APIView for class-based views.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.utils import timezone
from typing import Dict, Any

from .models import DietaryGoal, DietaryPlan, Recipe, MealInstance, get_currency_for_country
from .llm_service import OpenAIService
from .serializers import (
    DietaryGoalSerializer, 
    DietaryGoalDetailSerializer,
    RecipeSerializer,
    MealInstanceSerializer,
    MealInstanceCreateUpdateSerializer,
)
from .schemas import DietaryGoalCreateRequest, DietaryGoalCreateResponse
from .tasks import process_dietary_goal_task, build_llm_prompt_json
from celery.result import AsyncResult


class DietaryGoalCreateView(APIView):
    """
    API endpoint for creating a new dietary goal.
    Accepts user prompt and triggers async LLM processing via Celery.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request) -> Response:
        """
        Create a new dietary goal and trigger async processing.
        
        Request body:
        {
            "prompt": "I want to lose 5kg in 2 months...",
            "dietary_restrictions": "No gluten, lactose intolerant",
            "country": "PL",
            "city": "Warsaw",
            "language_code": "pl"
        }
        
        Response:
        {
            "status": "success",
            "data": {
                "goal_id": 1,
                "status": "pending",
                "message": "Dietary goal created. Processing will begin shortly."
            },
            "error": null
        }
        """
        try:
            # Validate request using Pydantic schema
            schema = DietaryGoalCreateRequest(**request.data)
            
            # Auto-determine currency from country
            currency = get_currency_for_country(schema.country.value)
            
            # Create dietary goal
            dietary_goal = DietaryGoal.objects.create(
                user=request.user,
                prompt=schema.prompt,
                dietary_restrictions=schema.dietary_restrictions,
                country=schema.country.value,
                city=schema.city,
                currency=currency,
                language_code=schema.language_code,
                num_days=schema.num_days,
                breakfast=schema.breakfast,
                lunch=schema.lunch,
                dinner=schema.dinner,
                small_meals_per_day=schema.small_meals_per_day,
                snacks_per_day=schema.snacks_per_day,
                status=DietaryGoal.StatusChoices.PENDING
            )
            
            # Trigger async Celery task for LLM processing (optional - graceful fallback if Celery unavailable)
            try:
                task = process_dietary_goal_task.delay(dietary_goal.id)
                dietary_goal.celery_task_id = task.id
                dietary_goal.save(update_fields=['celery_task_id'])
                message = "Dietary goal created. Processing will begin shortly."
            except Exception as celery_error:
                # Celery/Redis not available - log but don't fail
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Celery task could not be triggered for goal {dietary_goal.id}: {str(celery_error)}. "
                    "Goal created but processing will need to be triggered manually or when Celery is available."
                )
                message = "Dietary goal created. Note: Celery is not available - processing will need to be triggered manually."
            
            # Return standardized response with task_id for polling
            response_data: Dict[str, Any] = {
                "goal_id": dietary_goal.id,
                "status": dietary_goal.status,
                "task_id": dietary_goal.celery_task_id,
                "message": message
            }
            
            return Response(
                {
                    "status": "success",
                    "data": response_data,
                    "error": None
                },
                status=status.HTTP_201_CREATED
            )
            
        except ValueError as e:
            # Pydantic validation errors
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DietaryGoalListView(APIView):
    """
    List all dietary goals for the authenticated user.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request) -> Response:
        """
        Get list of user's dietary goals.
        """
        goals = DietaryGoal.objects.filter(
            user=request.user
        ).select_related('user').prefetch_related('dietary_plan').order_by('-created_at')
        
        serializer = DietaryGoalSerializer(goals, many=True)
        
        return Response(
            {
                "status": "success",
                "data": serializer.data,
                "error": None
            },
            status=status.HTTP_200_OK
        )


class DietaryGoalDetailView(APIView):
    """
    Retrieve details of a specific dietary goal including plan (if completed).
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, goal_id: int) -> Response:
        """
        Get detailed information about a dietary goal.
        """
        try:
            goal = DietaryGoal.objects.select_related(
                'user',
                'dietary_plan'
            ).get(id=goal_id, user=request.user)
            
            serializer = DietaryGoalDetailSerializer(goal)
            
            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None
                },
                status=status.HTTP_200_OK
            )
        except DietaryGoal.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": "Dietary goal not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            # Log the full error for debugging
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_trace = traceback.format_exc()
            logger.error(f"Error retrieving dietary goal {goal_id}: {str(e)}\n{error_trace}")
            
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred while retrieving the goal: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DietaryGoalTaskStatusView(APIView):
    """
    Check the status of a Celery task processing a dietary goal.
    Allows frontend to poll for task completion.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, goal_id: int) -> Response:
        """
        Get the status of the Celery task processing a dietary goal.
        
        Response includes:
        - task_status: PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED
        - goal_status: pending, processing, completed, failed (from DB)
        - result: Task result if completed
        """
        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
            
            # If no task ID, task wasn't started
            if not goal.celery_task_id:
                return Response(
                    {
                        "status": "success",
                        "data": {
                            "goal_id": goal_id,
                            "task_status": "NOT_STARTED",
                            "goal_status": goal.status,
                            "message": "Task was not started (Celery may not be available)"
                        },
                        "error": None
                    },
                    status=status.HTTP_200_OK
                )
            
            # Check Celery task status
            task_result = AsyncResult(goal.celery_task_id)
            
            # Map Celery states to readable status
            task_status_map = {
                'PENDING': 'pending',
                'STARTED': 'processing',
                'SUCCESS': 'completed',
                'FAILURE': 'failed',
                'RETRY': 'processing',
                'REVOKED': 'failed',
            }
            
            task_status = task_status_map.get(task_result.state, task_result.state.lower())
            
            # Get task result if available
            result_data = None
            if task_result.ready():
                if task_result.successful():
                    result_data = task_result.result
                else:
                    # Task failed
                    result_data = {
                        "error": str(task_result.info) if task_result.info else "Task failed"
                    }
            
            # Get goal status from DB (may be more up-to-date than task status)
            goal_status = goal.status
            
            return Response(
                {
                    "status": "success",
                    "data": {
                        "goal_id": goal_id,
                        "task_id": goal.celery_task_id,
                        "task_status": task_status,
                        "celery_state": task_result.state,
                        "goal_status": goal_status,
                        "result": result_data,
                        "ready": task_result.ready(),
                    },
                    "error": None
                },
                status=status.HTTP_200_OK
            )
            
        except DietaryGoal.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": "Dietary goal not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import logging
            import traceback
            logger = logging.getLogger(__name__)
            error_trace = traceback.format_exc()
            logger.error(f"Error checking task status for goal {goal_id}: {str(e)}\n{error_trace}")
            
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred while checking task status: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DietaryGoalPromptDebugView(APIView):
    """
    Debug endpoint to view the raw JSON prompt structure for a dietary goal.
    Useful for testing and verifying the LLM prompt format.
    
    Note: For MVP testing, authentication is disabled. Re-enable for production.
    """
    permission_classes = []  # Temporarily disabled for testing - re-enable IsAuthenticated for production
    
    def get(self, request, goal_id: int) -> Response:
        """
        Get the raw JSON prompt structure for a dietary goal.
        
        Response includes:
        - The structured JSON that would be sent to the LLM
        - Both as a Python dict and as a formatted JSON string
        """
        try:
            # For testing: allow access without user check. Re-enable user check for production.
            goal = DietaryGoal.objects.get(id=goal_id)
            
            # Build the JSON prompt structure
            llm_prompt_json = build_llm_prompt_json(goal)
            
            # Format as pretty JSON string
            import json
            llm_prompt_text = json.dumps(llm_prompt_json, indent=2, ensure_ascii=False)
            
            return Response(
                {
                    "status": "success",
                    "data": {
                        "goal_id": goal_id,
                        "json_object": llm_prompt_json,
                        "json_string": llm_prompt_text,
                    },
                    "error": None
                },
                status=status.HTTP_200_OK
            )
        except DietaryGoal.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": "Dietary goal not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )


class RecipeDetailView(APIView):
    """
    Get or create/update a recipe for a specific meal.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, meal_identifier: str) -> Response:
        """
        Get recipe by meal identifier.
        If recipe doesn't exist, auto-create it from meal data in dietary plan.
        """
        try:
            # Try to get existing recipe
            try:
                recipe = Recipe.objects.select_related('dietary_goal').get(
                    meal_identifier=meal_identifier,
                    dietary_goal__user=request.user
                )
                
                serializer = RecipeSerializer(recipe)
                
                return Response(
                    {
                        "status": "success",
                        "data": serializer.data,
                        "error": None
                    },
                    status=status.HTTP_200_OK
                )
            except Recipe.DoesNotExist:
                # Recipe doesn't exist - try to create it from meal data
                # Parse meal identifier: format is "goal_id:day_number:meal_type:meal_index"
                parts = meal_identifier.split(':')
                if len(parts) != 4:
                    return Response(
                        {
                            "status": "error",
                            "data": None,
                            "error": "Invalid meal identifier format"
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                goal_id, day_number_str, meal_type, meal_index_str = parts
                try:
                    goal_id = int(goal_id)
                    day_number = int(day_number_str)
                    meal_index = int(meal_index_str)
                except ValueError:
                    return Response(
                        {
                            "status": "error",
                            "data": None,
                            "error": "Invalid meal identifier format"
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Get dietary goal and plan
                try:
                    dietary_goal = DietaryGoal.objects.select_related('dietary_plan').get(
                        id=goal_id,
                        user=request.user
                    )
                except DietaryGoal.DoesNotExist:
                    return Response(
                        {
                            "status": "error",
                            "data": None,
                            "error": "Dietary goal not found"
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Check if dietary plan exists
                if not hasattr(dietary_goal, 'dietary_plan') or not dietary_goal.dietary_plan:
                    return Response(
                        {
                            "status": "error",
                            "data": None,
                            "error": "Dietary plan not found"
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                plan = dietary_goal.dietary_plan
                days = plan.days if plan.days else []
                
                # Find the meal in the days data
                meal_data = None
                for day in days:
                    if day.get('day_number') == day_number:
                        # Check main meals (breakfast, lunch, dinner)
                        if meal_type in ['breakfast', 'lunch', 'dinner'] and meal_index == 0:
                            meal_data = day.get(meal_type)
                        # Check small_meals array
                        elif meal_type == 'small_meal' and meal_index < len(day.get('small_meals', [])):
                            meal_data = day.get('small_meals', [])[meal_index]
                        # Check snacks array
                        elif meal_type == 'snack' and meal_index < len(day.get('snacks', [])):
                            meal_data = day.get('snacks', [])[meal_index]
                        break
                
                if not meal_data:
                    return Response(
                        {
                            "status": "error",
                            "data": None,
                            "error": "Meal not found in dietary plan"
                        },
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Get instructions from meal data, or generate them using LLM if missing
                instructions = meal_data.get('instructions', [])
                if not instructions or (isinstance(instructions, list) and len(instructions) == 0):
                    # Try to generate proper instructions using LLM
                    meal_name = meal_data.get('name', 'this meal')
                    ingredients = meal_data.get('ingredients', [])
                    description = meal_data.get('description', '')
                    
                    try:
                        llm_service = OpenAIService()
                        instructions = llm_service.generate_recipe_instructions(
                            meal_name=meal_name,
                            ingredients=ingredients,
                            description=description,
                            language_code=dietary_goal.language_code
                        )
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Failed to generate LLM instructions for {meal_name}: {e}")
                        instructions = []
                    
                    # Fallback to basic instructions if LLM generation failed or returned empty
                    if not instructions:
                        prep_time = meal_data.get('preparation_time', 10)
                        if meal_type == 'breakfast':
                            instructions = [
                                "Prepare all ingredients and cooking equipment",
                                f"Follow standard breakfast preparation methods for {meal_name}",
                                f"Cook for approximately {prep_time} minutes or until done",
                                "Plate and serve immediately while warm"
                            ]
                        elif meal_type == 'lunch':
                            instructions = [
                                "Wash and prepare all fresh ingredients",
                                f"Cook {meal_name} following standard lunch preparation techniques",
                                f"Allow {prep_time} minutes for preparation and cooking",
                                "Check doneness and adjust seasoning if needed",
                                "Serve hot and enjoy"
                            ]
                        elif meal_type == 'dinner':
                            instructions = [
                                "Preheat any necessary cooking equipment",
                                "Prepare and measure all ingredients",
                                f"Cook {meal_name} following the recipe method",
                                f"Cook for approximately {prep_time} minutes, checking periodically",
                                "Ensure all components are properly cooked",
                                "Plate attractively and serve"
                            ]
                        else:
                            instructions = [
                                "Gather all ingredients",
                                f"Prepare {meal_name} according to standard methods",
                                f"Allow {prep_time} minutes for preparation",
                                "Serve and enjoy"
                            ]
                
                # Create recipe from meal data
                recipe = Recipe.objects.create(
                    meal_identifier=meal_identifier,
                    dietary_goal=dietary_goal,
                    name=meal_data.get('name', 'Unnamed Meal'),
                    description=meal_data.get('description', ''),
                    instructions=instructions,
                    ingredients=meal_data.get('ingredients', []),
                    preparation_time=meal_data.get('preparation_time'),
                    cooking_time=meal_data.get('cooking_time'),  # May not exist in meal data
                    servings=meal_data.get('servings', 1),
                    nutritional_info=meal_data.get('nutritional_info', {}),
                )
                
                serializer = RecipeSerializer(recipe)
                
                return Response(
                    {
                        "status": "success",
                        "data": serializer.data,
                        "error": None
                    },
                    status=status.HTTP_201_CREATED
                )
                
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error retrieving/creating recipe {meal_identifier}: {str(e)}", exc_info=True)
            
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request, meal_identifier: str) -> Response:
        """
        Create or update a recipe for a meal.
        Requires goal_id, day_number, meal_type, and meal_index in request data.
        """
        try:
            # Extract meal info from identifier or request data
            goal_id = request.data.get('goal_id')
            day_number = request.data.get('day_number')
            meal_type = request.data.get('meal_type')
            meal_index = request.data.get('meal_index', 0)
            
            if not all([goal_id, day_number, meal_type]):
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Missing required fields: goal_id, day_number, meal_type"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify the dietary goal belongs to the user
            try:
                dietary_goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
            except DietaryGoal.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Dietary goal not found"
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Create or update recipe
            recipe, created = Recipe.objects.update_or_create(
                meal_identifier=meal_identifier,
                defaults={
                    'dietary_goal': dietary_goal,
                    'name': request.data.get('name', ''),
                    'description': request.data.get('description', ''),
                    'instructions': request.data.get('instructions', []),
                    'ingredients': request.data.get('ingredients', []),
                    'preparation_time': request.data.get('preparation_time'),
                    'cooking_time': request.data.get('cooking_time'),
                    'servings': request.data.get('servings', 1),
                    'nutritional_info': request.data.get('nutritional_info', {}),
                }
            )
            
            serializer = RecipeSerializer(recipe)
            
            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None
                },
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating/updating recipe {meal_identifier}: {str(e)}", exc_info=True)
            
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MealInstanceView(APIView):
    """
    Get or create/update a meal instance (for marking as cooked).
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, meal_identifier: str) -> Response:
        """
        Get meal instance by meal identifier for the current user.
        """
        try:
            meal_instance = MealInstance.objects.select_related(
                'recipe', 'dietary_goal', 'user'
            ).get(
                meal_identifier=meal_identifier,
                user=request.user
            )
            
            serializer = MealInstanceSerializer(meal_instance)
            
            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None
                },
                status=status.HTTP_200_OK
            )
        except MealInstance.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": "Meal instance not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error retrieving meal instance {meal_identifier}: {str(e)}", exc_info=True)
            
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request, meal_identifier: str) -> Response:
        """
        Create or update a meal instance (mark as cooked/un cooked).
        """
        try:
            # Extract required fields
            goal_id = request.data.get('goal_id')
            meal_name = request.data.get('meal_name', '')
            day_number = request.data.get('day_number')
            meal_type = request.data.get('meal_type')
            
            if not all([goal_id, day_number, meal_type]):
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Missing required fields: goal_id, day_number, meal_type"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify the dietary goal belongs to the user
            try:
                dietary_goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
            except DietaryGoal.DoesNotExist:
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Dietary goal not found"
                    },
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Get recipe if it exists
            recipe = None
            try:
                recipe = Recipe.objects.get(meal_identifier=meal_identifier)
            except Recipe.DoesNotExist:
                pass
            
            # Determine if cooked
            is_cooked = request.data.get('is_cooked', False)
            cooked_at = timezone.now() if is_cooked else None
            
            # Create or update meal instance
            meal_instance, created = MealInstance.objects.update_or_create(
                meal_identifier=meal_identifier,
                user=request.user,
                defaults={
                    'dietary_goal': dietary_goal,
                    'recipe': recipe,
                    'meal_name': meal_name,
                    'day_number': day_number,
                    'meal_type': meal_type,
                    'is_cooked': is_cooked,
                    'cooked_at': cooked_at,
                    'notes': request.data.get('notes', ''),
                }
            )
            
            serializer = MealInstanceSerializer(meal_instance)
            
            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None
                },
                status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating/updating meal instance {meal_identifier}: {str(e)}", exc_info=True)
            
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MealInstanceCookedListView(APIView):
    """
    List all cooked meals for the authenticated user.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request) -> Response:
        """
        Get list of cooked meals for the user.
        Optional query params: goal_id, limit, offset
        """
        try:
            queryset = MealInstance.objects.filter(
                user=request.user,
                is_cooked=True
            ).select_related('recipe', 'dietary_goal').order_by('-cooked_at')
            
            # Filter by goal if provided
            goal_id = request.query_params.get('goal_id')
            if goal_id:
                queryset = queryset.filter(dietary_goal_id=goal_id)
            
            # Pagination
            limit = int(request.query_params.get('limit', 50))
            offset = int(request.query_params.get('offset', 0))
            queryset = queryset[offset:offset + limit]
            
            serializer = MealInstanceSerializer(queryset, many=True)
            
            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error retrieving cooked meals: {str(e)}", exc_info=True)
            
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
