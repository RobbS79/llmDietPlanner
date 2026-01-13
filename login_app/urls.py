from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from . import views
from .social_views import GoogleLogin

"""
LOGIN_APP URL CONFIGURATION
===========================
Mounted at /api/auth/ in the root urls.py.
All these endpoints return JSON data or perform redirects.
They do NOT serve HTML pages (React handles the UI).
"""

app_name = 'login_app'

urlpatterns = [
    # --- GOOGLE OAUTH FLOW ---
    
    # Step 1: The 'Trigger'
    # URL: /api/auth/google/login/
    # Frontend redirects the browser here to start the Google handshake.
    path('google/login/', views.GoogleLoginRedirectView.as_view(), name='google_redirect'),
    
    # Step 2: The 'Receiver'
    # URL: /api/auth/google/callback/
    # Google sends the user back here with an auth code.
    path('google/callback/', views.GoogleCallbackView.as_view(), name='google_callback'),
    
    # Step 3: The 'Token Exchange'
    # URL: /api/auth/google/
    # Used for direct token exchange (e.g. mobile or frontend-only flows).
    path('google/', GoogleLogin.as_view(), name='google_login'),
    
    
    # --- STANDARD AUTHENTICATION (JSON API) ---
    
    # URL: /api/auth/register/
    path('register/', views.RegistrationView.as_view(), name='register'),
    
    # URL: /api/auth/login/
    path('login/', views.LoginView.as_view(), name='login'),
    
    # URL: /api/auth/refresh/
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Optional dj-rest-auth paths for profile/user management
    path('', include('dj_rest_auth.urls')),
]