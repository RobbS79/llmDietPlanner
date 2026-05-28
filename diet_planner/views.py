# File: diet_planner/views.py
"""
API Views for dietary goals and plans.
Uses DRF APIView for class-based views to maintain strict control over logic flow.
Handles asynchronous task triggering (Celery) and partial "Draft" saves for UI persistence.
"""
import logging
import traceback
from typing import Dict, Any, List, Optional

from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth.models import User
from .food_categories import guess_category
from django.utils import timezone

from .models import (
    DietaryGoal,
    DietaryPlan,
    Recipe,
    MealInstance,
    GroceryStore,
    PriceFeedback,
    HistoricNutritionPlan,
    get_currency_for_country,
    get_shops_for_country,
    SHOP_CHOICES
)
from .serializers import (
    DietaryGoalSerializer,
    DietaryGoalDetailSerializer,
    RecipeSerializer,
    MealInstanceSerializer,
    MealInstanceCreateUpdateSerializer,
    HistoricNutritionPlanSerializer,
)
from .schemas import DietaryGoalCreateRequest
from .tasks import process_dietary_goal_task, process_dietary_goal_catalog_task, build_llm_prompt_json, optimize_plan_discounts_task, process_protocol_pdf_task
from llm_diet_planner_project.celery_compat import AsyncResult, is_celery_available
from login_app.models import UserProfile

logger = logging.getLogger(__name__)

class DietaryGoalCreateView(APIView):
    """
    API endpoint for creating or updating a dietary goal.
    Supports 'is_draft' for partial saves of Section I (Objectives/Hub).
    When 'is_draft' is False, triggers full Pydantic validation and Celery worker.
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request) -> Response:
        try:
            is_partial = request.data.get('is_draft', False)
            goal_id = request.data.get('goal_id')
            
            # 1. DRAFT PERSISTENCE LOGIC (Section I Save)
            # This allows the UI to save progress without triggering the LLM or failing validation.
            if is_partial:
                defaults = {
                    'prompt': request.data.get('prompt', ''),
                    'country': request.data.get('country', 'CZ'),
                    'city': request.data.get('city', ''),
                    'status': DietaryGoal.StatusChoices.PENDING,
                }
                
                if goal_id:
                    goal, created = DietaryGoal.objects.update_or_create(
                        id=goal_id, user=request.user,
                        defaults=defaults
                    )
                else:
                    goal = DietaryGoal.objects.create(user=request.user, **defaults)
                
                return Response({
                    "status": "success", 
                    "data": {"goal_id": goal.id, "status": goal.status}
                }, status=status.HTTP_201_CREATED)

            # 2. FINAL SYNTHESIS LOGIC (Full Validation + Task Trigger)
            # Strict validation using Pydantic DietaryGoalCreateRequest schema
            schema = DietaryGoalCreateRequest(**request.data)

            # Auto-determine currency from Hub selection
            currency = get_currency_for_country(schema.country.value)

            # Verification of generation credits
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            is_free_generation = profile.has_free_generations()

            # Mapping validated schema to model fields
            goal_data = {
                'prompt': schema.prompt,
                'dietary_restrictions': schema.dietary_restrictions,
                'country': schema.country.value,
                'city': schema.city,
                'currency': currency,
                'language_code': schema.language_code,
                'num_days': schema.num_days,
                'breakfast': schema.breakfast,
                'lunch': schema.lunch,
                'dinner': schema.dinner,
                'small_meals_per_day': schema.small_meals_per_day,
                'snacks_per_day': schema.snacks_per_day,
                'shop': schema.shop.value if schema.shop else None,
                'store_mode': schema.store_mode.value if schema.store_mode else 'single',
                'status': DietaryGoal.StatusChoices.PENDING,
                'is_free_generation': is_free_generation,
            }

            if schema.historic_plan_id:
                protocol = HistoricNutritionPlan.objects.filter(
                    id=schema.historic_plan_id,
                    user=request.user,
                    processing_status='completed',
                ).first()
                if protocol:
                    goal_data['historic_plan_reference_id'] = protocol.id
                else:
                    return Response(
                        {"status": "error", "error": "Selected protocol not found or not yet processed"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Update existing draft or create new entry
            if goal_id:
                dietary_goal = DietaryGoal.objects.filter(id=goal_id, user=request.user).first()
                if dietary_goal:
                    for key, value in goal_data.items():
                        setattr(dietary_goal, key, value)
                    dietary_goal.save()
                else:
                    dietary_goal = DietaryGoal.objects.create(user=request.user, **goal_data)
            else:
                dietary_goal = DietaryGoal.objects.create(user=request.user, **goal_data)

            # Decrement credits only on full successful creation
            if is_free_generation:
                profile.use_free_generation()

            # Trigger Background Synthesis
            try:
                use_catalog = getattr(settings, 'CATALOG_CONSTRAINED_GENERATION', False)
                if use_catalog:
                    task = process_dietary_goal_catalog_task.delay(dietary_goal.id)
                else:
                    task = process_dietary_goal_task.delay(dietary_goal.id)
                dietary_goal.celery_task_id = task.id
                dietary_goal.save(update_fields=['celery_task_id'])
                message = "Synthesis protocol initiated."
            except Exception as celery_error:
                logger.error(f"Task Fault: {str(celery_error)}")
                message = "Goal stored. Async worker unreachable. Retrying locally..."
            
            return Response(
                {
                    "status": "success",
                    "data": {
                        "goal_id": dietary_goal.id,
                        "status": dietary_goal.status,
                        "task_id": dietary_goal.celery_task_id,
                        "message": message
                    }
                },
                status=status.HTTP_201_CREATED
            )
            
        except ValueError as e:
            logger.warning(f"Validation error: {e}")
            return Response({"status": "error", "error": "Invalid input parameters"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unhandled View Error: {traceback.format_exc()}")
            return Response({"status": "error", "error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DietaryGoalListView(APIView):
    """
    Retrieves all dietary strategies for the user.
    Optimized with prefetch_related for the 100k user scale.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        goals = DietaryGoal.objects.filter(
            user=request.user
        ).select_related('user').prefetch_related('dietary_plan').order_by('-created_at')

        serializer = DietaryGoalSerializer(goals, many=True)
        return Response({"status": "success", "data": serializer.data}, status=status.HTTP_200_OK)


