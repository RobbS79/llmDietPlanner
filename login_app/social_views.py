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
                "free_generations_remaining": 10,
                "primary_auth_provider": "google",
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
        
        Returns standardized response format matching our API conventions.
        """
        # Check if OAuth credentials are configured
        if not self._check_credentials_configured():
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"{self.provider_name} OAuth credentials are not configured. Please set {self.credential_env_vars} environment variables."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        try:
            # Call parent's post method to handle OAuth authentication
            response = super().post(request, *args, **kwargs)
            
            # If authentication was successful, standardize the response
            if response.status_code == status.HTTP_200_OK:
                # dj-rest-auth returns response.data directly, wrap it in our format
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
                    # Extract error message from dj-rest-auth response
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
        # This method should be overridden by subclasses
        return True


@method_decorator(csrf_exempt, name='dispatch')
class GoogleLogin(StandardizedSocialLoginView):
    """
    Google OAuth2 login endpoint.

    Accepts either:
    - access_token: Direct access token from Google
    - code + redirect_uri: Authorization code flow (requires GOOGLE_CALLBACK_URL)

    Returns JWT tokens and user info on successful authentication.
    Creates a new user if one doesn't exist with the Google email.
    Links to existing account if email already registered.

    Environment variables required:
    - GOOGLE_CLIENT_ID: OAuth 2.0 Client ID from Google Cloud Console
    - GOOGLE_CLIENT_SECRET: OAuth 2.0 Client Secret from Google Cloud Console
    - GOOGLE_CALLBACK_URL: (Optional) Callback URL for authorization code flow
    """
    adapter_class = GoogleOAuth2Adapter
    callback_url = getattr(settings, 'GOOGLE_CALLBACK_URL', None)
    client_class = OAuth2Client
    provider_name = "Google"
    credential_env_vars = "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET"

    def _check_credentials_configured(self) -> bool:
        """Check if Google OAuth credentials are configured."""
        google_provider = settings.SOCIALACCOUNT_PROVIDERS.get('google', {})
        app_config = google_provider.get('APP', {})
        client_id = app_config.get('client_id', '')
        client_secret = app_config.get('secret', '')
        return bool(client_id and client_secret)

    def post(self, request, *args, **kwargs):
        """Override post to add debug logging."""
        import sys
        import traceback

        print(f"[DEBUG OAUTH] GoogleLogin.post: Request received", file=sys.stderr, flush=True)
        print(f"[DEBUG OAUTH] GoogleLogin.post: Request data keys: {list(request.data.keys())}", file=sys.stderr, flush=True)
        print(f"[DEBUG OAUTH] GoogleLogin.post: Has access_token: {'access_token' in request.data}", file=sys.stderr, flush=True)
        print(f"[DEBUG OAUTH] GoogleLogin.post: Has code: {'code' in request.data}", file=sys.stderr, flush=True)

        # Check credentials
        if not self._check_credentials_configured():
            print(f"[DEBUG OAUTH] GoogleLogin.post: Credentials NOT configured!", file=sys.stderr, flush=True)
        else:
            print(f"[DEBUG OAUTH] GoogleLogin.post: Credentials are configured", file=sys.stderr, flush=True)

        try:
            # Call parent's post method
            response = super().post(request, *args, **kwargs)
            print(f"[DEBUG OAUTH] GoogleLogin.post: Response status: {response.status_code}", file=sys.stderr, flush=True)
            print(f"[DEBUG OAUTH] GoogleLogin.post: Response data keys: {list(response.data.keys()) if hasattr(response.data, 'keys') else type(response.data)}", file=sys.stderr, flush=True)
            return response
        except Exception as e:
            print(f"[DEBUG OAUTH] GoogleLogin.post: EXCEPTION: {str(e)}", file=sys.stderr, flush=True)
            print(f"[DEBUG OAUTH] GoogleLogin.post: Traceback:\n{traceback.format_exc()}", file=sys.stderr, flush=True)
            raise


@method_decorator(csrf_exempt, name='dispatch')
class FacebookLogin(StandardizedSocialLoginView):
    """
    Facebook OAuth2 login endpoint.

    Accepts either:
    - access_token: Direct access token from Facebook
    - code + redirect_uri: Authorization code flow (requires FACEBOOK_CALLBACK_URL)

    Returns JWT tokens and user info on successful authentication.
    Creates a new user if one doesn't exist with the Facebook email.
    Links to existing account if email already registered.
    
    Environment variables required:
    - FACEBOOK_APP_ID: App ID from Facebook Developers Console
    - FACEBOOK_APP_SECRET: App Secret from Facebook Developers Console
    - FACEBOOK_CALLBACK_URL: (Optional) Callback URL for authorization code flow
    """
    adapter_class = FacebookOAuth2Adapter
    callback_url = getattr(settings, 'FACEBOOK_CALLBACK_URL', None)
    client_class = OAuth2Client
    provider_name = "Facebook"
    credential_env_vars = "FACEBOOK_APP_ID, FACEBOOK_APP_SECRET"
    
    def _check_credentials_configured(self) -> bool:
        """Check if Facebook OAuth credentials are configured."""
        facebook_provider = settings.SOCIALACCOUNT_PROVIDERS.get('facebook', {})
        app_config = facebook_provider.get('APP', {})
        app_id = app_config.get('client_id', '')
        app_secret = app_config.get('secret', '')
        return bool(app_id and app_secret)
