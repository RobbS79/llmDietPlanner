"""
Django REST Framework serializers for dietary goals and plans.
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import DietaryGoal, DietaryPlan, Recipe, MealInstance, HistoricNutritionPlan


class DietaryGoalSerializer(serializers.ModelSerializer):
    """Serializer for DietaryGoal model."""
    user = serializers.ReadOnlyField(source='user.username')
    
    class Meta:
        model = DietaryGoal
        fields = [
            'id',
            'user',
            'status',
            'prompt',
            'country',
            'city',
            'currency',
            'language_code',
            'num_days',
            'breakfast',
            'lunch',
            'dinner',
            'small_meals_per_day',
            'snacks_per_day',
            'shop',
            'created_at',
            'updated_at',
            'completed_at',
        ]
        read_only_fields = [
            'id',
            'status',
            'created_at',
            'updated_at',
            'completed_at',
        ]


class MealIdeaSerializer(serializers.Serializer):
    """Serializer for meal idea JSON structure."""
    name = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True)
    ingredients = serializers.ListField(child=serializers.CharField())
    preparation_time = serializers.IntegerField(required=False, allow_null=True)
    nutritional_info = serializers.DictField(required=False, allow_null=True)


class ShoppingListItemSerializer(serializers.Serializer):
    """Serializer for shopping list item JSON structure."""
    ingredient = serializers.CharField()
    quantity = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    unit = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Price information
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    price_total = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    matched_product_name = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # Price transparency (Phase 4)
    price_source = serializers.CharField(required=False, allow_null=True)
    source_detail = serializers.CharField(required=False, allow_null=True)
    estimated = serializers.BooleanField(required=False, default=False)
    valid_until = serializers.CharField(required=False, allow_null=True)
    cross_store = serializers.CharField(required=False, allow_null=True)
    original_price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, allow_null=True)
    discount_percentage = serializers.IntegerField(required=False, allow_null=True)


class DietaryPlanSerializer(serializers.ModelSerializer):
    """Serializer for DietaryPlan model."""
    # JSONField fields are already Python objects (lists/dicts), return them directly
    days = serializers.SerializerMethodField()
    shopping_list = serializers.SerializerMethodField()

    # Honest pricing: regular-price range + factual leaflet deals + pantry toggles
    pricing = serializers.SerializerMethodField()

    # LLM usage information
    llm_usage = serializers.SerializerMethodField()

    class Meta:
        model = DietaryPlan
        fields = [
            'id',
            'days',
            'shopping_list',
            'pricing',
            'total_price',
            'pantry_price',
            'pantry_basics_on',
            'pantry_fridge_on',
            'currency',
            'llm_usage',
            'discount_optimization',
            'discount_optimization_applied',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'days',
            'shopping_list',
            'pricing',
            'total_price',
            'pantry_price',
            'pantry_basics_on',
            'pantry_fridge_on',
            'currency',
            'llm_usage',
            'discount_optimization',
            'discount_optimization_applied',
            'created_at',
            'updated_at',
        ]
    
    def get_days(self, obj):
        """Return days JSONField as-is (already a Python list)."""
        # Support backward compatibility: if meal_ideas exists, convert to days format
        if hasattr(obj, 'meal_ideas') and obj.meal_ideas and not hasattr(obj, 'days'):
            # Legacy format - convert meal_ideas to days structure
            return []
        return obj.days if hasattr(obj, 'days') and obj.days else []
    
    def get_shopping_list(self, obj):
        """Return shopping_list JSONField as-is (already a Python list)."""
        return obj.shopping_list if obj.shopping_list else []

    def get_pricing(self, obj):
        """Honest price range + factual leaflet deals for this plan.

        Computed live from scraped PriceRecord rows (see
        SHOPPING_LIST_PRICING_PLAN.md). Returns
        {price_range, deals, pantry_toggles} or None if it can't be built.
        """
        from .services.shopping_list_pricing import compute_pricing

        items = obj.shopping_list or []
        if not items:
            return None

        country = getattr(obj.dietary_goal, 'country', None)
        if not country:
            return None

        import logging
        logger = logging.getLogger(__name__)
        try:
            return compute_pricing(
                items=items,
                country=country,
                currency=obj.currency,
                basics_on=obj.pantry_basics_on,
                fridge_on=obj.pantry_fridge_on,
            )
        except Exception as e:
            logger.error(
                f"Error computing pricing for plan {obj.id}: {e}", exc_info=True
            )
            return None

    def get_llm_usage(self, obj):
        """Return LLM usage information including tokens and cost."""
        if obj.llm_input_tokens is None:
            return None
        
        return {
            'input_tokens': obj.llm_input_tokens,
            'output_tokens': obj.llm_output_tokens,
            'total_tokens': obj.llm_total_tokens,
            'cost_usd': str(obj.llm_cost_usd) if obj.llm_cost_usd else None,
            'model': obj.llm_model_used,
        }


class DietaryGoalDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with nested dietary plan."""
    dietary_plan = DietaryPlanSerializer(read_only=True, allow_null=True, required=False)
    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = DietaryGoal
        fields = [
            'id',
            'user',
            'status',
            'country',
            'city',
            'currency',
            'language_code',
            'num_days',
            'breakfast',
            'lunch',
            'dinner',
            'small_meals_per_day',
            'snacks_per_day',
            'shop',
            'store_mode',
            'created_at',
            'updated_at',
            'completed_at',
            'dietary_plan',
        ]
        read_only_fields = [
            'id',
            'user',
            'status',
            'country',
            'city',
            'currency',
            'language_code',
            'num_days',
            'breakfast',
            'lunch',
            'dinner',
            'small_meals_per_day',
            'snacks_per_day',
            'shop',
            'store_mode',
            'created_at',
            'updated_at',
            'completed_at',
            'dietary_plan',
        ]
    
    def to_representation(self, instance):
        """Custom representation to handle missing dietary_plan gracefully."""
        # Get the base representation
        representation = super().to_representation(instance)
        
        # Try to get dietary_plan - handle DoesNotExist exception
        try:
            # Access the related plan - this might raise DoesNotExist
            plan = instance.dietary_plan
            if plan:
                # Serialize the plan
                representation['dietary_plan'] = DietaryPlanSerializer(plan).data
            else:
                representation['dietary_plan'] = None
        except DietaryPlan.DoesNotExist:
            representation['dietary_plan'] = None
        except AttributeError:
            # dietary_plan attribute doesn't exist
            representation['dietary_plan'] = None
        except Exception as e:
            # Log any other errors but set to None
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error serializing dietary_plan for goal {instance.id}: {str(e)}", exc_info=True)
            representation['dietary_plan'] = None
        
        return representation


