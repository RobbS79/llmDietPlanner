from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .social_views import GoogleLogin

app_name = 'login_app'

urlpatterns = [
    # 1. The DOOR the frontend clicks: REDIRECTS to Google
    path('google/login/', views.GoogleLoginRedirectView.as_view(), name='google_redirect'),
    
    # 2. The CALLBACK: Handles the token exchange after Google is done
    path('google/', GoogleLogin.as_view(), name='google_login'),
    path('google/callback/', views.GoogleCallbackView.as_view(), name='google_callback'),
    
    # 3. Standard Auth
    path('register/', views.RegistrationView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Optional dj-rest-auth paths
    path('', include('dj_rest_auth.urls')),
]