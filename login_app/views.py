import requests
import sys
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
    def post(self, request):
        try:
            schema = RegistrationRequest(**request.data)
            if User.objects.filter(username=schema.username).exists():
                return Response({"error": "Username already exists"}, status=400)
            user = User.objects.create_user(username=schema.username, email=schema.email, password=schema.password, is_active=False)
            
            # Async email send
            uid, token = generate_email_verification_token(user)
            send_verification_email_task.delay(user_id=user.id, uid=uid, token=token, base_url=request.build_absolute_uri('/'))
            
            return Response({"status": "success", "message": "Verification email sent."}, status=201)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
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
            return Response({"error": "Invalid credentials"}, status=401)
        except Exception as e:
            return Response({"error": str(e)}, status=500)

class GoogleLoginRedirectView(APIView):
    """
    Constructs the Google OAuth2 URL and redirects the user.
    """
    permission_classes = [AllowAny]
    def get(self, request):
        client_id = settings.GOOGLE_CLIENT_ID
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
    Handles the Google redirect, exchanges code for user profile, and returns local tokens.
    """
    permission_classes = [AllowAny]
    def get(self, request):
        code = request.GET.get('code')
        if not code: return Response({"error": "No code provided"}, status=400)

        # 1. Exchange code for access token
        token_res = requests.post("https://oauth2.googleapis.com/token", data={
            'code': code,
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'redirect_uri': request.build_absolute_uri('/api/auth/google/callback/'),
            'grant_type': 'authorization_code',
        })
        token_data = token_res.json()
        access_token = token_data.get('access_token')

        # 2. Get user info
        user_info = requests.get("https://www.googleapis.com/oauth2/v3/userinfo", 
                                 headers={'Authorization': f'Bearer {access_token}'}).json()
        
        email = user_info.get('email')
        # 3. Create or Update local user
        user, created = User.objects.get_or_create(email=email, defaults={'username': email.split('@')[0], 'is_active': True})
        
        # 4. Generate local JWT
        refresh = RefreshToken.for_user(user)
        
        # 5. Redirect back to frontend success page
        frontend_base = getattr(settings, 'FRONTEND_URL', 'https://squid-app-6avsy.ondigitalocean.app')
        return redirect(f"{frontend_base}/login-success?access={str(refresh.access_token)}&refresh={str(refresh)}")

@method_decorator(csrf_exempt, name='dispatch')
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        return Response({"message": "Verification logic goes here"})

@method_decorator(csrf_exempt, name='dispatch')
class TestEmailView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        return Response({"message": "Email test logic goes here"})