class RecipeSerializer(serializers.ModelSerializer):
    """Serializer for Recipe model."""
    dietary_goal_id = serializers.IntegerField(source='dietary_goal.id', read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = [
            'id',
            'meal_identifier',
            'dietary_goal_id',
            'name',
            'slug',
            'description',
            'food_category',
            'image_url',
            'instructions',
            'ingredients',
            'preparation_time',
            'cooking_time',
            'servings',
            'nutritional_info',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
        ]

    def get_image_url(self, obj):
        from .food_categories import DEFAULT_CATEGORY, FOOD_CATEGORIES
        category = obj.food_category if obj.food_category in FOOD_CATEGORIES else DEFAULT_CATEGORY
        return f"/static/food-images/{category}.webp"


class MealInstanceSerializer(serializers.ModelSerializer):
    """Serializer for MealInstance model."""
    recipe = RecipeSerializer(read_only=True)
    recipe_id = serializers.IntegerField(source='recipe.id', read_only=True, allow_null=True)
    dietary_goal_id = serializers.IntegerField(source='dietary_goal.id', read_only=True)
    
    class Meta:
        model = MealInstance
        fields = [
            'id',
            'meal_identifier',
            'dietary_goal_id',
            'recipe',
            'recipe_id',
            'meal_name',
            'day_number',
            'meal_type',
            'is_cooked',
            'cooked_at',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
        ]


class MealInstanceCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating MealInstance (marking as cooked)."""

    class Meta:
        model = MealInstance
        fields = [
            'is_cooked',
            'notes',
        ]


class HistoricNutritionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistoricNutritionPlan
        fields = [
            'id',
            'name',
            'pdf_filename',
            'pdf_size_bytes',
            'processing_status',
            'processing_error',
            'structured_constraints',
            'created_at',
        ]
        read_only_fields = fields
