from django.contrib import admin
from django.contrib import messages
from .models import (
    DietaryGoal, DietaryPlan, HistoricNutritionPlan, LeafletOffer, Recipe, MealInstance,
    GroceryStore, CanonicalIngredient, IngredientAlias, IngredientSubstitute,
    StoreProduct, PriceRecord, PriceFreshnessPolicy, ScrapeRun,
)


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
    list_display = ['id', 'dietary_goal', 'total_price', 'currency', 'llm_model_used', 'created_at']
    list_filter = ['currency', 'created_at']
    readonly_fields = ['created_at', 'updated_at']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Goal Reference', {
            'fields': ('dietary_goal',)
        }),
        ('LLM Generated Content', {
            'fields': ('days', 'meal_ideas', 'shopping_list'),
        }),
        ('Price Information', {
            'fields': ('total_price', 'currency'),
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
