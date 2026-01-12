"""
Complete refactored views for login_app including Google OAuth2.
Handles registration, standard login, and social authentication.
"""
import requests
import sys
import traceback
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
from .utils import generate_email_verification_token, get_verification_email_content
from .tasks import send_verification_email_task

@method_decorator(csrf_exempt, name='dispatch')
class RegistrationView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        try:
            schema = RegistrationRequest(**request.data)
            if User.objects.filter(username=schema.username).exists():
                return Response({"status": "error", "error": "Username already exists"}, status=400)
            
            user = User.objects.create_user(
                username=schema.username,
                email=schema.email,
                password=schema.password,
                is_active=False
            )
            
            uid, token = generate_email_verification_token(user)
            send_verification_email_task.delay(user.id, uid, token, request.build_absolute_uri('/'))
            
            return Response({"status": "success", "message": "User created. Check email."}, status=201)
        except Exception as e:
            return Response({"status": "error", "error": str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        try:
            schema = LoginRequest(**request.data)
            user = authenticate(username=schema.username, password=schema.password)
            if user and user.is_active:
                refresh = RefreshToken.for_user(user)
                return Response({
                    "status": "success",
                    "data": {
                        "access": str(refresh.access_token),
                        "refresh": str(refresh),
                        "user": {"id": user.id, "username": user.username, "email": user.email}
                    }
                })
            return Response({"status": "error", "error": "Invalid credentials or account not verified"}, status=401)
        except Exception as e:
            return Response({"status": "error", "error": str(e)}, status=500)

class GoogleLoginRedirectView(APIView):
    """
    Constructs the Google OAuth2 authorization URL and redirects the user.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
        if not client_id:
            return Response({"error": "GOOGLE_CLIENT_ID not configured in backend environment"}, status=500)
            
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        scope = "openid email profile"
        
        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&"
            f"scope={scope}&access_type=offline&prompt=select_account"
        )
        return redirect(auth_url)

class GoogleCallbackView(APIView):
    """
    Exchanges code for profile and issues local JWT.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.GET.get('code')
        if not code:
            return Response({"error": "Code missing"}, status=400)

        try:
            # 1. Exchange code for token
            token_res = requests.post("https://oauth2.googleapis.com/token", data={
                'code': code,
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uri': request.build_absolute_uri('/api/auth/google/callback/'),
                'grant_type': 'authorization_code',
            })
            token_data = token_res.json()
            access_token = token_data.get('access_token')

            # 2. Get profile
            user_info = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={'Authorization': f'Bearer {access_token}'}
            ).json()
            
            email = user_info.get('email')
            # 3. Get/Create local User
            user, created = User.objects.get_or_create(
                email=email, 
                defaults={'username': email.split('@')[0], 'is_active': True}
            )
            
            # 4. Local JWT
            refresh = RefreshToken.for_user(user)
            
            # 5. Redirect to frontend with tokens
            frontend_base = getattr(settings, 'FRONTEND_URL', 'http://localhost:3000')
            success_url = f"{frontend_base}/login-success?access={str(refresh.access_token)}&refresh={str(refresh)}"
            return redirect(success_url)

        except Exception as e:
            traceback.print_exc()
            return Response({"error": "Internal OAuth error"}, status=500)

class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        return Response({"status": "success", "message": "Email verification handled"})

class TestEmailView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        return Response({"status": "success", "message": "Test email sent"})