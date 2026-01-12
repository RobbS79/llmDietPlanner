from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'login_app'

urlpatterns = [
    # Standard email auth
    path('register/', views.RegistrationView.as_view(), name='register'),
    path('verify-email/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Google OAuth
    path('google/login/', views.GoogleLoginRedirectView.as_view(), name='google-login'),
    path('google/callback/', views.GoogleCallbackView.as_view(), name='google-callback'),
    
    # Utils
    path('test-email/', views.TestEmailView.as_view(), name='test-email'),
]