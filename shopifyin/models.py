"""
Models for Shopify integration.
Handles store configuration and order tracking.
"""
from django.db import models
from django.contrib.auth.models import User
from encrypted_model_fields.fields import EncryptedCharField
from typing import Optional, Dict, Any


class ShopifyStore(models.Model):
    """
    Configuration for a Shopify store.
    Stores encrypted API credentials following GDPR best practices.
    """
    name = models.CharField(
        max_length=255,
        help_text="Display name for the store"
    )
    store_domain = models.CharField(
        max_length=255,
        unique=True,
        help_text="Shopify store domain (e.g., 'mealprep-9693.myshopify.com')"
    )
    storefront_access_token = EncryptedCharField(
        max_length=500,
        help_text="Shopify Storefront API access token (encrypted)"
    )
    admin_api_key = EncryptedCharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Shopify Admin API key (optional, for order management - encrypted)"
    )
    admin_api_secret = EncryptedCharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Shopify Admin API secret (optional - encrypted)"
    )
    webhook_secret = EncryptedCharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Shopify webhook secret for verifying webhook signatures (encrypted)"
    )
    meal_plan_variant_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Shopify Product Variant ID for the meal plan generation product (e.g., gid://shopify/ProductVariant/...)"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this store configuration is active"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shopify Store"
        verbose_name_plural = "Shopify Stores"
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f"{self.name} ({self.store_domain})"

    @property
    def storefront_api_url(self) -> str:
        """Generate the Storefront API URL for this store."""
        return f"https://{self.store_domain}/api/2024-01/graphql.json"

    @property
    def admin_api_url(self) -> str:
        """Generate the Admin API URL for this store."""
        return f"https://{self.store_domain}/admin/api/2024-01"

    def get_webhook_secret(self) -> Optional[str]:
        """Get the decrypted webhook secret for HMAC verification."""
        try:
            if self.webhook_secret:
                return self.webhook_secret
        except Exception:
            pass
        return None


class ShopifyCheckout(models.Model):
    """
    Track Shopify checkout sessions created for users.
    Links Django users to Shopify checkout IDs for order tracking.
    """
    class StatusChoices(models.TextChoices):
        CREATED = "created", "Created"
        PENDING = "pending", "Pending Payment"
        COMPLETED = "completed", "Completed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='shopify_checkouts',
        help_text="Django user who initiated the checkout"
    )
    store = models.ForeignKey(
        ShopifyStore,
        on_delete=models.PROTECT,
        related_name='checkouts',
        help_text="Shopify store for this checkout"
    )
    checkout_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="Shopify checkout ID (e.g., 'gid://shopify/Checkout/...')"
    )
    checkout_token = models.CharField(
        max_length=255,
        help_text="Shopify checkout token for accessing checkout"
    )
    checkout_url = models.URLField(
        max_length=500,
        help_text="URL to redirect user to complete checkout"
    )
    status = models.CharField(
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.CREATED,
        help_text="Current status of the checkout"
    )
    total_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Total price in store currency"
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="Currency code (ISO 4217)"
    )
    # Metadata for tracking what user was purchasing
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata (e.g., goal_id, product_ids)"
    )
    order_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Shopify order ID after checkout completion"
    )
    order_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Human-readable order number"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When checkout was completed"
    )

    class Meta:
        verbose_name = "Shopify Checkout"
        verbose_name_plural = "Shopify Checkouts"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['checkout_token']),
        ]

    def __str__(self) -> str:
        return f"Checkout {self.checkout_id[:20]}... ({self.user.username})"


class ShopifyProduct(models.Model):
    """
    Cache of Shopify products for quick access.
    Synced periodically or on-demand from Shopify.
    """
    store = models.ForeignKey(
        ShopifyStore,
        on_delete=models.CASCADE,
        related_name='products',
        help_text="Shopify store this product belongs to"
    )
    product_id = models.CharField(
        max_length=255,
        help_text="Shopify product ID (GraphQL GID)"
    )
    variant_id = models.CharField(
        max_length=255,
        help_text="Shopify product variant ID (GraphQL GID)"
    )
    title = models.CharField(
        max_length=255,
        help_text="Product title"
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Product price in store currency"
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="Currency code"
    )
    available_for_sale = models.BooleanField(
        default=True,
        help_text="Whether product is currently available"
    )
    image_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Product image URL"
    )
    # Store full product data as JSON for flexibility
    product_data = models.JSONField(
        default=dict,
        blank=True,
        help_text="Full product data from Shopify API"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shopify Product"
        verbose_name_plural = "Shopify Products"
        unique_together = [['store', 'variant_id']]
        indexes = [
            models.Index(fields=['store', 'available_for_sale']),
            models.Index(fields=['product_id']),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.store.name})"
