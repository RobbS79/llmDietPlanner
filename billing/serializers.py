"""Serializers for billing API responses."""
from rest_framework import serializers

from .models import SubscriptionPlan, Subscription


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = (
            'tier', 'name', 'price_czk', 'monthly_plan_quota',
            'edits_per_plan', 'allow_multi_store',
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    entitled = serializers.SerializerMethodField()
    remaining_quota = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = (
            'tier', 'status', 'current_period_end', 'cancel_at_period_end',
            'plans_used_this_period', 'entitled', 'remaining_quota',
        )

    def get_entitled(self, obj) -> bool:
        return obj.is_entitled()

    def get_remaining_quota(self, obj) -> int:
        return obj.remaining_quota()
