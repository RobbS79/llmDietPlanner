"""
login_app/views.py
==================
Production-grade Authentication and Social OAuth2 views.
Ensures unique identity mapping, profile synchronization, and strict API standardization.
"""

import requests
import logging
import uuid
import traceback
from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserProfile
from .schemas import RegistrationRequest, LoginRequest
from .utils import generate_email_verification_token
from .tasks import send_verification_email_task

logger = logging.getLogger(__name__)

class GoogleLoginRedirectView(APIView):
    """
    Step 1: The Redirector.
    URL: /api/auth/google/login/
    Constructs the authoritative Google OAuth2 URL and redirects the browser.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
        
        # If credentials are missing in DigitalOcean, redirect back to login 
        # so the React app can display a professional error message.
        if not client_id:
            logger.critical("OAuth Configuration Error: GOOGLE_CLIENT_ID is missing.")
            return redirect('/login?error=google_not_configured')

        # The callback URI must be registered in Google Cloud Console
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        scope = "openid email profile"
        
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&"
            f"scope={scope}&access_type=offline&prompt=select_account"
        )
        
        logger.info(f"Initiating Google OAuth redirect to: {redirect_uri}")
        return redirect(auth_url)

class GoogleCallbackView(APIView):
    """
    Step 2: The Handler.
    URL: /api/auth/google/callback/
    Exchanges the authorization code for tokens and synchronizes the local user.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.GET.get('code')
        if not code:
            logger.warning("OAuth Callback hit without authorization code.")
            return redirect('/login?error=missing_code')

        try:
            # 1. Exchange code for Google Access Token
            token_res = requests.post("https://oauth2.googleapis.com/token", data={
                'code': code,
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uri': request.build_absolute_uri('/api/auth/google/callback/'),
                'grant_type': 'authorization_code',
            }, timeout=10)
            
            if token_res.status_code != 200:
                logger.error(f"Google Token Exchange Failed: {token_res.text}")
                return redirect('/login?error=token_exchange_failed')
            
            token_data = token_res.json()
            google_access_token = token_data.get('access_token')

            # 2. Retrieve User Profile from Google
            user_info_res = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={'Authorization': f'Bearer {google_access_token}'},
                timeout=10
            )
            user_info = user_info_res.json()
            email = user_info.get('email')
            
            if not email:
                return redirect('/login?error=email_access_denied')

            # 3. Secure User Match & Creation (Atomic)
            with transaction.atomic():
                user = User.objects.filter(email=email).first()
                if not user:
                    # Robust Identity Logic: Handle username collisions
                    base_username = email.split('@')[0]
                    username = base_username
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}_{uuid.uuid4().hex[:4]}"
                    
                    user = User.objects.create_user(
                        username=username,
                        email=email,
                        is_active=True # Google users are pre-verified
                    )
                
                # 4. Profile Synchronization
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.primary_auth_provider = 'google'
                profile.email_verified = True
                profile.save()

            # 5. Issue local JWT tokens for the SPA
            refresh = RefreshToken.for_user(user)
            
            logger.info(f"OAuth Success: {email} session initiated.")
            
            # Redirect to the frontend success handler route
            success_url = f"/login-success?access={str(refresh.access_token)}&refresh={str(refresh)}"
            return redirect(success_url)

        except Exception as e:
            logger.error(f"OAuth Internal Failure: {str(e)}")
            return redirect('/login?error=auth_internal_failure')

@method_decorator(csrf_exempt, name='dispatch')
class RegistrationView(APIView):
    """
    Standard Email Registration.
    Validated via Pydantic Schemas.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        try:
            # Type-safe validation using Pydantic
            schema = RegistrationRequest(**request.data)
            
            if User.objects.filter(username=schema.username).exists():
                return Response({"status": "error", "data": None, "error": "Username already taken"}, status=400)
            
            if User.objects.filter(email=schema.email).exists():
                return Response({"status": "error", "data": None, "error": "Email already registered"}, status=400)
            
            with transaction.atomic():
                user = User.objects.create_user(
                    username=schema.username,
                    email=schema.email,
                    password=schema.password,
                    is_active=False # Pending email verification
                )
                
                # Generate verification token
                uid, token = generate_email_verification_token(user)
                
                # Offload email sending to background Celery task
                send_verification_email_task.delay(user.id, uid, token, request.build_absolute_uri('/'))
            
            return Response({
                "status": "success", 
                "data": {"message": "Account created. Please check your email to verify."},
                "error": None
            }, status=201)
            
        except Exception as e:
            logger.error(f"Registration Error: {str(e)}")
            return Response({"status": "error", "data": None, "error": "Failed to create account"}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    """
    Standard Email Login.
    Issues JWT tokens for valid credentials.
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
                return Response({"status": "error", "data": None, "error": "Account not verified"}, status=403)
                
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
            return Response({"status": "error", "data": None, "error": "Login failed"}, status=500)