"""
URL configuration for shopifyin app.
"""
from django.urls import path
from . import views
from . import webhooks

app_name = "shopifyin"

urlpatterns = [
    # Debug endpoint - remove after fixing
    path(
        "debug/",
        views.ShopifyDebugView.as_view(),
        name="debug",
    ),
    path(
        "checkouts/",
        views.ShopifyCheckoutCreateView.as_view(),
        name="checkout-create",
    ),
    path(
        "checkouts/list/",
        views.ShopifyCheckoutListView.as_view(),
        name="checkout-list",
    ),
    path(
        "checkouts/<int:checkout_id>/",
        views.ShopifyCheckoutStatusView.as_view(),
        name="checkout-status",
    ),
    path(
        "products/",
        views.ShopifyProductListView.as_view(),
        name="product-list",
    ),
    # Shopify webhooks
    path(
        "webhooks/order-paid/",
        webhooks.shopify_order_paid_webhook,
        name="webhook-order-paid",
    ),
    path(
        "webhooks/order-cancelled/",
        webhooks.shopify_order_cancelled_webhook,
        name="webhook-order-cancelled",
    ),
]


