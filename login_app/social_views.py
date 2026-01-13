# File: login_app/social_views.py
"""
Social authentication views for Google and Facebook OAuth.
Updated with enhanced logging to debug credential mismatches.
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
import sys
import json

logger = logging.getLogger(__name__)

class StandardizedSocialLoginView(SocialLoginView):
    """
    Base class for social login views with standardized response format.
    Wraps dj-rest-auth's SocialLoginView with deep debug logging.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request, *args, **kwargs):
        # --- DEBUG LOGGING ---
        print(f"\n[DEBUG OAUTH] Incoming {self.provider_name} Login Request", file=sys.stderr)
        print(f"[DEBUG OAUTH] Request Data: {json.dumps(request.data)}", file=sys.stderr)
        
        # Check if OAuth credentials are configured in Django settings
        if not self._check_credentials_configured():
            error_msg = f"{self.provider_name} credentials missing in BACKEND settings (settings.py/env vars)."
            print(f"[DEBUG OAUTH] ERROR: {error_msg}", file=sys.stderr)
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": error_msg,
                    "debug_info": "Check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on server."
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        try:
            # Call parent's post method (dj-rest-auth) to handle actual token exchange
            print(f"[DEBUG OAUTH] Proceeding to provider handshake...", file=sys.stderr)
            response = super().post(request, *args, **kwargs)
            
            if response.status_code == status.HTTP_200_OK:
                print(f"[DEBUG OAUTH] SUCCESS: User authenticated via {self.provider_name}", file=sys.stderr)
                return Response(
                    {
                        "status": "success",
                        "data": response.data,
                        "error": None
                    },
                    status=status.HTTP_200_OK
                )
            else:
                # Provide much more detail for failures
                print(f"[DEBUG OAUTH] FAILURE: Provider returned status {response.status_code}", file=sys.stderr)
                print(f"[DEBUG OAUTH] Provider Error Data: {response.data}", file=sys.stderr)
                
                error_message = "Social authentication failed."
                if isinstance(response.data, dict):
                    error_detail = response.data.get('non_field_errors', []) or response.data.get('error', [])
                    if error_detail:
                        error_message = error_detail[0] if isinstance(error_detail, list) else str(error_detail)
                    elif 'access_token' in response.data:
                        error_message = "The access token provided was rejected by Google/Facebook."
                
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": error_message,
                        "raw_provider_response": response.data
                    },
                    status=response.status_code
                )
                
        except Exception as e:
            print(f"[DEBUG OAUTH] EXCEPTION: {str(e)}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"Internal auth failure: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _check_credentials_configured(self) -> bool:
        return True

@method_decorator(csrf_exempt, name='dispatch')
class GoogleLogin(StandardizedSocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    provider_name = "Google"
    
    def _check_credentials_configured(self) -> bool:
        # Verify both ID and Secret are present
        google_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
        google_secret = getattr(settings, 'GOOGLE_CLIENT_SECRET', None)
        
        print(f"[DEBUG CONFIG] Google Client ID Present: {bool(google_id)}", file=sys.stderr)
        print(f"[DEBUG CONFIG] Google Client Secret Present: {bool(google_secret)}", file=sys.stderr)
        
        return bool(google_id and google_secret)

@method_decorator(csrf_exempt, name='dispatch')
class FacebookLogin(StandardizedSocialLoginView):
    adapter_class = FacebookOAuth2Adapter
    client_class = OAuth2Client
    provider_name = "Facebook"
    
    def _check_credentials_configured(self) -> bool:
        facebook_id = getattr(settings, 'FACEBOOK_APP_ID', None)
        facebook_secret = getattr(settings, 'FACEBOOK_APP_SECRET', None)
        return bool(facebook_id and facebook_secret)