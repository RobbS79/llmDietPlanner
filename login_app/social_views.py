"""
Social authentication views for Google and Facebook OAuth.

Uses dj-rest-auth's SocialLoginView with JWT support.
These views accept OAuth access tokens or authorization codes from the frontend
and return JWT tokens for authenticated API access.

Usage:
    POST /api/auth/google/
    Body: { "access_token": "..." } or { "code": "...", "redirect_uri": "..." }

    POST /api/auth/facebook/
    Body: { "access_token": "..." } or { "code": "...", "redirect_uri": "..." }

Response (standardized format):
    {
        "status": "success",
        "data": {
            "access": "jwt_access_token",
            "refresh": "jwt_refresh_token",
            "user": {
                "pk": 1,
                "username": "john",
                "email": "john@example.com",
                ...
            }
        },
        "error": null
    }
"""
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.facebook.views import FacebookOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from django.conf import settings
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import logging

logger = logging.getLogger(__name__)


class StandardizedSocialLoginView(SocialLoginView):
    """
    Base class for social login views with standardized response format.
    
    Wraps dj-rest-auth's SocialLoginView to return responses in our standard format:
    { "status": "success", "data": {...}, "error": null }
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def dispatch(self, request, *args, **kwargs):
        """Override to add CSRF exemption for OAuth callbacks."""
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        """
        Handle social authentication POST request.
        """
        # Check if OAuth credentials are configured
        if not self._check_credentials_configured():
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"{self.provider_name} OAuth credentials are not configured. Please set environment variables."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        try:
            # Call parent's post method to handle OAuth authentication
            response = super().post(request, *args, **kwargs)
            
            # If authentication was successful, standardize the response
            if response.status_code == status.HTTP_200_OK:
                return Response(
                    {
                        "status": "success",
                        "data": response.data,
                        "error": None
                    },
                    status=status.HTTP_200_OK
                )
            else:
                # Handle error responses from parent
                error_message = "Authentication failed"
                if isinstance(response.data, dict):
                    error_detail = response.data.get('non_field_errors', [])
                    if not error_detail:
                        error_detail = response.data.get('error', [])
                    if error_detail:
                        error_message = error_detail[0] if isinstance(error_detail, list) else str(error_detail)
                    elif 'access_token' in response.data or 'code' in response.data:
                        error_message = "Invalid access token or authorization code"
                
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": error_message
                    },
                    status=response.status_code
                )
                
        except Exception as e:
            logger.exception(f"Error during {self.provider_name} authentication")
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred during {self.provider_name} authentication: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _check_credentials_configured(self) -> bool:
        """Check if OAuth credentials are properly configured."""
        return True


@method_decorator(csrf_exempt, name='dispatch')
class GoogleLogin(StandardizedSocialLoginView):
    """
    Google OAuth2 login endpoint.
    """
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    provider_name = "Google"
    credential_env_vars = "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET"
    # Prioritize settings but fallback to the production URL for this DigitalOcean environment
    callback_url = getattr(settings, 'GOOGLE_CALLBACK_URL', "https://squid-app-6avsy.ondigitalocean.app/")

    def _check_credentials_configured(self) -> bool:
        google_provider = settings.SOCIALACCOUNT_PROVIDERS.get('google', {})
        app_config = google_provider.get('APP', {})
        return bool(app_config.get('client_id') and app_config.get('secret'))


@method_decorator(csrf_exempt, name='dispatch')
class FacebookLogin(StandardizedSocialLoginView):
    """
    Facebook OAuth2 login endpoint.
    """
    adapter_class = FacebookOAuth2Adapter
    client_class = OAuth2Client
    provider_name = "Facebook"
    credential_env_vars = "FACEBOOK_APP_ID, FACEBOOK_APP_SECRET"
    callback_url = getattr(settings, 'FACEBOOK_CALLBACK_URL', None)
    
    def _check_credentials_configured(self) -> bool:
        facebook_provider = settings.SOCIALACCOUNT_PROVIDERS.get('facebook', {})
        app_config = facebook_provider.get('APP', {})
        return bool(app_config.get('client_id') and app_config.get('secret'))


class GoogleOAuthDiagnosticView(APIView):
    """
    Diagnostic endpoint to verify social auth configuration.
    Endpoint: /api/auth/google/diagnostic/
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        from allauth.socialaccount.models import SocialApp
        google_app = SocialApp.objects.filter(provider='google').first()
        
        return Response({
            "status": "success",
            "google_app_configured": google_app is not None,
            "client_id_found": google_app.client_id[:10] + "..." if google_app else None,
            "configured_callback": getattr(settings, 'GOOGLE_CALLBACK_URL', "Not Set"),
            "message": "Social authentication backend is reachable."
        })