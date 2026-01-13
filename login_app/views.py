# File: login_app/views.py
import requests
import sys
import uuid
import logging
from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile

logger = logging.getLogger(__name__)

class GoogleLoginRedirectView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
        
        # Determine redirect URI and force HTTPS in production
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        if not settings.DEBUG:
            redirect_uri = redirect_uri.replace('http://', 'https://')
            
        print(f"\n[DEBUG OAUTH] Redirecting to Google", file=sys.stderr)
        print(f"[DEBUG OAUTH] Client ID: {client_id[:10] if client_id else 'None'}...", file=sys.stderr)
        print(f"[DEBUG OAUTH] Redirect URI: {redirect_uri}", file=sys.stderr)

        if not client_id:
            return redirect('/login?error=google_not_configured')

        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&"
            f"scope=openid%20email%20profile&access_type=offline&prompt=select_account"
        )
        return redirect(auth_url)

class GoogleCallbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.GET.get('code')
        
        # Reconstruct the EXACT same redirect_uri used in the first step
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        if not settings.DEBUG:
            redirect_uri = redirect_uri.replace('http://', 'https://')
            
        print(f"\n[DEBUG OAUTH] Callback Received", file=sys.stderr)
        print(f"[DEBUG OAUTH] Code present: {bool(code)}", file=sys.stderr)

        if not code:
            return redirect('/login?error=missing_code')

        try:
            # 1. Exchange code for Google Access Token
            token_res = requests.post("https://oauth2.googleapis.com/token", data={
                'code': code,
                'client_id': settings.GOOGLE_CLIENT_ID,
                'client_secret': settings.GOOGLE_CLIENT_SECRET,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            }, timeout=10)
            
            if token_res.status_code != 200:
                print(f"[DEBUG OAUTH] Token exchange 400/error: {token_res.text}", file=sys.stderr)
                return redirect('/login?error=token_exchange_failed')
            
            token_data = token_res.json()
            access_token = token_data.get('access_token')

            # 2. Get User Profile
            user_info = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10
            ).json()
            
            email = user_info.get('email')
            if not email:
                return redirect('/login?error=email_access_denied')

            # 3. User Management
            with transaction.atomic():
                user = User.objects.filter(email=email).first()
                if not user:
                    username = email.split('@')[0]
                    # Ensure uniqueness
                    while User.objects.filter(username=username).exists():
                        username = f"{username}_{uuid.uuid4().hex[:4]}"
                    user = User.objects.create_user(username=username, email=email, is_active=True)
                
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.primary_auth_provider = 'google'
                profile.email_verified = True
                profile.save()

            # 4. Issue Tokens
            refresh = RefreshToken.for_user(user)
            return redirect(f"/login-success?access={str(refresh.access_token)}&refresh={str(refresh)}")

        except Exception as e:
            print(f"[DEBUG OAUTH] CRITICAL: {str(e)}", file=sys.stderr)
            return redirect('/login?error=auth_failed')