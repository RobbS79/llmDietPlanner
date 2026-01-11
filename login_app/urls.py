"""
Refactored URL configuration for login_app including Google OAuth routes.
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'login_app'

urlpatterns = [
    path('register/', views.RegistrationView.as_view(), name='register'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('test-email/', views.TestEmailView.as_view(), name='test-email'),
    
    # NEW ROUTES FOR GOOGLE AUTH
    path('google/login/', views.GoogleLoginView.as_view(), name='google-login'),
    path('google/callback/', views.GoogleCallbackView.as_view(), name='google-callback'),
]