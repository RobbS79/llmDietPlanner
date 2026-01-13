from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .social_views import GoogleLogin

"""
LOGIN_APP URL CONFIGURATION
===========================
Mounted at /api/auth/ in the root urls.py.
Final URLs look like: /api/auth/google/login/
"""

app_name = 'login_app'

urlpatterns = [
    # --- GOOGLE OAUTH FLOW ---
    
    # Step 1: The 'Door' (Frontend clicks this)
    # URL: /api/auth/google/login/
    path('google/login/', views.GoogleLoginRedirectView.as_view(), name='google_redirect'),
    
    # Step 2: The Callback (Google returns here with a code)
    # URL: /api/auth/google/callback/
    path('google/callback/', views.GoogleCallbackView.as_view(), name='google_callback'),
    
    # Step 3: The JWT Issuer (Callback uses this internally or for mobile token exchange)
    # URL: /api/auth/google/
    path('google/', GoogleLogin.as_view(), name='google_login'),
    
    
    # --- STANDARD AUTHENTICATION ---
    
    # URL: /api/auth/register/
    path('register/', views.RegistrationView.as_view(), name='register'),
    
    # URL: /api/auth/login/
    path('login/', views.LoginView.as_view(), name='login'),
    
    # URL: /api/auth/refresh/
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Optional dj-rest-auth paths for profile management
    path('', include('dj_rest_auth.urls')),
]