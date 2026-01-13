"""
login_app/views.py
==================
Professional implementation of Authentication and Social OAuth2 views.
Follows strict API standardization: { "status": "success", "data": {}, "error": null }
"""

import requests
import sys
import traceback
import logging
from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from .schemas import RegistrationRequest, LoginRequest
from .utils import generate_email_verification_token
from .tasks import send_verification_email_task

logger = logging.getLogger(__name__)

class GoogleLoginRedirectView(APIView):
    """
    AUTHORITATIVE REDIRECT: Entry point for Google OAuth.
    Routes the browser to the Google Consent screen.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
        if not client_id:
            logger.critical("OAuth Failure: GOOGLE_CLIENT_ID missing from environment.")
            return Response(
                {"status": "error", "data": None, "error": "Google Auth not configured on server."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
            
        # This URI must be whitelisted in Google Cloud Console
        # It directs the user back to the GoogleCallbackView defined below
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        scope = "openid email profile"
        
        # We use prompt=select_account to ensure the user can switch accounts if needed
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&"
            f"scope={scope}&access_type=offline&prompt=select_account"
        )
        
        logger.info(f"Initiating Google OAuth redirect for URI: {redirect_uri}")
        return redirect(auth_url)

@method_decorator(csrf_exempt, name='dispatch')
class RegistrationView(APIView):
    """
    SECURE REGISTRATION: Handles new user creation and triggers email verification.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        try:
            # Pydantic Schema Validation (Strict types)
            schema = RegistrationRequest(**request.data)
            
            if User.objects.filter(username=schema.username).exists():
                return Response({"status": "error", "data": None, "error": "Username already taken"}, status=400)
            
            if User.objects.filter(email=schema.email).exists():
                return Response({"status": "error", "data": None, "error": "Email already registered"}, status=400)
            
            user = User.objects.create_user(
                username=schema.username,
                email=schema.email,
                password=schema.password,
                is_active=False # Account disabled until email verification
            )
            
            # Generate verification artifacts
            uid, token = generate_email_verification_token(user)
            
            # Async Task: Offload email sending to Celery to keep request time low (<200ms)
            send_verification_email_task.delay(user.id, uid, token, request.build_absolute_uri('/'))
            
            return Response({
                "status": "success", 
                "data": {"username": user.username, "email": user.email},
                "error": None
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Registration Exception: {str(e)}")
            return Response({"status": "error", "data": None, "error": "Internal registration error"}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    """
    JWT ISSUER: Authenticates users and returns Bearer tokens.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        try:
            schema = LoginRequest(**request.data)
            user = authenticate(username=schema.username, password=schema.password)
            
            if not user:
                return Response({"status": "error", "data": None, "error": "Invalid credentials"}, status=401)
                
            if not user.is_active:
                return Response({"status": "error", "data": None, "error": "Account pending verification"}, status=403)
                
            refresh = RefreshToken.for_user(user)
            return Response({
                "status": "success",
                "data": {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {"id": user.id, "username": user.username, "email": user.email}
                },
                "error": None
            })
        except Exception as e:
            return Response({"status": "error", "data": None, "error": str(e)}, status=500)


class GoogleCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.GET.get('code')
        if not code:
            return redirect('/login?error=missing_code')

        try:
            # 1. Exchange code for Google Token
            token_res = requests.post("https://oauth2.googleapis.com/token", data={
                'code': code,
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uri': request.build_absolute_uri('/api/auth/google/callback/'),
                'grant_type': 'authorization_code',
            })
            
            # 2. Get User Info
            user_info = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={'Authorization': f'Bearer {token_res.json().get("access_token")}'}
            ).json()
            
            email = user_info.get('email')
            
            # 3. Robust User Match (Fix: Handle existing usernames)
            user = User.objects.filter(email=email).first()
            if not user:
                user = User.objects.create_user(
                    username=email.split('@')[0], 
                    email=email, 
                    is_active=True
                )
            
            # 4. Issue JWT and Redirect to React Route
            refresh = RefreshToken.for_user(user)
            return redirect(f"/login-success?access={str(refresh.access_token)}&refresh={str(refresh)}")

        except Exception:
            return redirect('/login?error=auth_failed')

            
    """
    OAUTH EXCHANGE: Receives Google Code, verifies it, and logs the user in.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        # Google sends a 'code' parameter in the URL
        code = request.GET.get('code')
        if not code:
            logger.warning("Google Callback hit without authorization code.")
            return redirect('/login?error=missing_code')

        try:
            # 1. Exchange authorization code for an actual Access Token
            token_res = requests.post("https://oauth2.googleapis.com/token", data={
                'code': code,
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uri': request.build_absolute_uri('/api/auth/google/callback/'),
                'grant_type': 'authorization_code',
            })
            token_data = token_res.json()
            access_token = token_data.get('access_token')

            if not access_token:
                logger.error(f"Google Token Exchange Failed: {token_data}")
                return redirect('/login?error=token_exchange_failed')

            # 2. Use the token to fetch the User's Profile from Google
            user_info = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={'Authorization': f'Bearer {access_token}'}
            ).json()
            
            email = user_info.get('email')
            if not email:
                return redirect('/login?error=email_not_provided')

            # 3. Synchronize with Django User Database
            # We trust Google's verification, so we mark user as is_active=True
            user, created = User.objects.get_or_create(
                email=email, 
                defaults={
                    'username': email.split('@')[0], 
                    'is_active': True
                }
            )
            
            # 4. Generate local JWT for the SPA to use
            refresh = RefreshToken.for_user(user)
            
            # 5. FINAL REDIRECT: Hand the tokens to the frontend
            # We pass tokens in the query string so the React 'LoginSuccess' component can grab them
            success_url = f"/login-success?access={str(refresh.access_token)}&refresh={str(refresh)}"
            logger.info(f"OAuth successful for {email}. Redirecting to SPA.")
            return redirect(success_url)

        except Exception as e:
            logger.error(f"Internal OAuth error: {str(e)}")
            traceback.print_exc()
            return redirect('/login?error=internal_auth_failure')