class DietaryGoalBulkDeleteView(APIView):
    """Bulk delete dietary goals by list of IDs. Only deletes goals owned by the requesting user."""
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        goal_ids = request.data.get('goal_ids', [])
        if not goal_ids or not isinstance(goal_ids, list):
            return Response({"status": "error", "error": "goal_ids must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)

        goals = DietaryGoal.objects.filter(id__in=goal_ids, user=request.user)
        deleted_count = goals.count()
        goals.delete()

        return Response({"status": "success", "data": {"deleted": deleted_count}}, status=status.HTTP_200_OK)


class DietaryGoalDetailView(APIView):
    """
    Detailed object retrieval including synthesized plan results.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.select_related('user', 'dietary_plan').get(id=goal_id, user=request.user)
            return Response({"status": "success", "data": DietaryGoalDetailSerializer(goal).data})
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Object not found"}, status=status.HTTP_404_NOT_FOUND)


class DietaryGoalTaskStatusView(APIView):
    """
    Polling endpoint for frontend to track Gemini/Celery state.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
            
            if not goal.celery_task_id:
                return Response({"status": "success", "data": {"goal_id": goal_id, "task_status": "IDLE", "goal_status": goal.status}})
            
            if not is_celery_available():
                return Response({"status": "success", "data": {"goal_id": goal_id, "task_status": "CELERY_OFFLINE", "goal_status": goal.status}})
            
            task_result = AsyncResult(goal.celery_task_id)
            return Response({
                "status": "success",
                "data": {
                    "goal_id": goal_id,
                    "task_status": task_result.state,
                    "goal_status": goal.status,
                    "ready": task_result.ready(),
                    "error_message": goal.error_message,
                }
            })
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)


class DietaryGoalPromptDebugView(APIView):
    """
    Debug tool to inspect raw JSON prompt construction.
    Restricted to admin users only.
    """
    permission_classes = [IsAdminUser]

    def get(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.get(id=goal_id)
            llm_prompt_json = build_llm_prompt_json(goal)
            return Response({"status": "success", "data": {"goal_id": goal_id, "json_object": llm_prompt_json}})
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)


class AdminRetryGoalView(APIView):
    """Retry or fail a stuck goal. Users can retry their own goals."""
    permission_classes = [IsAuthenticated]

    def post(self, request, goal_id: int) -> Response:
        action = request.data.get('action', 'retry')
        try:
            if request.user.is_staff:
                goal = DietaryGoal.objects.get(id=goal_id)
            else:
                goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)

        if action == 'fail':
            goal.status = DietaryGoal.StatusChoices.FAILED
            goal.error_message = request.data.get('reason', 'Manually marked as failed by admin')
            goal.save(update_fields=['status', 'error_message'])
            return Response({"status": "success", "data": {"goal_id": goal_id, "new_status": "failed"}})

        goal.status = DietaryGoal.StatusChoices.PENDING
        goal.error_message = ''
        goal.save(update_fields=['status', 'error_message'])
        try:
            task = process_dietary_goal_task.delay(goal_id)
            goal.celery_task_id = task.id
            goal.save(update_fields=['celery_task_id'])
            return Response({"status": "success", "data": {"goal_id": goal_id, "new_status": "pending", "task_id": task.id}})
        except Exception as e:
            return Response({"status": "error", "error": f"Celery unavailable: {e}"}, status=503)


