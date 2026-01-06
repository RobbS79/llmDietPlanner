"""
API Views for Shopify integration.
Uses DRF APIView for class-based views.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.utils import timezone
from typing import Dict, Any, List
import logging

from .models import ShopifyStore, ShopifyCheckout, ShopifyProduct
from .shopify_service import ShopifyService
from .serializers import (
    ShopifyCheckoutCreateSerializer,
    ShopifyCheckoutSerializer,
    ShopifyProductSerializer,
)

logger = logging.getLogger(__name__)


class ShopifyCheckoutCreateView(APIView):
    """
    Create a Shopify checkout session.
    
    This endpoint creates a checkout in Shopify and returns a URL
    that the frontend can redirect the user to complete the purchase.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        """
        Create a new Shopify checkout.
        
        Request body:
        {
            "store_id": 1,  # Optional, uses default store if not provided
            "variant_ids": ["gid://shopify/ProductVariant/123"],
            "quantities": [1],
            "email": "user@example.com",  # Optional
            "metadata": {"goal_id": 1}  # Optional
        }
        
        Response:
        {
            "status": "success",
            "data": {
                "checkout_id": 1,
                "checkout_url": "https://checkout.shopify.com/...",
                "checkout_token": "...",
                "total_price": "29.99",
                "currency": "USD"
            },
            "error": null
        }
        """
        try:
            # Validate request
            serializer = ShopifyCheckoutCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": serializer.errors,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            validated_data = serializer.validated_data
            variant_ids = validated_data["variant_ids"]
            quantities = validated_data["quantities"]
            email = validated_data.get("email")
            metadata = validated_data.get("metadata", {})

            # Get store (default to first active store if not specified)
            store_id = request.data.get("store_id")
            if store_id:
                try:
                    store = ShopifyStore.objects.get(id=store_id, is_active=True)
                except ShopifyStore.DoesNotExist:
                    return Response(
                        {
                            "status": "error",
                            "data": None,
                            "error": f"Store with id {store_id} not found or inactive",
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )
            else:
                # Get default active store
                store = ShopifyStore.objects.filter(is_active=True).first()
                if not store:
                    return Response(
                        {
                            "status": "error",
                            "data": None,
                            "error": "No active Shopify store configured",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Initialize Shopify service
            shopify_service = ShopifyService(
                store_domain=store.store_domain,
                storefront_token=store.storefront_access_token,
            )

            # Build line items
            line_items: List[Dict[str, Any]] = [
                {"variantId": vid, "quantity": qty}
                for vid, qty in zip(variant_ids, quantities)
            ]

            # Use user email if not provided
            checkout_email = email or request.user.email

            # Add custom attributes for tracking
            custom_attributes = []
            if metadata:
                for key, value in metadata.items():
                    custom_attributes.append({
                        "key": str(key),
                        "value": str(value),
                    })

            # Create checkout in Shopify
            checkout_data = shopify_service.create_checkout(
                line_items=line_items,
                email=checkout_email,
                note=f"Order from user {request.user.username}",
                custom_attributes=custom_attributes,
            )

            # Extract checkout details
            checkout_id = checkout_data["id"]
            checkout_token = checkout_data["token"]
            checkout_url = checkout_data["webUrl"]
            total_price_data = checkout_data.get("totalPrice", {})
            total_price = Decimal(total_price_data.get("amount", "0"))
            currency = total_price_data.get("currencyCode", "USD")

            # Save checkout to database
            shopify_checkout = ShopifyCheckout.objects.create(
                user=request.user,
                store=store,
                checkout_id=checkout_id,
                checkout_token=checkout_token,
                checkout_url=checkout_url,
                total_price=total_price,
                currency=currency,
                metadata=metadata,
                status=ShopifyCheckout.StatusChoices.CREATED,
            )

            # Return response
            return Response(
                {
                    "status": "success",
                    "data": {
                        "checkout_id": shopify_checkout.id,
                        "checkout_url": checkout_url,
                        "checkout_token": checkout_token,
                        "total_price": str(total_price),
                        "currency": currency,
                    },
                    "error": None,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error creating Shopify checkout: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"Failed to create checkout: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ShopifyCheckoutStatusView(APIView):
    """
    Get status of a Shopify checkout.
    Updates status from Shopify if checkout has been completed.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, checkout_id: int) -> Response:
        """
        Get checkout status.
        
        Response:
        {
            "status": "success",
            "data": {
                "checkout_id": 1,
                "checkout_url": "...",
                "status": "completed",
                "order_id": "...",
                "order_number": "#1001",
                ...
            },
            "error": null
        }
        """
        try:
            checkout = ShopifyCheckout.objects.select_related("store").get(
                id=checkout_id,
                user=request.user,
            )

            # Try to sync status from Shopify
            try:
                shopify_service = ShopifyService(
                    store_domain=checkout.store.store_domain,
                    storefront_token=checkout.store.storefront_access_token,
                )
                checkout_data = shopify_service.get_checkout(checkout.checkout_token)

                # Update status if checkout is completed
                if checkout_data.get("completedAt"):
                    checkout.status = ShopifyCheckout.StatusChoices.COMPLETED
                    checkout.completed_at = timezone.now()

                    # Get order info if available
                    order_data = checkout_data.get("order")
                    if order_data:
                        checkout.order_id = order_data.get("id", "")
                        checkout.order_number = order_data.get("name", "")

                    checkout.save()

            except Exception as sync_error:
                # Log but don't fail - we'll return cached status
                logger.warning(
                    f"Failed to sync checkout status from Shopify: {str(sync_error)}"
                )

            serializer = ShopifyCheckoutSerializer(checkout)

            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        except ShopifyCheckout.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": "Checkout not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Error retrieving checkout status: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ShopifyCheckoutListView(APIView):
    """
    List all checkouts for the authenticated user.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """
        Get list of user's Shopify checkouts.
        
        Query parameters:
        - status: Filter by status (optional)
        - limit: Number of results (default 50)
        - offset: Offset for pagination (default 0)
        """
        try:
            queryset = ShopifyCheckout.objects.filter(
                user=request.user
            ).select_related("store").order_by("-created_at")

            # Filter by status if provided
            status_filter = request.query_params.get("status")
            if status_filter:
                queryset = queryset.filter(status=status_filter)

            # Pagination
            limit = int(request.query_params.get("limit", 50))
            offset = int(request.query_params.get("offset", 0))
            queryset = queryset[offset : offset + limit]

            serializer = ShopifyCheckoutSerializer(queryset, many=True)

            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error listing checkouts: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ShopifyProductListView(APIView):
    """
    List available Shopify products (from cache).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """
        Get list of available Shopify products.
        
        Query parameters:
        - store_id: Filter by store (optional)
        - available_only: Only show available products (default true)
        """
        try:
            queryset = ShopifyProduct.objects.select_related("store").order_by("title")

            # Filter by store if provided
            store_id = request.query_params.get("store_id")
            if store_id:
                queryset = queryset.filter(store_id=store_id)

            # Filter by availability
            available_only = request.query_params.get("available_only", "true").lower() == "true"
            if available_only:
                queryset = queryset.filter(available_for_sale=True)

            serializer = ShopifyProductSerializer(queryset, many=True)

            return Response(
                {
                    "status": "success",
                    "data": serializer.data,
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.error(f"Error listing products: {str(e)}", exc_info=True)
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
