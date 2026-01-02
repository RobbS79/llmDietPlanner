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
    meal_ideas = MealIdeaSerializer(many=True, read_only=True)
    shopping_list = ShoppingListItemSerializer(many=True, read_only=True)
    
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
        read_only_fields = '__all__'


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
        read_only_fields = '__all__'
    
    def to_representation(self, instance):
        """Custom representation to handle missing dietary_plan gracefully."""
        representation = super().to_representation(instance)
        # If dietary_plan doesn't exist, set it to null instead of causing an error
        if not hasattr(instance, 'dietary_plan') or instance.dietary_plan is None:
            representation['dietary_plan'] = None
        return representation