class ShopsListView(APIView):
    """
    Public inventory hub retrieval.
    """
    permission_classes = []
    def get(self, request) -> Response:
        country = request.query_params.get('country')
        if not country:
            return Response({"status": "error", "error": "Hub ID required"}, status=400)

        shop_codes = get_shops_for_country(country)
        shop_choices_dict = dict(SHOP_CHOICES)

        db_stores = {s.code: s for s in GroceryStore.objects.filter(code__in=shop_codes, is_active=True)}

        shops = []
        for code in shop_codes:
            store = db_stores.get(code)
            shops.append({
                "code": code,
                "name": store.name if store else shop_choices_dict.get(code, code),
                "is_online_only": store.is_online_only if store else False,
            })

        return Response({"status": "success", "data": {"country": country, "shops": shops}})


class RecipeDetailView(APIView):
    """
    Synthesized recipe instructions.
    Returns existing recipe or generates one on-demand from the meal plan data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, meal_identifier: str) -> Response:
        # Return existing recipe if available
        try:
            recipe = Recipe.objects.get(meal_identifier=meal_identifier, dietary_goal__user=request.user)
            return Response({"status": "success", "data": RecipeSerializer(recipe).data})
        except Recipe.DoesNotExist:
            pass

        # Generate on-demand: parse meal_identifier (format: goal_id:day_number:meal_type:index)
        try:
            parts = meal_identifier.split(':')
            if len(parts) < 3:
                return Response({"status": "error", "error": "Invalid meal identifier"}, status=400)
            goal_id, day_number, meal_type = int(parts[0]), int(parts[1]), parts[2]
        except (ValueError, IndexError):
            return Response({"status": "error", "error": "Invalid meal identifier format"}, status=400)

        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)

        try:
            plan = goal.dietary_plan
        except DietaryPlan.DoesNotExist:
            return Response({"status": "error", "error": "Plan not found"}, status=404)

        # Find the meal in plan days
        meal = None
        for day in (plan.days or []):
            if day.get('day_number') == day_number:
                meal = day.get(meal_type)
                break
        if not meal:
            return Response({"status": "error", "error": "Meal not found in plan"}, status=404)

        # Generate cooking instructions via LLM
        from .llm_service import GeminiService
        try:
            llm_service = GeminiService()
            ingredient_names = []
            for ing in meal.get('ingredients', []):
                if isinstance(ing, dict):
                    ingredient_names.append(ing.get('name', str(ing)))
                else:
                    ingredient_names.append(str(ing))

            instructions = llm_service.generate_recipe_instructions(
                meal_name=meal.get('name', ''),
                ingredients=ingredient_names,
                description=meal.get('description', ''),
                language_code=goal.language_code,
            )
        except Exception as e:
            logger.error(f"Failed to generate recipe instructions for {meal_identifier}: {e}")
            instructions = []

        # Store recipe for future requests
        recipe = Recipe.objects.create(
            meal_identifier=meal_identifier,
            dietary_goal=goal,
            name=meal.get('name', ''),
            description=meal.get('description', ''),
            food_category=meal.get('food_category', '') or guess_category(meal.get('name', ''), meal.get('ingredients', [])),
            instructions=instructions,
            ingredients=meal.get('ingredients', []),
            preparation_time=meal.get('preparation_time'),
            nutritional_info=meal.get('nutritional_info', {}),
        )
        return Response({"status": "success", "data": RecipeSerializer(recipe).data})


class MealInstanceView(APIView):
    """
    Individual meal execution state (Cooked/Pending).
    Supports GET (read) and PATCH (toggle cooked / update notes).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, meal_identifier: str) -> Response:
        try:
            instance = MealInstance.objects.get(meal_identifier=meal_identifier, user=request.user)
            return Response({"status": "success", "data": MealInstanceSerializer(instance).data})
        except MealInstance.DoesNotExist:
            return Response({"status": "error", "error": "Node not found"}, status=404)

    def patch(self, request, meal_identifier: str) -> Response:
        instance, created = MealInstance.objects.get_or_create(
            meal_identifier=meal_identifier,
            user=request.user,
            defaults={
                'dietary_goal_id': int(meal_identifier.split(':')[0]),
                'meal_name': request.data.get('meal_name', ''),
                'day_number': int(meal_identifier.split(':')[1]) if len(meal_identifier.split(':')) > 1 else 1,
                'meal_type': meal_identifier.split(':')[2] if len(meal_identifier.split(':')) > 2 else '',
            }
        )
        serializer = MealInstanceCreateUpdateSerializer(instance, data=request.data, partial=True)
        if serializer.is_valid():
            if 'is_cooked' in request.data and request.data['is_cooked'] and not instance.is_cooked:
                serializer.validated_data['cooked_at'] = timezone.now()
            elif 'is_cooked' in request.data and not request.data['is_cooked']:
                serializer.validated_data['cooked_at'] = None
            serializer.save()
            instance.refresh_from_db()
            return Response({"status": "success", "data": MealInstanceSerializer(instance).data})
        return Response({"status": "error", "error": serializer.errors}, status=400)


