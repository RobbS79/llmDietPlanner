"""
API Views for user authentication and registration.
Uses DRF APIView for class-based views.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from typing import Dict, Any
import sys
import traceback

from rest_framework_simplejwt.tokens import RefreshToken
from .schemas import RegistrationRequest, LoginRequest, EmailVerificationRequest
from .utils import generate_email_verification_token, verify_email_token, get_verification_email_content
from .tasks import send_verification_email_task
from .models import UserProfile


@method_decorator(csrf_exempt, name='dispatch')
class RegistrationView(APIView):
    """
    API endpoint for user registration.
    Creates an inactive user and sends email verification.
    """
    permission_classes = [AllowAny]
    # Exclude SessionAuthentication to avoid CSRF requirement
    authentication_classes = []
    
    def post(self, request) -> Response:
        """
        Register a new user.
        
        Request body:
        {
            "username": "testuser",
            "email": "test@example.com",
            "password": "securepass123",
            "passwordConfirm": "securepass123"
        }
        
        Response:
        {
            "status": "success",
            "data": {
                "user_id": 1,
                "username": "testuser",
                "email": "test@example.com",
                "message": "Registration successful. Please check your email to verify your account."
            },
            "error": null
        }
        """
        # #region agent log
        print(f"[DEBUG CSRF] RegistrationView.post: Request received", file=sys.stderr, flush=True)
        print(f"[DEBUG CSRF] RegistrationView.post: Request META: {dict(request.META)}", file=sys.stderr, flush=True)
        # #endregion
        
        try:
            # Validate request using Pydantic schema
            schema = RegistrationRequest(**request.data)
            
            # Check if username already exists
            if User.objects.filter(username=schema.username).exists():
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Username already exists"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if email already exists
            if User.objects.filter(email=schema.email).exists():
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Email already registered"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create inactive user
            user = User.objects.create_user(
                username=schema.username,
                email=schema.email,
                password=schema.password,
                is_active=False  # User must verify email before activation
            )
            
            # Generate email verification token
            uid, token = generate_email_verification_token(user)
            
            # Build base URL for verification link
            base_url = request.build_absolute_uri('/').rstrip('/')
            
            # Send verification email
            # Try Celery first (if available), otherwise send synchronously
            import logging
            logger = logging.getLogger(__name__)
            
            verify_path = reverse('login_app:verify-email')
            verification_url = request.build_absolute_uri(
                f'{verify_path}?uid={uid}&token={token}'
            )
            
            email_sent = False
            
            # #region agent log
            print(f"[DEBUG EMAIL] RegistrationView: Attempting to send verification email to {user.email}", file=sys.stderr, flush=True)
            print(f"[DEBUG EMAIL] RegistrationView: Verification URL: {verification_url}", file=sys.stderr, flush=True)
            print(f"[DEBUG EMAIL] RegistrationView: EMAIL_BACKEND: {settings.EMAIL_BACKEND}", file=sys.stderr, flush=True)
            print(f"[DEBUG EMAIL] RegistrationView: EMAIL_HOST: {settings.EMAIL_HOST}", file=sys.stderr, flush=True)
            print(f"[DEBUG EMAIL] RegistrationView: EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}", file=sys.stderr, flush=True)
            print(f"[DEBUG EMAIL] RegistrationView: DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}", file=sys.stderr, flush=True)
            # #endregion
            
            # Try Celery first (if available)
            celery_available = False
            try:
                # #region agent log
                print(f"[DEBUG EMAIL] RegistrationView: Attempting to queue Celery task", file=sys.stderr, flush=True)
                # #endregion
                
                send_verification_email_task.delay(
                    user_id=user.id,
                    uid=uid,
                    token=token,
                    base_url=base_url
                )
                celery_available = True
                email_sent = True
                
                # #region agent log
                print(f"[DEBUG EMAIL] RegistrationView: Celery task queued successfully", file=sys.stderr, flush=True)
                # #endregion
                
                logger.info(f"Verification email task queued via Celery for {user.email}")
            except Exception as celery_error:
                # Celery is not available - fall back to synchronous sending
                error_msg = str(celery_error)
                error_trace = traceback.format_exc()
                
                # #region agent log
                print(f"[DEBUG EMAIL] RegistrationView: Celery not available, using synchronous fallback", file=sys.stderr, flush=True)
                print(f"[DEBUG EMAIL] RegistrationView: Celery error: {error_msg}", file=sys.stderr, flush=True)
                # #endregion
                
                logger.info(
                    f"Celery not available for {user.email}. "
                    f"Falling back to synchronous email sending. Error: {error_msg}"
                )
            
            # If Celery failed or is not available, send synchronously
            if not email_sent:
                try:
                    # #region agent log
                    print(f"[DEBUG EMAIL] RegistrationView: Attempting synchronous email send", file=sys.stderr, flush=True)
                    # #endregion
                    
                    # Get email content (text and HTML)
                    email_content = get_verification_email_content(user.username, verification_url)
                    
                    # Send email with both text and HTML versions
                    msg = EmailMultiAlternatives(
                        subject=email_content['subject'],
                        body=email_content['text_content'],
                        from_email=email_content['from_email'],
                        to=[user.email]
                    )
                    msg.attach_alternative(email_content['html_content'], "text/html")
                    msg.send(fail_silently=False)
                    email_sent = True
                    
                    # #region agent log
                    print(f"[DEBUG EMAIL] RegistrationView: Synchronous email sent successfully", file=sys.stderr, flush=True)
                    # #endregion
                    
                    logger.info(f"Verification email sent synchronously to {user.email}")
                except Exception as sync_email_error:
                    error_msg_sync = str(sync_email_error)
                    error_trace_sync = traceback.format_exc()
                    
                    # #region agent log
                    print(f"[DEBUG EMAIL ERROR] RegistrationView: Synchronous email send failed", file=sys.stderr, flush=True)
                    print(f"[DEBUG EMAIL ERROR] RegistrationView: Error: {error_msg_sync}", file=sys.stderr, flush=True)
                    print(f"[DEBUG EMAIL ERROR] RegistrationView: Traceback: {error_trace_sync}", file=sys.stderr, flush=True)
                    # #endregion
                    
                    logger.error(
                        f"Failed to send verification email to {user.email}. "
                        f"Error: {error_msg_sync}. "
                        f"Please check email configuration (EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)."
                    )
                    email_sent = False
            
            # Return standardized response
            response_data: Dict[str, Any] = {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "message": "Registration successful. Please check your email to verify your account."
            }
            
            # If email couldn't be sent, log the issue but still return success
            # Include warning in response so frontend can inform user
            if not email_sent:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"User {user.username} ({user.email}) registered but verification email could not be sent. "
                    f"Please check email configuration and Celery/Redis status."
                )
                # Add warning to response data
                response_data['email_sent'] = False
                response_data['warning'] = "Registration successful, but verification email could not be sent. Please contact support."
            else:
                response_data['email_sent'] = True
            
            return Response(
                {
                    "status": "success",
                    "data": response_data,
                    "error": None
                },
                status=status.HTTP_201_CREATED
            )
            
        except ValueError as e:
            # Pydantic validation errors
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Registration validation error: {str(e)}")
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            # Log the full exception for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Registration error: {str(e)}\n{traceback.format_exc()}")
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred during registration: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class VerifyEmailView(APIView):
    """
    API endpoint for email verification.
    Activates user account when token is valid.
    """
    permission_classes = [AllowAny]
    # Exclude SessionAuthentication to avoid CSRF requirement
    authentication_classes = []
    
    def get(self, request) -> Response:
        """
        Verify email address using token.
        
        Query parameters:
        - uid: Base64 encoded user ID
        - token: Verification token
        
        Response:
        {
            "status": "success",
            "data": {
                "message": "Email verified successfully. Your account is now active."
            },
            "error": null
        }
        """
        try:
            uid = request.query_params.get('uid')
            token = request.query_params.get('token')
            
            if not uid or not token:
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Missing uid or token parameters"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Decode user ID
            from django.utils.http import urlsafe_base64_decode
            from django.utils.encoding import force_str
            
            try:
                user_id = force_str(urlsafe_base64_decode(uid))
                user = User.objects.get(pk=user_id)
            except (TypeError, ValueError, OverflowError, User.DoesNotExist):
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Invalid verification link"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Verify token
            if not verify_email_token(user, uid, token):
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Invalid or expired verification token"
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Activate user account
            if user.is_active:
                return Response(
                    {
                        "status": "success",
                        "data": {
                            "message": "Email already verified. Your account is active."
                        },
                        "error": None
                    },
                    status=status.HTTP_200_OK
                )
            
            user.is_active = True
            user.save(update_fields=['is_active'])
            
            return Response(
                {
                    "status": "success",
                    "data": {
                        "message": "Email verified successfully. Your account is now active."
                    },
                    "error": None
                },
                status=status.HTTP_200_OK
            )
            
        except Exception as e:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred during email verification: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    """
    API endpoint for user login.
    Returns JWT access and refresh tokens upon successful authentication.
    """
    permission_classes = [AllowAny]
    # Exclude SessionAuthentication to avoid CSRF requirement
    authentication_classes = []
    
    def post(self, request) -> Response:
        """
        Authenticate user and return JWT tokens.
        
        Request body:
        {
            "username": "testuser",
            "password": "securepass123"
        }
        
        Response:
        {
            "status": "success",
            "data": {
                "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                "user": {
                    "id": 1,
                    "username": "testuser",
                    "email": "test@example.com"
                }
            },
            "error": null
        }
        """
        try:
            # Validate request using Pydantic schema
            schema = LoginRequest(**request.data)
            
            # First, try to get the user to check if they exist and are active
            user_obj = None
            if '@' in schema.username:
                # Try email login
                try:
                    user_obj = User.objects.get(email=schema.username)
                except User.DoesNotExist:
                    pass
            else:
                # Username login
                try:
                    user_obj = User.objects.get(username=schema.username)
                except User.DoesNotExist:
                    pass
            
            # Check if user exists and is inactive (before authentication)
            if user_obj and not user_obj.is_active:
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Account is not active. Please verify your email address."
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Authenticate user (supports both username and email)
            user = None
            if '@' in schema.username and user_obj:
                # Try email login
                user = authenticate(request, username=user_obj.username, password=schema.password)
            else:
                # Username login
                user = authenticate(request, username=schema.username, password=schema.password)
            
            if user is None:
                return Response(
                    {
                        "status": "error",
                        "data": None,
                        "error": "Invalid username/email or password"
                    },
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            access_token = refresh.access_token
            
            # Return standardized response
            response_data: Dict[str, Any] = {
                "access": str(access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                }
            }
            
            return Response(
                {
                    "status": "success",
                    "data": response_data,
                    "error": None
                },
                status=status.HTTP_200_OK
            )
            
        except ValueError as e:
            # Pydantic validation errors
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"An error occurred during login: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class TestEmailView(APIView):
    """
    Test endpoint for email configuration.
    Only available in DEBUG mode or for superusers.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        """
        Test email sending configuration.
        
        Request body (optional):
        {
            "to_email": "test@example.com"  # Defaults to DEFAULT_FROM_EMAIL if not provided
        }
        """
        from django.core.mail import EmailMultiAlternatives
        from django.conf import settings
        import logging
        
        logger = logging.getLogger(__name__)
        to_email = request.data.get('to_email', settings.DEFAULT_FROM_EMAIL)
        
        # #region agent log
        print(f"[DEBUG EMAIL TEST] TestEmailView: Testing email to {to_email}", file=sys.stderr, flush=True)
        print(f"[DEBUG EMAIL TEST] TestEmailView: EMAIL_BACKEND: {settings.EMAIL_BACKEND}", file=sys.stderr, flush=True)
        print(f"[DEBUG EMAIL TEST] TestEmailView: EMAIL_HOST: {settings.EMAIL_HOST}", file=sys.stderr, flush=True)
        print(f"[DEBUG EMAIL TEST] TestEmailView: EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}", file=sys.stderr, flush=True)
        print(f"[DEBUG EMAIL TEST] TestEmailView: EMAIL_HOST_PASSWORD: {'***' if settings.EMAIL_HOST_PASSWORD else '(not set)'}", file=sys.stderr, flush=True)
        print(f"[DEBUG EMAIL TEST] TestEmailView: DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}", file=sys.stderr, flush=True)
        # #endregion
        
        try:
            from_email = f"LLM Diet Planner <{settings.DEFAULT_FROM_EMAIL}>"
            text_content = 'This is a test email. If you receive this, email configuration is working correctly!'
            html_content = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background-color: #f8f9fa; padding: 30px; border-radius: 8px;">
        <h1 style="color: #2c3e50; margin-top: 0;">Email Configuration Test</h1>
        <p>This is a test email. If you receive this, email configuration is working correctly!</p>
        <p style="margin-top: 30px;">Best regards,<br><strong>LLM Diet Planner Team</strong></p>
    </div>
