"""
URL configuration for login_app.

Includes:
- Email-based authentication (register, login, verify-email)
- JWT token refresh
- User profile
- Social authentication (Google, Facebook OAuth)
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import social_views

app_name = 'login_app'

urlpatterns = [
    # Email-based authentication
    path('register/', views.RegistrationView.as_view(), name='register'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('test-email/', views.TestEmailView.as_view(), name='test-email'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),

    # Social authentication (OAuth)
    path('google/', social_views.GoogleLogin.as_view(), name='google-login'),
    path('facebook/', social_views.FacebookLogin.as_view(), name='facebook-login'),
]