class MealInstanceBatchView(APIView):
    """
    Batch state for all nodes in a roadmap.
    """
    permission_classes = [IsAuthenticated]
    def get(self, request, goal_id: int) -> Response:
        instances = MealInstance.objects.filter(dietary_goal_id=goal_id, user=request.user)
        return Response({"status": "success", "data": MealInstanceSerializer(instances, many=True).data})


class MealInstanceCookedListView(APIView):
    """
    Global history of successfully executed meals.
    """
    permission_classes = [IsAuthenticated]
    def get(self, request) -> Response:
        instances = MealInstance.objects.filter(user=request.user, is_cooked=True)
        return Response({"status": "success", "data": MealInstanceSerializer(instances, many=True).data})

class ScraperDebugView(APIView):
    """
    Inventory engine tester. Restricted to admin users only.
    """
    permission_classes = [IsAdminUser]

    def get(self, request) -> Response:
        shop = request.query_params.get('shop')
        country = request.query_params.get('country')
        if not shop or not country:
            return Response({"status": "error", "error": "Invalid engine params"}, status=400)
        from .scrapers.scraper_service import ScraperService
        offers = ScraperService.get_available_ingredients(shop, country, force_refresh=True)
        return Response({"status": "success", "data": {"count": len(offers), "sample": offers[:5]}})