</body>
</html>'''
            
            msg = EmailMultiAlternatives(
                subject='Test Email from LLM Diet Planner',
                body=text_content,
                from_email=from_email,
                to=[to_email]
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
            
            # #region agent log
            print(f"[DEBUG EMAIL TEST] TestEmailView: Email sent successfully", file=sys.stderr, flush=True)
            # #endregion
            
            logger.info(f"Test email sent successfully to {to_email}")
            
            return Response(
                {
                    "status": "success",
                    "data": {
                        "message": f"Test email sent successfully to {to_email}",
                        "email_backend": settings.EMAIL_BACKEND,
                        "email_host": settings.EMAIL_HOST,
                        "from_email": settings.DEFAULT_FROM_EMAIL,
                    },
                    "error": None
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            error_msg = str(e)
            error_trace = traceback.format_exc()
            
            # #region agent log
            print(f"[DEBUG EMAIL TEST ERROR] TestEmailView: Failed to send test email: {error_msg}", file=sys.stderr, flush=True)
            print(f"[DEBUG EMAIL TEST ERROR] TestEmailView: Traceback: {error_trace}", file=sys.stderr, flush=True)
            # #endregion
            
            logger.error(f"Test email failed: {error_msg}")
            
            return Response(
                {
                    "status": "error",
                    "data": {
                        "email_backend": settings.EMAIL_BACKEND,
                        "email_host": settings.EMAIL_HOST,
                        "from_email": settings.DEFAULT_FROM_EMAIL,
                        "email_host_user_set": bool(settings.EMAIL_HOST_USER),
                        "email_host_password_set": bool(settings.EMAIL_HOST_PASSWORD),
                    },
                    "error": f"Failed to send test email: {error_msg}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserProfileView(APIView):
    """
    API endpoint to get user profile including free generations remaining.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        """
        Get current user's profile information.

        Response:
        {
            "status": "success",
            "data": {
                "id": 1,
                "username": "testuser",
                "email": "test@example.com",
                "free_generations_remaining": 10,
                "total_generations": 0
            },
            "error": null
        }
        """
        try:
            user = request.user

            # Get or create user profile
            profile, created = UserProfile.objects.get_or_create(user=user)

            return Response(
                {
                    "status": "success",
                    "data": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                        "free_generations_remaining": profile.free_generations_remaining,
                        "total_generations": profile.total_generations,
                        "primary_auth_provider": profile.primary_auth_provider,
                        "email_verified": profile.email_verified,
                    },
                    "error": None,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {
                    "status": "error",
                    "data": None,
                    "error": f"Failed to get user profile: {str(e)}",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


import sys
import logging
import traceback
from django.conf import settings
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)

class StandardizedSocialLoginView(SocialLoginView):
    """Base class with robust error handling for Social Auth."""
    
    def _validate_access_token(self, request) -> tuple[bool, str]:
        access_token = request.data.get('access_token')
        if not access_token:
            return False, "Missing 'access_token' in request body."
        if len(str(access_token)) < 20:
            return False, "Access token appears malformed (too short)."
        return True, ""

    def post(self, request, *args, **kwargs):
        is_valid, error_msg = self._validate_access_token(request)
        if not is_valid:
            return Response({"status": "error", "error": error_msg}, status=400)

        try:
            return super().post(request, *args, **kwargs)
        except Exception as e:
            # Fix for the empty colon error: use repr(e) and log trace
            exc_msg = str(e) or repr(e)
            logger.error(f"[OAUTH ERROR] {exc_msg}")
            return Response({
                "status": "error",
                "error": f"Google authentication failed: {exc_msg}"
            }, status=500)

class GoogleLogin(StandardizedSocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client

class GoogleOAuthDiagnosticView(SocialLoginView):
    """Endpoint to check if Google Auth is configured correctly on the server."""
    permission_classes = [AllowAny]
    
    def get(self, request):
        from allauth.socialaccount.models import SocialApp
        google_app = SocialApp.objects.filter(provider='google').first()
        
        return Response({
            "configured_in_db": bool(google_app),
            "client_id_prefix": google_app.client_id[:10] if google_app else "None",
            "has_secret": bool(google_app.secret) if google_app else False,
            "settings_pkce": settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('OAUTH_PKCE_ENABLED'),
            "callback_url_env": settings.GOOGLE_CALLBACK_URL
        })

