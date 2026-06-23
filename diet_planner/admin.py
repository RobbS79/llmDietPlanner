from datetime import timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib import messages
from django.db.models import Sum, Count, Max
from django.template.response import TemplateResponse
from django.urls import path
from django.utils import timezone

from .models import (
    DietaryGoal, DietaryPlan, HistoricNutritionPlan, LeafletOffer, Recipe, MealInstance,
    GroceryStore, CanonicalIngredient, IngredientAlias, IngredientSubstitute,
    StoreProduct, PriceRecord, PriceFreshnessPolicy, ScrapeRun,
    CuratedRecipe,
)
from django.utils.html import format_html


@admin.register(DietaryGoal)
class DietaryGoalAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'user', 'status', 'country', 'city',
        'currency', 'language_code', 'created_at', 'completed_at',
    ]
    list_filter = ['status', 'country', 'currency', 'language_code', 'created_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at', 'completed_at', 'celery_task_id']
    date_hierarchy = 'created_at'

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:
            readonly.extend(['prompt', 'dietary_restrictions'])
        return readonly

    def has_delete_permission(self, request, obj=None):
        return True

    def delete_model(self, request, obj):
        try:
            obj.delete()
            messages.success(request, f"Dietary Goal {obj.id} deleted successfully.")
        except Exception as e:
            messages.error(request, f"Error deleting Dietary Goal {obj.id}: {str(e)}")
            raise

    def delete_queryset(self, request, queryset):
        deleted_count = 0
        errors = []
        for obj in queryset:
            try:
                obj.delete()
                deleted_count += 1
            except Exception as e:
                errors.append(f"Goal {obj.id}: {str(e)}")
        if deleted_count > 0:
            messages.success(request, f"Successfully deleted {deleted_count} dietary goal(s).")
        if errors:
            messages.error(request, f"Errors deleting some goals: {'; '.join(errors)}")

    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Dietary Information', {
            'fields': ('prompt', 'dietary_restrictions', 'historic_plan_reference')
        }),
        ('Status & Processing', {
            'fields': ('status', 'celery_task_id', 'completed_at')
        }),
        ('Location', {
            'fields': ('country', 'city', 'currency', 'language_code'),
        }),
        ('Meal Configuration', {
            'fields': ('num_days', 'breakfast', 'lunch', 'dinner', 'small_meals_per_day', 'snacks_per_day', 'shop'),
        }),
        ('Payment', {
            'fields': ('is_free_generation', 'shopify_checkout_id', 'shopify_order_id', 'payment_confirmed_at'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(DietaryPlan)
class DietaryPlanAdmin(admin.ModelAdmin):
    list_display = ['id', 'dietary_goal', 'currency', 'llm_model_used', 'created_at']
    list_filter = ['currency', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Goal Reference', {
            'fields': ('dietary_goal',)
        }),
        ('LLM Generated Content', {
            'fields': ('days', 'meal_ideas'),
        }),
        ('Price Information', {
            'fields': ('currency',),
        }),
        ('LLM Usage', {
            'fields': ('llm_model_used', 'llm_input_tokens', 'llm_output_tokens', 'llm_total_tokens', 'llm_cost_usd'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(HistoricNutritionPlan)
class HistoricNutritionPlanAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'name', 'created_at']
    list_filter = ['created_at']
    search_fields = ['user__username', 'name']
    readonly_fields = ['created_at', 'updated_at', 'content']


@admin.register(LeafletOffer)
class LeafletOfferAdmin(admin.ModelAdmin):
    list_display = ['id', 'shop', 'country', 'ingredient_name', 'price', 'currency', 'price_type', 'freshness_state', 'expires_at']
    list_filter = ['shop', 'country', 'price_type', 'freshness_state', 'currency']
    search_fields = ['ingredient_name', 'display_name']
    readonly_fields = ['scraped_at']


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'name', 'meal_identifier', 'dietary_goal',
        'preparation_time', 'cooking_time', 'servings', 'created_at',
    ]
    list_filter = ['dietary_goal', 'created_at']
    search_fields = ['name', 'meal_identifier', 'description']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Meal Information', {
            'fields': ('meal_identifier', 'dietary_goal', 'name', 'description')
        }),
        ('Recipe Details', {
            'fields': ('ingredients', 'instructions', 'preparation_time', 'cooking_time', 'servings')
        }),
        ('Nutritional Information', {
            'fields': ('nutritional_info',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(MealInstance)
class MealInstanceAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'meal_name', 'user', 'dietary_goal',
        'day_number', 'meal_type', 'is_cooked', 'cooked_at', 'created_at',
    ]
    list_filter = ['is_cooked', 'meal_type', 'dietary_goal', 'cooked_at', 'created_at']
    search_fields = ['meal_name', 'meal_identifier', 'user__username', 'notes']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'cooked_at'

    fieldsets = (
        ('Meal Information', {
            'fields': ('user', 'dietary_goal', 'recipe', 'meal_identifier', 'meal_name', 'day_number', 'meal_type')
        }),
        ('Cooking Status', {
            'fields': ('is_cooked', 'cooked_at', 'notes')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


# ========================================================================
# New catalog / pricing / scraping models
# ========================================================================

@admin.register(GroceryStore)
class GroceryStoreAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'chain', 'country', 'currency', 'is_online_only', 'is_active', 'default_price_ttl_hours']
    list_filter = ['chain', 'country', 'is_active', 'is_online_only']
    search_fields = ['code', 'name']


@admin.register(CanonicalIngredient)
class CanonicalIngredientAdmin(admin.ModelAdmin):
    list_display = ['name', 'name_cs', 'slug', 'category', 'default_unit', 'is_pantry_staple']
    list_filter = ['category', 'is_pantry_staple']
    search_fields = ['name', 'name_cs', 'name_sk', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(IngredientAlias)
class IngredientAliasAdmin(admin.ModelAdmin):
    list_display = ['alias', 'canonical_ingredient', 'language_code']
    list_filter = ['language_code']
    search_fields = ['alias', 'canonical_ingredient__name']
    raw_id_fields = ['canonical_ingredient']


@admin.register(IngredientSubstitute)
class IngredientSubstituteAdmin(admin.ModelAdmin):
    list_display = ['ingredient', 'substitute', 'quality_score', 'conversion_factor']
    raw_id_fields = ['ingredient', 'substitute']


@admin.register(StoreProduct)
class StoreProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'store', 'canonical_ingredient', 'package_size', 'package_unit', 'is_active']
    list_filter = ['store', 'is_active']
    search_fields = ['name', 'normalized_name', 'canonical_ingredient__name']
    raw_id_fields = ['canonical_ingredient']


@admin.register(PriceRecord)
class PriceRecordAdmin(admin.ModelAdmin):
    list_display = ['store_product', 'price', 'currency', 'source_type', 'confidence', 'valid_from', 'valid_until', 'scraped_at']
    list_filter = ['source_type', 'currency']
    search_fields = ['store_product__name']
    raw_id_fields = ['store_product', 'scrape_run']
    date_hierarchy = 'scraped_at'


@admin.register(PriceFreshnessPolicy)
class PriceFreshnessPolicyAdmin(admin.ModelAdmin):
    list_display = ['source_type', 'ttl_hours', 'auto_expire', 'default_confidence']


@admin.register(ScrapeRun)
class ScrapeRunAdmin(admin.ModelAdmin):
    list_display = ['store', 'status', 'method', 'products_found', 'prices_recorded', 'errors_count', 'llm_cost_usd', 'started_at', 'duration_seconds']
    list_filter = ['status', 'method', 'store']
    date_hierarchy = 'started_at'
    readonly_fields = ['started_at']

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('dashboard/', self.admin_site.admin_view(self.dashboard_view), name='scraper-dashboard'),
        ]
        return custom + urls

    def dashboard_view(self, request):
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        stores = GroceryStore.objects.filter(is_active=True).order_by('chain', 'country')

        store_data = []
        for store in stores:
            latest = ScrapeRun.objects.filter(
                store=store, status='COMPLETED',
            ).order_by('-started_at').first()

            active = PriceRecord.objects.current().filter(
                store_product__store=store,
                store_product__is_active=True,
                price__gt=0,
            ).count()

            # PriceRecord doesn't carry a tri-state freshness machine; derive
            # "fresh" as records within half the TTL window of the latest scrape.
            ttl_hours = store.default_price_ttl_hours or 168
            fresh_cutoff = now - timedelta(hours=ttl_hours / 2)
            fresh = PriceRecord.objects.current().filter(
                store_product__store=store,
                scraped_at__gte=fresh_cutoff,
            ).count()
            stale = max(0, active - fresh)

            weekly_cost = ScrapeRun.objects.filter(
                store=store, started_at__gte=week_ago,
            ).aggregate(total=Sum('llm_cost_usd'))['total'] or Decimal('0')

            weekly_runs = ScrapeRun.objects.filter(
                store=store, started_at__gte=week_ago,
            ).count()

            if latest:
                age_hours = (now - latest.started_at).total_seconds() / 3600
                health = 'ok' if age_hours < store.default_price_ttl_hours * 0.75 else (
                    'warn' if age_hours < store.default_price_ttl_hours else 'stale'
                )
            else:
                age_hours = None
                health = 'never'

            store_data.append({
                'store': store,
                'latest_run': latest,
                'age_hours': f"{age_hours:.0f}h" if age_hours else "never",
                'active_offers': active,
                'fresh': fresh,
                'stale': stale,
                'weekly_runs': weekly_runs,
                'weekly_cost': f"${weekly_cost:.4f}",
                'health': health,
            })

        # Recent failed runs
        recent_failures = ScrapeRun.objects.filter(
            status='FAILED', started_at__gte=week_ago,
        ).order_by('-started_at')[:10]

        total_weekly_cost = ScrapeRun.objects.filter(
            started_at__gte=week_ago,
        ).aggregate(total=Sum('llm_cost_usd'))['total'] or Decimal('0')

        context = {
            **self.admin_site.each_context(request),
            'title': 'Scraper Dashboard',
            'store_data': store_data,
            'recent_failures': recent_failures,
            'total_weekly_cost': f"${total_weekly_cost:.4f}",
            'total_active_offers': sum(s['active_offers'] for s in store_data),
        }
        return TemplateResponse(request, 'admin/scraper_dashboard.html', context)


@admin.register(CuratedRecipe)
class CuratedRecipeAdmin(admin.ModelAdmin):
    list_display = [
        'name_cs', 'status', 'cuisine', 'difficulty',
        'meal_types', 'mapped', 'source_link', 'usage_count', 'updated_at',
    ]
    list_filter = ['status', 'cuisine', 'difficulty']
    search_fields = ['name_cs', 'name_en', 'source_name', 'source_url']
    prepopulated_fields = {'slug': ('name_cs',)}
    readonly_fields = ['created_at', 'updated_at', 'usage_count', 'source_link']
    actions = ['mark_vetted', 'mark_published', 'mark_draft']
    fieldsets = (
        (None, {'fields': ('slug', 'name_cs', 'name_en', 'description', 'status')}),
        ('Classification', {'fields': ('meal_types', 'cuisine', 'difficulty', 'dietary_tags')}),
        ('Content', {'fields': ('ingredients', 'instructions', 'base_servings',
                                'base_nutrition', 'prep_time', 'cook_time')}),
        ('Provenance', {'fields': ('source_url', 'source_link', 'source_name',
                                   'source_author', 'license_note')}),
        ('Quality', {'fields': ('quality_score', 'usage_count', 'created_at', 'updated_at')}),
    )

    @admin.display(boolean=True, description='Mapped')
    def mapped(self, obj):
        return obj.is_catalog_mapped()

    @admin.display(description='Source')
    def source_link(self, obj):
        if not obj.source_url:
            return '—'
        return format_html('<a href="{}" target="_blank" rel="noopener">{}</a>',
                           obj.source_url, obj.source_name or obj.source_url)

    @admin.action(description='Mark selected as vetted')
    def mark_vetted(self, request, queryset):
        n = queryset.update(status=CuratedRecipe.Status.VETTED)
        self.message_user(request, f"{n} recipe(s) marked vetted.")

    @admin.action(description='Mark selected as published')
    def mark_published(self, request, queryset):
        n = queryset.update(status=CuratedRecipe.Status.PUBLISHED)
        self.message_user(request, f"{n} recipe(s) published.")

    @admin.action(description='Mark selected as draft')
    def mark_draft(self, request, queryset):
        n = queryset.update(status=CuratedRecipe.Status.DRAFT)
        self.message_user(request, f"{n} recipe(s) moved to draft.")
