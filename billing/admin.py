"""Admin registration for billing models."""
from django.contrib import admin

from .models import SubscriptionPlan, Subscription, ProcessedWebhookEvent


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'tier', 'price_czk', 'monthly_plan_quota',
        'edits_per_plan', 'allow_multi_store', 'is_active', 'stripe_price_id',
    )
    list_filter = ('is_active', 'allow_multi_store')
    search_fields = ('name', 'tier', 'stripe_price_id')


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'tier', 'status', 'current_period_end',
        'plans_used_this_period', 'cancel_at_period_end',
    )
    list_filter = ('tier', 'status', 'cancel_at_period_end')
    search_fields = (
        'user__username', 'user__email',
        'stripe_customer_id', 'stripe_subscription_id',
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(ProcessedWebhookEvent)
class ProcessedWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('stripe_event_id', 'event_type', 'received_at')
    search_fields = ('stripe_event_id', 'event_type')
    readonly_fields = ('stripe_event_id', 'event_type', 'received_at')
