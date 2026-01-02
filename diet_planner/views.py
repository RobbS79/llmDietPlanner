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

from .models import DietaryGoal, DietaryPlan, get_currency_for_country
from .serializers import DietaryGoalSerializer, DietaryGoalDetailSerializer
from .schemas import DietaryGoalCreateRequest, DietaryGoalCreateResponse
from .tasks import process_dietary_goal_task, build_llm_prompt_json


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
                status=DietaryGoal.StatusChoices.PENDING
            )
            
            # Trigger async Celery task for LLM processing
            task = process_dietary_goal_task.delay(dietary_goal.id)
            dietary_goal.celery_task_id = task.id
            dietary_goal.save(update_fields=['celery_task_id'])
            
            # Return standardized response
            response_data: Dict[str, Any] = {
                "goal_id": dietary_goal.id,
                "status": dietary_goal.status,
                "message": "Dietary goal created. Processing will begin shortly."
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
                'user'
            ).prefetch_related(
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
