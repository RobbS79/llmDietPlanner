"""
Django REST Framework serializers for dietary goals and plans.
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import DietaryGoal, DietaryPlan


class DietaryGoalSerializer(serializers.ModelSerializer):
    """Serializer for DietaryGoal model."""
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


class DietaryPlanSerializer(serializers.ModelSerializer):
    """Serializer for DietaryPlan model."""
    # JSONField fields are already Python objects (lists/dicts), return them directly
    meal_ideas = serializers.SerializerMethodField()
    shopping_list = serializers.SerializerMethodField()
    
    class Meta:
        model = DietaryPlan
        fields = [
            'id',
            'meal_ideas',
            'shopping_list',
            'total_price',
            'currency',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'meal_ideas',
            'shopping_list',
            'total_price',
            'currency',
            'created_at',
            'updated_at',
        ]
    
    def get_meal_ideas(self, obj):
        """Return meal_ideas JSONField as-is (already a Python list)."""
        return obj.meal_ideas if obj.meal_ideas else []
    
    def get_shopping_list(self, obj):
        """Return shopping_list JSONField as-is (already a Python list)."""
        return obj.shopping_list if obj.shopping_list else []


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
