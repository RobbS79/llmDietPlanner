"""
URL configuration for login_app.
Includes social authentication endpoints.
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from . import social_views # Ensure this import is present

app_name = 'login_app'

urlpatterns = [
    path('register/', views.RegistrationView.as_view(), name='register'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('test-email/', views.TestEmailView.as_view(), name='test-email'),
    
    # Social Auth Endpoints
    path('google/', social_views.GoogleLoginView.as_view(), name='google_login'),
    path('google/diagnostic/', social_views.GoogleOAuthDiagnosticView.as_view(), name='google-diagnostic'),
]