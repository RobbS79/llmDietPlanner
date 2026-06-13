"""URL configuration for the billing app (mounted at /api/billing/)."""
from django.urls import path

from . import views

app_name = 'billing'

urlpatterns = [
    path('plans/', views.PlansView.as_view(), name='plans'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('portal/', views.PortalView.as_view(), name='portal'),
    path('me/', views.MeView.as_view(), name='me'),
    path('webhook/', views.WebhookView.as_view(), name='webhook'),
]
