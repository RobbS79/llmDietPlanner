"""
URL configuration for shopifyin app.
"""
from django.urls import path
from . import views

app_name = "shopifyin"

urlpatterns = [
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
]

