from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from . import views

class GoogleLogin(SocialLoginView):
    """
    Standardized Google Login view.
    The callback_url MUST match exactly what is in Google Cloud Console.
    """
    adapter_class = GoogleOAuth2Adapter
    callback_url = "https://squid-app-6avsy.ondigitalocean.app/api/auth/google/callback/"
    client_class = OAuth2Client

app_name = 'login_app'

urlpatterns = [
    # Social Auth
    path('google/', GoogleLogin.as_view(), name='google_login'),
    
    # Standard Auth
    path('register/', views.RegistrationView.as_view(), name='register'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    # Optional rest-auth views
    path('', include('dj_rest_auth.urls')),
]