class DiscountOptimizationView(APIView):
    """Trigger or retrieve discount optimization for a plan."""
    permission_classes = [IsAuthenticated]

    def post(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)

        try:
            plan = goal.dietary_plan
        except DietaryPlan.DoesNotExist:
            return Response({"status": "error", "error": "Plan not found"}, status=404)

        requested_shops = request.data.get('shops')
        validated_shops: Optional[List[str]] = None
        if requested_shops:
            if not isinstance(requested_shops, list) or not all(isinstance(s, str) for s in requested_shops):
                return Response(
                    {"status": "error", "error": "'shops' must be a list of shop codes"},
                    status=400,
                )
            allowed = set(
                GroceryStore.objects.filter(country=goal.country, is_active=True)
                .values_list('code', flat=True)
            )
            validated_shops = [s for s in requested_shops if s in allowed]
            if not validated_shops:
                return Response(
                    {"status": "error", "error": "No valid shops in selection"},
                    status=400,
                )

        force = bool(request.data.get('force'))
        if plan.discount_optimization and not force:
            cached = plan.discount_optimization if isinstance(plan.discount_optimization, dict) else {}
            cached_shops = cached.get('shops_queried')
            requested_set = set(validated_shops) if validated_shops else None
            cached_set = set(cached_shops) if cached_shops else None
            if requested_set == cached_set:
                return Response({"status": "success", "data": plan.discount_optimization})

        task = optimize_plan_discounts_task.delay(goal_id, shops=validated_shops, force_scrape=force)
        return Response({
            "status": "success",
            "data": {"task_id": task.id, "message": "Optimization started", "shops_queried": validated_shops}
        }, status=status.HTTP_202_ACCEPTED)

    def get(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)

        try:
            plan = goal.dietary_plan
        except DietaryPlan.DoesNotExist:
            return Response({"status": "error", "error": "Plan not found"}, status=404)

        if not plan.discount_optimization:
            return Response({"status": "success", "data": {"ready": False}})

        return Response({"status": "success", "data": {
            "ready": True,
            "applied": plan.discount_optimization_applied,
            **plan.discount_optimization,
        }})


class ApplyDiscountOptimizationView(APIView):
    """Apply or reject the discount optimization suggestions."""
    permission_classes = [IsAuthenticated]

    def post(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)

        try:
            plan = goal.dietary_plan
        except DietaryPlan.DoesNotExist:
            return Response({"status": "error", "error": "Plan not found"}, status=404)

        optimization = plan.discount_optimization
        if not optimization or not optimization.get('swaps'):
            return Response({"status": "error", "error": "No optimization available"}, status=400)

        optimized_days = optimization.get('optimized_days')
        optimized_list = optimization.get('optimized_shopping_list')

        if not optimized_days:
            return Response({"status": "error", "error": "Optimization has no plan data"}, status=400)

        plan.discount_optimization['original_days'] = plan.days
        plan.discount_optimization['original_shopping_list'] = plan.shopping_list
        plan.discount_optimization['original_total_price'] = str(plan.total_price)

        plan.days = optimized_days
        if optimized_list:
            plan.shopping_list = optimized_list
        new_total = sum(
            float(item.get('price_total') or item.get('price') or 0)
            for item in (optimized_list or [])
        )
        if new_total > 0:
            plan.total_price = new_total
        plan.discount_optimization_applied = True
        plan.save()

        return Response({"status": "success", "data": {
            "applied": True,
            "new_total_price": str(plan.total_price),
        }})


class PublicRecipeListView(APIView):
    permission_classes = []

    def get(self, request) -> Response:
        from django.core.paginator import Paginator
        page_num = request.query_params.get('page', 1)
        recipes = Recipe.objects.filter(is_public=True).order_by('-created_at')
        paginator = Paginator(recipes, 24)
        page = paginator.get_page(page_num)
        serializer = RecipeSerializer(page.object_list, many=True)
        return Response({
            "status": "success",
            "data": {
                "results": serializer.data,
                "count": paginator.count,
                "num_pages": paginator.num_pages,
                "current_page": page.number,
                "has_next": page.has_next(),
                "has_previous": page.has_previous(),
            }
        })


class PublicRecipeDetailView(APIView):
    permission_classes = []

    def get(self, request, pk: int) -> Response:
        try:
            recipe = Recipe.objects.get(pk=pk, is_public=True)
            return Response({"status": "success", "data": RecipeSerializer(recipe).data})
        except Recipe.DoesNotExist:
            return Response({"status": "error", "error": "Recipe not found"}, status=404)


class PriceFeedbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)

        try:
            plan = goal.dietary_plan
        except DietaryPlan.DoesNotExist:
            return Response({"status": "error", "error": "Plan not found"}, status=404)

        actual_total = request.data.get('actual_total')
        if actual_total is None:
            return Response({"status": "error", "error": "actual_total is required"}, status=400)

        try:
            actual_total = float(actual_total)
            if actual_total < 0:
                raise ValueError
        except (ValueError, TypeError):
            return Response({"status": "error", "error": "actual_total must be a positive number"}, status=400)

        feedback = PriceFeedback.objects.create(
            user=request.user,
            dietary_plan=plan,
            estimated_total=plan.total_price or 0,
            actual_total=actual_total,
            currency=plan.currency or '',
            note=str(request.data.get('note', ''))[:1000],
        )

        return Response({
            "status": "success",
            "data": {
                "id": feedback.id,
                "estimated_total": str(feedback.estimated_total),
                "actual_total": str(feedback.actual_total),
                "difference": str(feedback.actual_total - feedback.estimated_total),
                "currency": feedback.currency,
            }
        }, status=status.HTTP_201_CREATED)

    def get(self, request, goal_id: int) -> Response:
        try:
            goal = DietaryGoal.objects.get(id=goal_id, user=request.user)
        except DietaryGoal.DoesNotExist:
            return Response({"status": "error", "error": "Goal not found"}, status=404)

        try:
            plan = goal.dietary_plan
        except DietaryPlan.DoesNotExist:
            return Response({"status": "error", "error": "Plan not found"}, status=404)

        feedback = plan.price_feedbacks.filter(user=request.user).first()
        if not feedback:
            return Response({"status": "success", "data": None})

        return Response({
            "status": "success",
            "data": {
                "id": feedback.id,
                "estimated_total": str(feedback.estimated_total),
                "actual_total": str(feedback.actual_total),
                "difference": str(feedback.actual_total - feedback.estimated_total),
                "currency": feedback.currency,
                "note": feedback.note,
            }
        })


MAX_PDF_SIZE = 10 * 1024 * 1024  # 10 MB


class ProtocolUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        pdf_file = request.FILES.get('pdf_file')
        if not pdf_file:
            return Response(
                {"status": "error", "error": "No PDF file provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if pdf_file.size > MAX_PDF_SIZE:
            return Response(
                {"status": "error", "error": f"File too large (max {MAX_PDF_SIZE // (1024*1024)} MB)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_bytes = pdf_file.read()
        if not pdf_bytes[:5].startswith(b'%PDF'):
            return Response(
                {"status": "error", "error": "Invalid file — only PDF files are accepted"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name = request.data.get('name', '') or pdf_file.name or 'Uploaded Protocol'

        plan = HistoricNutritionPlan.objects.create(
            user=request.user,
            name=name,
            pdf_file=pdf_bytes,
            pdf_filename=pdf_file.name or '',
            pdf_size_bytes=len(pdf_bytes),
            processing_status=HistoricNutritionPlan.ProcessingStatus.PENDING,
        )

        try:
            process_protocol_pdf_task.delay(plan.id)
        except Exception as e:
            logger.error(f"Could not queue protocol processing task: {e}")

        return Response({
            "status": "success",
            "data": HistoricNutritionPlanSerializer(plan).data,
        }, status=status.HTTP_201_CREATED)


class ProtocolListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        protocols = HistoricNutritionPlan.objects.filter(user=request.user)
        return Response({
            "status": "success",
            "data": HistoricNutritionPlanSerializer(protocols, many=True).data,
        })


class ProtocolDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, protocol_id: int) -> Response:
        try:
            protocol = HistoricNutritionPlan.objects.get(id=protocol_id, user=request.user)
        except HistoricNutritionPlan.DoesNotExist:
            return Response(
                {"status": "error", "error": "Protocol not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = HistoricNutritionPlanSerializer(protocol).data
        if protocol.processing_status == 'completed' and protocol.structured_constraints:
            try:
                import json
                data['structured_constraints'] = json.loads(protocol.structured_constraints)
            except (json.JSONDecodeError, TypeError):
                pass
        return Response({"status": "success", "data": data})

    def delete(self, request, protocol_id: int) -> Response:
        try:
            protocol = HistoricNutritionPlan.objects.get(id=protocol_id, user=request.user)
        except HistoricNutritionPlan.DoesNotExist:
            return Response(
                {"status": "error", "error": "Protocol not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        protocol.delete()
        return Response({"status": "success"}, status=status.HTTP_204_NO_CONTENT)