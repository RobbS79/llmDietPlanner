"""
Django admin configuration for Shopify models.
"""
from django.contrib import admin
from .models import ShopifyStore, ShopifyCheckout, ShopifyProduct


@admin.register(ShopifyStore)
class ShopifyStoreAdmin(admin.ModelAdmin):
    """Admin interface for Shopify stores."""
    list_display = [
        "name",
        "store_domain",
        "is_active",
        "created_at",
        "updated_at",
    ]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "store_domain"]
    readonly_fields = ["created_at", "updated_at", "storefront_api_url", "admin_api_url"]

    fieldsets = (
        ("Store Information", {
            "fields": ("name", "store_domain", "is_active"),
        }),
        ("API Configuration", {
            "fields": (
                "storefront_access_token",
                "admin_api_key",
                "admin_api_secret",
            ),
            "description": "Storefront API token is required. Admin API credentials are optional.",
        }),
        ("Webhook & Billing Configuration", {
            "fields": (
                "webhook_secret",
                "meal_plan_variant_id",
            ),
            "description": "Webhook secret from Shopify Admin (Settings → Notifications → Webhooks). "
                          "Meal plan variant ID is the Shopify variant ID for the €3 generation product.",
        }),
        ("API URLs", {
            "fields": ("storefront_api_url", "admin_api_url"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(ShopifyCheckout)
class ShopifyCheckoutAdmin(admin.ModelAdmin):
    """Admin interface for Shopify checkouts."""
    list_display = [
        "id",
        "user",
        "store",
        "status",
        "total_price",
        "currency",
        "order_number",
        "created_at",
        "completed_at",
    ]
    list_filter = ["status", "store", "created_at", "completed_at"]
    search_fields = [
        "user__username",
        "user__email",
        "checkout_id",
        "checkout_token",
        "order_id",
        "order_number",
    ]
    readonly_fields = [
        "checkout_id",
        "checkout_token",
        "checkout_url",
        "created_at",
        "updated_at",
        "completed_at",
    ]
    raw_id_fields = ["user", "store"]

    fieldsets = (
        ("Checkout Information", {
            "fields": ("user", "store", "status", "checkout_id", "checkout_token"),
        }),
        ("Order Details", {
            "fields": (
                "checkout_url",
                "total_price",
                "currency",
                "order_id",
                "order_number",
            ),
        }),
        ("Metadata", {
            "fields": ("metadata",),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at", "completed_at"),
        }),
    )


@admin.register(ShopifyProduct)
class ShopifyProductAdmin(admin.ModelAdmin):
    """Admin interface for Shopify products cache."""
    list_display = [
        "title",
        "store",
        "price",
        "currency",
        "available_for_sale",
        "updated_at",
    ]
    list_filter = ["store", "available_for_sale", "currency", "updated_at"]
    search_fields = ["title", "product_id", "variant_id"]
    readonly_fields = ["created_at", "updated_at"]
    raw_id_fields = ["store"]

    fieldsets = (
        ("Product Information", {
            "fields": (
                "store",
                "product_id",
                "variant_id",
                "title",
                "price",
                "currency",
                "available_for_sale",
                "image_url",
            ),
        }),
        ("Product Data", {
            "fields": ("product_data",),
            "classes": ("collapse",),
            "description": "Full product data from Shopify API (JSON)",
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )
