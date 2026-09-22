"""Admin registration for billing models."""
from django.contrib import admin, messages

from .models import (
    SubscriptionPlan, Subscription, ProcessedWebhookEvent, PromoCode, PromoRedemption,
)
from .services import ensure_stripe_coupon

_COUPON_TERMS = ('percent_off', 'duration_kind', 'duration_months')


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
        'user', 'tier', 'status', 'source', 'current_period_end', 'grant_expires_at',
        'plans_used_this_period', 'cancel_at_period_end', 'promo_code',
    )
    list_filter = ('tier', 'status', 'source', 'cancel_at_period_end')
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


class PromoRedemptionInline(admin.TabularInline):
    model = PromoRedemption
    extra = 0
    can_delete = False
    readonly_fields = ('user', 'tier', 'redeemed_at', 'stripe_checkout_session_id')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = (
        'code', 'percent_off', 'duration_kind', 'duration_months', 'tiers',
        'used_of_max', 'expires_at', 'is_active', 'stripe_coupon_id',
    )
    list_filter = ('is_active', 'duration_kind')
    search_fields = ('code', 'note')
    readonly_fields = ('stripe_coupon_id', 'created_at', 'updated_at')
    inlines = (PromoRedemptionInline,)
    actions = ('create_stripe_coupon',)

    @admin.display(description='Využito / max')
    def used_of_max(self, obj):
        mx = obj.max_redemptions if obj.max_redemptions is not None else '∞'
        return f"{obj.redemption_count()} / {mx}"

    def save_model(self, request, obj, form, change):
        if change and obj.stripe_coupon_id and obj.pk:
            old = PromoCode.objects.filter(pk=obj.pk).values(*_COUPON_TERMS).first()
            if old and any(old[f] != getattr(obj, f) for f in _COUPON_TERMS):
                obj.stripe_coupon_id = ''  # coupons are immutable — mint a new one
        super().save_model(request, obj, form, change)
        try:
            ensure_stripe_coupon(obj)
        except Exception as exc:  # Stripe down must not block saving the code
            messages.warning(request, f'Stripe kupón se nepodařilo vytvořit: {exc}')

    @admin.action(description='Vytvořit Stripe kupón')
    def create_stripe_coupon(self, request, queryset):
        for promo in queryset:
            try:
                ensure_stripe_coupon(promo)
            except Exception as exc:
                messages.error(request, f'{promo.code}: {exc}')


@admin.register(PromoRedemption)
class PromoRedemptionAdmin(admin.ModelAdmin):
    list_display = ('promo_code', 'user', 'tier', 'redeemed_at', 'stripe_checkout_session_id')
    search_fields = ('promo_code__code', 'user__username', 'user__email')
    readonly_fields = ('promo_code', 'user', 'tier', 'redeemed_at', 'stripe_checkout_session_id')
