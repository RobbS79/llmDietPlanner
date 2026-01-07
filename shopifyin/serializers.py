"""
Serializers for Shopify integration endpoints.
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import ShopifyStore, ShopifyCheckout, ShopifyProduct


class ShopifyCheckoutCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a Shopify checkout.
    
    Example request:
    {
        "variant_ids": ["gid://shopify/ProductVariant/123"],
        "quantities": [1],
        "email": "user@example.com",
        "metadata": {"goal_id": 1}
    }
    """
    variant_ids = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        help_text="List of Shopify product variant IDs (GraphQL GIDs)"
    )
    quantities = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        min_length=1,
        help_text="List of quantities corresponding to variant_ids"
    )
    email = serializers.EmailField(
        required=False,
        allow_null=True,
        help_text="Optional customer email"
    )
    metadata = serializers.DictField(
        required=False,
        allow_empty=True,
        default=dict,
        help_text="Optional metadata to store with checkout (e.g., goal_id)"
    )

    def validate(self, attrs: dict) -> dict:
        """Validate that variant_ids and quantities lists have the same length."""
        variant_ids = attrs.get("variant_ids", [])
        quantities = attrs.get("quantities", [])

        if len(variant_ids) != len(quantities):
            raise serializers.ValidationError(
                "variant_ids and quantities must have the same length"
            )

        return attrs


class ShopifyCheckoutSerializer(serializers.ModelSerializer):
    """Serializer for Shopify checkout model."""
    user = serializers.ReadOnlyField(source="user.username")
    store_name = serializers.ReadOnlyField(source="store.name")

    class Meta:
        model = ShopifyCheckout
        fields = [
            "id",
            "user",
            "store_name",
            "checkout_id",
            "checkout_url",
            "status",
            "total_price",
            "currency",
            "metadata",
            "order_id",
            "order_number",
            "created_at",
            "updated_at",
            "completed_at",
        ]
        read_only_fields = [
            "id",
            "checkout_id",
            "checkout_url",
            "status",
            "total_price",
            "currency",
            "order_id",
            "order_number",
            "created_at",
            "updated_at",
            "completed_at",
        ]


class ShopifyProductSerializer(serializers.ModelSerializer):
    """Serializer for Shopify product cache."""
    store_name = serializers.ReadOnlyField(source="store.name")

    class Meta:
        model = ShopifyProduct
        fields = [
            "id",
            "store_name",
            "product_id",
            "variant_id",
            "title",
            "price",
            "currency",
            "available_for_sale",
            "image_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]


