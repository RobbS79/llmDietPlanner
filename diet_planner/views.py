# File: diet_planner/views.py
"""
API Views for dietary goals and plans.
Uses DRF APIView for class-based views to maintain strict control over logic flow.
Handles asynchronous task triggering (Celery) and partial "Draft" saves for UI persistence.
"""
import logging
import traceback
from typing import Dict, Any

from django.conf import settings
from django.db import transaction
from django.db.models import F
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.contrib.auth.models import User
from .food_categories import guess_category
from django.utils import timezone

from .models import (
    CuratedRecipe,
    DietaryGoal,
    DietaryPlan,
    Recipe,
    MealInstance,
    GroceryStore,
    HistoricNutritionPlan,
    RecipeResearchJob,
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
    build_price_range,
    build_shopping_list,
    build_deals,
)
from .schemas import DietaryGoalCreateRequest
from .services.recipe_coherence import filter_pre_prepared
from .services.recipe_retrieval import (
    required_tags_for_goal,
    published_pool,
    published_cuisine_vocab,
    eligible_recipes_for_slot,
    portions_for_target,
    score_recipe,
    scale_recipe_to_meal,
    wanted_matcher,
)
from .services.prompt_facets import extract_prompt_facets
from .services.refine_agent import run_refine_turn
from .services.refine_chat import clamp_messages, refine_conversation
from .tasks import process_dietary_goal_task, process_dietary_goal_catalog_task, build_llm_prompt_json, process_protocol_pdf_task
from llm_diet_planner_project.celery_compat import AsyncResult, is_celery_available
from login_app.models import UserProfile
from billing.entitlements import active_subscription

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

            # Verification of generation credits / paid entitlement.
            # Paid path: an active subscription still within its monthly quota.
            # Free path: the lifetime free-generation counter (unchanged).
            # Neither -> hard 402 (the paywall that did not exist before).
            profile, _ = UserProfile.objects.get_or_create(user=request.user)

            # Email-verification gate: only verified users may generate a plan.
            # Registration lets users log in immediately (is_active=True); email
            # verification (login_app VerifyEmailView) unlocks the core action.
            # Google-OAuth users are marked email_verified on login.
            if not profile.email_verified:
                return Response(
                    {
                        "status": "error",
                        "code": "EMAIL_NOT_VERIFIED",
                        "error": "Než vygenerujete jídelníček, potvrďte prosím svou e-mailovou adresu "
                                 "podle odkazu v e-mailu, který jsme vám poslali.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            subscription = active_subscription(request.user)
            is_paid_generation = bool(subscription and subscription.within_monthly_quota())
            is_free_generation = (not is_paid_generation) and profile.has_free_generations()

            if not is_paid_generation and not is_free_generation:
                return Response(
                    {
                        "status": "error",
                        "code": "PAYMENT_REQUIRED",
                        "error": "Vyčerpali jste své generování. Vyberte si předplatné.",
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )

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
                'shop': schema.shop.value if schema.shop else 'ROHLIK',
                'store_mode': 'single',
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

            # Account usage only on full successful creation.
            # Paid path consumes monthly quota; free path decrements the counter.
            if is_paid_generation:
                subscription.plans_used_this_period += 1
                subscription.save(update_fields=['plans_used_this_period', 'updated_at'])
            elif is_free_generation:
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

        # A retry re-runs the LLM plan generation, so it must carry the SAME
        # email-verification gate as first-time generation — otherwise an
        # unverified user could draft a goal (draft path is un-gated) and then
        # "retry" it to bypass the gate. Staff bypass for support/debugging.
        if not request.user.is_staff:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            if not profile.email_verified:
                return Response(
                    {
                        "status": "error",
                        "code": "EMAIL_NOT_VERIFIED",
                        "error": "Než vygenerujete jídelníček, potvrďte prosím svou e-mailovou adresu "
                                 "podle odkazu v e-mailu, který jsme vám poslali.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

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


def _parse_meal_identifier(meal_identifier: str):
    """(goal_id, day_number, meal_type) from 'goal_id:day_number:meal_type:index'.

    Raises ValueError when malformed. Shared by the recipe-detail GET and the
    replace swap so the identifier contract cannot drift between them.
    """
    parts = meal_identifier.split(':')
    if len(parts) < 3:
        raise ValueError('meal identifier needs at least goal:day:type')
    return int(parts[0]), int(parts[1]), parts[2]


def _recipe_cache_fields(meal: Dict[str, Any], instructions) -> Dict[str, Any]:
    """Field mapping for a cached Recipe row built from a meal dict. Shared by
    the recipe-detail GET (LLM-generated meals) and the replace swap (curated
    meals) so the two write paths cannot drift apart when a field is added."""
    return dict(
        servings=meal.get('servings') or 1,
        name=meal.get('name', ''),
        description=meal.get('description', '') or '',
        food_category=meal.get('food_category', '')
        or guess_category(meal.get('name', ''), meal.get('ingredients', [])),
        instructions=instructions,
        ingredients=meal.get('ingredients', []),
        preparation_time=meal.get('preparation_time'),
        nutritional_info=meal.get('nutritional_info', {}),
        source_name=meal.get('source_name', '') or '',
        source_url=meal.get('source_url', '') or '',
        source_author=meal.get('source_author', '') or '',
        curated_recipe_slug=meal.get('curated_recipe_slug', '') or '',
    )


def serialize_recipe_detail(recipe: Recipe) -> Dict[str, Any]:
    """Serialize a cached Recipe row into the detail payload the frontend reads.

    Re-applies the coherence filter and re-derives price_range/shopping_list/deals
    from the *filtered* ingredient list, so an "already prepared" ingredient is
    never priced or shown as a shopping-list line after being hidden from view.
    Shared by the recipe-detail GET and the replace-recipe swap so both return
    an identical shape.
    """
    data = RecipeSerializer(recipe).data
    filtered = filter_pre_prepared({
        'description': data.get('description') or '',
        'instructions': data.get('instructions') or [],
        'ingredients': data.get('ingredients') or [],
    })
    data['ingredients'] = filtered.get('ingredients', data.get('ingredients'))
    if filtered.get('pre_prepared_ingredients'):
        data['pre_prepared_ingredients'] = filtered['pre_prepared_ingredients']
    currency = getattr(recipe.dietary_goal, 'currency', None) or 'CZK'
    data['price_range'] = build_price_range(data['ingredients'], recipe.servings, currency)
    data['shopping_list'] = build_shopping_list(data['ingredients'], recipe.servings, currency)
    data['deals'] = build_deals(data['ingredients'])
    # The chat only reaches the open web through the v2 agent; with the flag off
    # the v1 facet path can only offer what is already in the corpus, so the UI
    # must not promise a web search it cannot run.
    data['refine_web_research'] = bool(getattr(settings, 'REFINE_CHAT_AGENT_ENABLED', False))
    return data


class RecipeDetailView(APIView):
    """
    Synthesized recipe instructions.
    Returns existing recipe or generates one on-demand from the meal plan data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, meal_identifier: str) -> Response:
        # Return existing recipe if available
        try:
            recipe = Recipe.objects.select_related('dietary_goal').get(
                meal_identifier=meal_identifier, dietary_goal__user=request.user)
            return Response({"status": "success", "data": serialize_recipe_detail(recipe)})
        except Recipe.DoesNotExist:
            pass

        # Generate on-demand: parse meal_identifier (format: goal_id:day_number:meal_type:index)
        try:
            goal_id, day_number, meal_type = _parse_meal_identifier(meal_identifier)
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

        # Coherence pass: if the meal's description / instructions say an
        # ingredient is "already prepared / leftover / from yesterday", do
        # NOT list it among the ingredients the user has to buy. Production
        # bug (plan 108, recipe 108:1:dinner:0): recipe said "the beef
        # (klizka) is already prepared" while the shopping list charged for
        # 300 g klizka. See diet_planner/services/recipe_coherence.py.
        meal = filter_pre_prepared(meal)

        # Recipe grounding (B4): if this meal was served from the curated
        # corpus, it already has novice-clear, vetted steps — use them as-is
        # and skip the LLM regeneration entirely.
        is_curated = bool(meal.get('source') == 'curated' and meal.get('instructions'))
        if is_curated:
            instructions = [
                s if isinstance(s, str) else (s.get('text') or '')
                for s in meal.get('instructions', [])
            ]

        # Generate cooking instructions via LLM (only when not curated). If the
        # first pass comes back too thin (one-liners like "eat a piece of
        # chocolate"), fire one expansion retry so the recipe has enough
        # substance to be published. The Recipe.save() gate enforces this same
        # threshold.
        if not is_curated:
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

                if Recipe.count_instruction_words(instructions) < Recipe.PUBLISH_MIN_WORDS:
                    logger.info(
                        f"Thin recipe instructions ({Recipe.count_instruction_words(instructions)} words) "
                        f"for {meal_identifier!r}, retrying with expansion prompt."
                    )
                    expanded = llm_service.expand_thin_recipe_instructions(
                        meal_name=meal.get('name', ''),
                        ingredients=ingredient_names,
                        thin_instructions=instructions,
                        description=meal.get('description', ''),
                        language_code=goal.language_code,
                    )
                    if Recipe.count_instruction_words(expanded) > Recipe.count_instruction_words(instructions):
                        instructions = expanded
            except Exception as e:
                logger.error(f"Failed to generate recipe instructions for {meal_identifier}: {e}")
                instructions = []

        # Store recipe for future requests
        recipe = Recipe.objects.create(
            meal_identifier=meal_identifier,
            dietary_goal=goal,
            **_recipe_cache_fields(meal, instructions),
        )
        return Response({"status": "success", "data": RecipeSerializer(recipe).data})


def _locate_plan_slot(user, meal_identifier: str):
    """Resolve a meal identifier to its plan slot for `user`.

    Returns (ctx, None) on success where ctx has .goal, .plan, .target_day,
    .meal_type, .current_meal — or (None, error Response) on any failure.
    Shared by RecipeReplaceView and RecipeRefineView so both address slots
    identically."""
    from types import SimpleNamespace
    try:
        goal_id, day_number, meal_type = _parse_meal_identifier(meal_identifier)
    except (ValueError, IndexError):
        return None, Response({"status": "error", "error": "Invalid meal identifier format"}, status=400)
    try:
        goal = DietaryGoal.objects.get(id=goal_id, user=user)
    except DietaryGoal.DoesNotExist:
        return None, Response({"status": "error", "error": "Goal not found"}, status=404)
    try:
        plan = goal.dietary_plan
    except DietaryPlan.DoesNotExist:
        return None, Response({"status": "error", "error": "Plan not found"}, status=404)
    target_day = next(
        (d for d in (plan.days or []) if d.get('day_number') == day_number), None,
    )
    current_meal = target_day.get(meal_type) if isinstance(target_day, dict) else None
    if not isinstance(current_meal, dict):
        return None, Response({"status": "error", "error": "Meal not found in plan"}, status=404)
    return SimpleNamespace(
        goal=goal, plan=plan, target_day=target_day,
        meal_type=meal_type, current_meal=current_meal,
    ), None


def _plan_swap_state(plan, current_id):
    """Selection context for swapping one slot: (pool, used_recipe_ids,
    used_cuisines). used_recipe_ids covers every curated recipe elsewhere in
    the plan (the slot being swapped doesn't count) so a swap never duplicates
    a dish already on another day/slot."""
    used_recipe_ids: set = set()
    for d in (plan.days or []):
        for slot in ('breakfast', 'lunch', 'dinner'):
            m = d.get(slot)
            if isinstance(m, dict) and m.get('curated_recipe_id'):
                used_recipe_ids.add(m['curated_recipe_id'])
        for list_key in ('small_meals', 'snacks'):
            for m in (d.get(list_key) or []):
                if isinstance(m, dict) and m.get('curated_recipe_id'):
                    used_recipe_ids.add(m['curated_recipe_id'])
    used_recipe_ids.discard(current_id)
    pool = published_pool()
    cuisine_by_id = {r.id: (r.cuisine or '') for r in pool}
    used_cuisines = [cuisine_by_id[i] for i in used_recipe_ids if cuisine_by_id.get(i)]
    return pool, used_recipe_ids, used_cuisines


def _commit_slot_swap(*, goal, plan, target_day, meal_type, meal_identifier, chosen, user):
    """Atomically write `chosen` (a CuratedRecipe) into the slot: rewrite
    plan.days, bump usage_count, refresh the cached Recipe row IN PLACE (same
    pk — a substantive row is auto-published at /recepty/<pk>/, recreating
    would orphan that live URL), and reset cooked state. Returns the Recipe."""
    with transaction.atomic():
        # Portion the incoming recipe to the outgoing meal's calories — a swap
        # must not turn a 500-kcal slot into the new recipe's whole pot.
        old = target_day.get(meal_type)
        old_cal = (old.get('nutritional_info') or {}).get('calories') if isinstance(old, dict) else None
        new_meal = scale_recipe_to_meal(chosen, portions=portions_for_target(chosen, old_cal))
        new_meal['meal_identifier'] = meal_identifier
        target_day[meal_type] = new_meal
        plan.save(update_fields=['days'])
        CuratedRecipe.objects.filter(pk=chosen.id).update(usage_count=F('usage_count') + 1)
        recipe, _ = Recipe.objects.update_or_create(
            meal_identifier=meal_identifier,
            defaults={
                'dietary_goal': goal,
                **_recipe_cache_fields(new_meal, new_meal.get('instructions', [])),
            },
        )
        MealInstance.objects.filter(
            meal_identifier=meal_identifier, user=user,
        ).update(is_cooked=False, cooked_at=None, meal_name=new_meal.get('name', ''))
    return recipe


class RecipeReplaceView(APIView):
    """Swap one plan slot for a different curated recipe.

    Curated-corpus only (preserves the 100% catalog-mapping / deals integrity
    bar): retrieval is a $0 DB query + scoring over the published corpus. The
    only paid step is parsing a non-blank hint into facets — a single flash
    call, skipped entirely when the hint is blank.
    Spec: docs/superpowers/specs/2026-07-16-replace-recipe-swap-design.md.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, meal_identifier: str) -> Response:
        ctx, err = _locate_plan_slot(request.user, meal_identifier)
        if err:
            return err

        goal, plan = ctx.goal, ctx.plan
        required_tags = required_tags_for_goal(goal)
        current_id = ctx.current_meal.get('curated_recipe_id')
        exclude_ids = {current_id} if current_id else set()
        pool, used_recipe_ids, used_cuisines = _plan_swap_state(plan, current_id)

        hint = (request.data.get('hint') or '').strip()
        facets = None
        hint_matched = None
        if hint:
            facets = extract_prompt_facets(
                hint, language=goal.language_code,
                cuisine_vocab=published_cuisine_vocab(pool=pool),
            )
            # extract_prompt_facets never raises: an LLM failure (or a hint with
            # no extractable facets) yields EMPTY facets, which match every
            # recipe. Treat that as "could not honor the hint" — a plain
            # next-best fallback reported as hint_matched=False — rather than
            # letting an unsteered pick masquerade as a successful match.
            if facets.is_empty():
                facets = None
                hint_matched = False

        def pick(active_facets):
            candidates = eligible_recipes_for_slot(
                ctx.meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=active_facets,
            )
            if not candidates:
                return None
            return max(candidates, key=lambda r: score_recipe(
                r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines, facets=active_facets,
            ))

        chosen = pick(facets)
        if hint and hint_matched is None:
            # A non-empty hint was applied — did it actually steer the pick?
            if chosen is None:
                # Hint too specific for the corpus — fall back to plain next-best.
                chosen = pick(None)
                hint_matched = False
            elif facets.wanted_ingredients:
                # Wanted ingredients rank rather than gate (issue #47), so an
                # eligible pick may still miss the hint's point — check the fit.
                hint_matched = wanted_matcher(facets).hits(chosen) > 0
            else:
                hint_matched = True

        if chosen is None:
            return Response(
                {"status": "success", "data": {"replaced": False, "reason": "no_alternatives"}},
                status=200,
            )

        recipe = _commit_slot_swap(
            goal=goal, plan=plan, target_day=ctx.target_day, meal_type=ctx.meal_type,
            meal_identifier=meal_identifier, chosen=chosen, user=request.user,
        )
        return Response({
            "status": "success",
            "data": {
                "replaced": True,
                "hint_matched": hint_matched,
                "recipe": serialize_recipe_detail(recipe),
            },
        }, status=200)


_EMPHASIS_CZ = {
    'high_protein': 'hodně bílkovin',
    'low_carb': 'málo sacharidů',
    'low_calorie': 'nízkokalorické',
    'budget': 'úsporné',
}

# Cuisine slugs are curator-normalized English; the why-line is user-facing
# Czech, so unknown slugs are dropped rather than leaked untranslated.
_CUISINE_CZ = {
    'czech': 'česká kuchyně',
    'slovak': 'slovenská kuchyně',
    'american': 'americká kuchyně',
    'mediterranean': 'středomořská kuchyně',
    'italian': 'italská kuchyně',
    'asian': 'asijská kuchyně',
    'mexican': 'mexická kuchyně',
    'middle eastern': 'blízkovýchodní kuchyně',
    'french': 'francouzská kuchyně',
    'indian': 'indická kuchyně',
    'thai': 'thajská kuchyně',
    'greek': 'řecká kuchyně',
    'spanish': 'španělská kuchyně',
    'japanese': 'japonská kuchyně',
    'chinese': 'čínská kuchyně',
    'vietnamese': 'vietnamská kuchyně',
    'balkan': 'balkánská kuchyně',
    'german': 'německá kuchyně',
    'international': 'mezinárodní kuchyně',
}


def _matched_ingredient_names(recipe, wanted) -> list:
    """The recipe's own (Czech) ingredient names that match wanted-ingredient
    tokens. The LLM normalizes tokens (often to English, e.g. 'pasta'); the
    user must see the real ingredient, never the internal token."""
    names: list = []
    for w in sorted(wanted):
        for ing in (recipe.ingredients or []):
            name = str(ing.get('name') or '').strip()
            canonical = str(ing.get('canonical') or '').strip().lower()
            if name and (w in name.lower() or w in canonical) and name not in names:
                names.append(name)
                break
    return names


def _candidate_why(recipe, facets) -> str | None:
    """Czech 'why this candidate' line, derived IN CODE from which facets the
    candidate actually matches — never LLM-written."""
    if facets is None:
        return None
    parts: list = []
    parts += _matched_ingredient_names(recipe, facets.wanted_ingredients)
    cuisine = (recipe.cuisine or '').strip().lower()
    if cuisine in facets.cuisines and cuisine in _CUISINE_CZ:
        parts.append(_CUISINE_CZ[cuisine])
    tags = set(recipe.dietary_tags or [])
    parts += [_EMPHASIS_CZ[e] for e in sorted(facets.emphases & tags) if e in _EMPHASIS_CZ]
    if 'quick' in facets.styles and recipe.total_time and recipe.total_time <= 20:
        parts.append('rychlé')
    return f"Odpovídá: {', '.join(parts)}" if parts else None


def _candidate_payload(recipe, facets) -> dict:
    """Card-sized preview of a candidate. Rendered from scale_recipe_to_meal so
    the fields match exactly what an accepted swap would write."""
    meal = scale_recipe_to_meal(recipe)
    return {
        'curated_recipe_id': recipe.id,
        'name': meal['name'],
        'description': meal['description'],
        'food_category': meal['food_category'],
        'preparation_time': meal['preparation_time'],
        'calories': (meal.get('nutritional_info') or {}).get('calories'),
        'why': _candidate_why(recipe, facets),
    }


class RecipeRefineView(APIView):
    """Conversational curated swap: preview candidates turn-by-turn, commit only
    on accept. Preview turns make exactly one flash call (facets + Czech
    follow-up question) and NEVER write; every candidate is a published
    CuratedRecipe, so the catalog-mapping integrity bar is preserved.
    Spec: docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, meal_identifier: str) -> Response:
        ctx, err = _locate_plan_slot(request.user, meal_identifier)
        if err:
            return err
        goal = ctx.goal
        required_tags = required_tags_for_goal(goal)
        current_id = ctx.current_meal.get('curated_recipe_id')
        pool, used_recipe_ids, used_cuisines = _plan_swap_state(ctx.plan, current_id)

        if request.data.get('accept') is not None:
            return self._accept(
                request, ctx=ctx, meal_identifier=meal_identifier,
                required_tags=required_tags, current_id=current_id, pool=pool,
            )

        messages = clamp_messages(request.data.get('messages'))
        rejected = {
            int(i) for i in (request.data.get('rejected_ids') or [])
            if isinstance(i, int) or (isinstance(i, str) and i.isdigit() and len(i) <= 18)
        }
        exclude_ids = ({current_id} if current_id else set()) | rejected

        if getattr(settings, 'REFINE_CHAT_AGENT_ENABLED', False):
            try:
                turn = run_refine_turn(
                    user=request.user,
                    meal_identifier=meal_identifier,
                    meal_type=ctx.meal_type,
                    current_meal=ctx.current_meal,
                    required_tags=required_tags,
                    pool=pool,
                    exclude_ids=exclude_ids,
                    used_recipe_ids=used_recipe_ids,
                    used_cuisines=used_cuisines,
                    messages=messages,
                )
                return Response({
                    "status": "success",
                    "data": {
                        "reply_text": turn.reply_text,
                        "candidate": (
                            _candidate_payload(turn.candidate, None)
                            if turn.candidate else None
                        ),
                        "alternatives": [
                            _candidate_payload(r, None) for r in turn.alternatives
                        ],
                        "research_job_id": turn.research_job_id,
                        "question": None,
                        "hint_matched": None,
                    },
                }, status=200)
            except Exception:
                # refine_agent_fallback: v1 path below still serves the turn.
                logger.warning("refine_agent_fallback", exc_info=True)

        facets, question = refine_conversation(
            messages, language=goal.language_code,
            cuisine_vocab=published_cuisine_vocab(pool=pool),
        )
        # Restrictions stated IN the chat ("nejím lepek") join the profile/goal
        # gate as HARD requirements — used by both picks below, so the
        # unmatched-facets fallback can never relax them.
        required_tags = required_tags | facets.dietary
        hint_matched = None
        if facets.is_empty():
            # Mirrors the replace endpoint: empty facets (LLM failure or nothing
            # extractable) match everything — report the pick as unsteered.
            facets = None
            hint_matched = False

        def pick(active_facets):
            candidates = eligible_recipes_for_slot(
                ctx.meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=active_facets,
            )
            if not candidates:
                return None
            return max(candidates, key=lambda r: score_recipe(
                r, used_recipe_ids=used_recipe_ids, used_cuisines=used_cuisines, facets=active_facets,
            ))

        chosen = pick(facets)
        if facets is not None:
            if chosen is None:
                chosen = pick(None)
                hint_matched = False
            elif facets.wanted_ingredients:
                # Wanted ingredients rank rather than gate (issue #47), so an
                # eligible pick may still miss the hint's point — check the fit.
                hint_matched = wanted_matcher(facets).hits(chosen) > 0
            else:
                hint_matched = True

        if chosen is None:
            return Response({
                "status": "success",
                "data": {"candidate": None, "question": None,
                         "hint_matched": hint_matched, "reason": "no_alternatives"},
            }, status=200)

        return Response({
            "status": "success",
            "data": {
                "candidate": _candidate_payload(chosen, facets),
                "question": question,
                "hint_matched": hint_matched,
            },
        }, status=200)

    def _accept(self, request, *, ctx, meal_identifier, required_tags, current_id, pool):
        try:
            accept_id = int(request.data.get('accept'))
        except (TypeError, ValueError):
            return Response({"status": "error", "error": "Invalid accept id"}, status=400)
        # Re-validate against the SAME eligibility gate the preview used — the
        # corpus or plan may have changed between preview and accept, and a
        # crafted id must never bypass slot/dietary rules.
        exclude_ids = {current_id} if current_id else set()
        candidates = eligible_recipes_for_slot(
            ctx.meal_type, required_tags, pool=pool, exclude_ids=exclude_ids, facets=None,
        )
        # Spec 2026-07-27 decision 1: the requester's own chat_web drafts are
        # acceptable without full catalog mapping (their unmapped ingredients
        # simply carry no price/deals data).
        own_drafts = list(CuratedRecipe.objects.filter(
            origin=CuratedRecipe.Origin.CHAT_WEB,
            created_for_user=request.user,
            status=CuratedRecipe.Status.DRAFT,
        ))
        candidates += eligible_recipes_for_slot(
            ctx.meal_type, required_tags, pool=own_drafts, exclude_ids=exclude_ids,
            facets=None, enforce_mapping=False,
        )
        chosen = next((r for r in candidates if r.id == accept_id), None)
        if chosen is None:
            return Response({"status": "error", "error": "Recipe not eligible for this slot"}, status=400)
        # Captured BEFORE the swap rewrites the slot. Undo works because
        # _accept only ever excludes the *current* recipe, so the one we are
        # replacing becomes eligible again the moment this commit lands. A meal
        # that didn't come from the corpus has no id to go back to.
        previous = {
            "curated_recipe_id": current_id,
            "name": ctx.current_meal.get('name') or '',
        } if current_id else None
        recipe = _commit_slot_swap(
            goal=ctx.goal, plan=ctx.plan, target_day=ctx.target_day, meal_type=ctx.meal_type,
            meal_identifier=meal_identifier, chosen=chosen, user=request.user,
        )
        return Response({
            "status": "success",
            "data": {"replaced": True, "recipe": serialize_recipe_detail(recipe),
                     "previous": previous},
        }, status=200)


class RecipeResearchJobView(APIView):
    """Poll target for chat web-research jobs. Owner-only; foreign ids 404."""
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: int) -> Response:
        try:
            job = RecipeResearchJob.objects.get(id=job_id, user=request.user)
        except RecipeResearchJob.DoesNotExist:
            return Response({"status": "error", "error": "Not found"}, status=404)
        candidate = None
        if job.status == RecipeResearchJob.Status.READY and job.result_recipe:
            candidate = _candidate_payload(job.result_recipe, None)
        return Response({
            "status": "success",
            "data": {
                "status": job.status,
                "reply_text": job.reply_text or None,
                "candidate": candidate,
            },
        }, status=200)


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


class PublicRecipeListView(APIView):
    permission_classes = []

    def get(self, request) -> Response:
        from django.core.paginator import Paginator
        page_num = request.query_params.get('page', 1)
        # Many users generate the same meal, producing near-identical public
        # rows ("Kuřecí parmigiana" ×5 on one page). Show only the newest row
        # per name. Python-side dedupe keeps this portable across DB backends;
        # the public corpus is small (hundreds, not millions).
        seen_names = set()
        ids = []
        for pk, name in Recipe.objects.filter(is_public=True).order_by('-created_at').values_list('id', 'name'):
            key = (name or '').strip().lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            ids.append(pk)
        recipes = Recipe.objects.filter(pk__in=ids).select_related('dietary_goal').order_by('-created_at')
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
            recipe = Recipe.objects.select_related('dietary_goal').get(pk=pk, is_public=True)
            return Response({"status": "success", "data": RecipeSerializer(recipe).data})
        except Recipe.DoesNotExist:
            return Response({"status": "error", "error": "Recipe not found"}, status=404)


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