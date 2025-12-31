"""
API Views for user authentication and registration.
Uses DRF APIView for class-based views.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from typing import Dict, Any

from rest_framework_simplejwt.tokens import RefreshToken
from .schemas import RegistrationRequest, LoginRequest, EmailVerificationRequest
from .utils import generate_email_verification_token, verify_email_token
from .tasks import send_verification_email_task


@method_decorator(csrf_exempt, name='dispatch')
class RegistrationView(APIView):
    """
    API endpoint for user registration.
    Creates an inactive user and sends email verification.
    """
    permission_classes = [AllowAny]
    
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
            
            # Send verification email asynchronously via Celery
            # This ensures registration completes immediately and email is sent reliably
            try:
                send_verification_email_task.delay(
                    user_id=user.id,
                    uid=uid,
                    token=token,
                    base_url=base_url
                )
                email_sent = True
            except Exception as email_task_error:
                # If Celery is not available, log warning but don't fail registration
                # Email will need to be sent manually or Celery needs to be configured
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Failed to queue verification email task for {user.email}. "
                    f"Celery may not be running. Error: {str(email_task_error)}"
                )
                # Fallback: try to send synchronously (will fail if email backend not configured)
                try:
                    verify_path = reverse('login_app:verify-email')
                    verification_url = request.build_absolute_uri(
                        f'{verify_path}?uid={uid}&token={token}'
                    )
                    send_mail(
                        subject='Verify your email address',
                        message=f'''
Hello {user.username},

Thank you for registering with LLM Diet Planner!

Please click the following link to verify your email address and activate your account:

{verification_url}

This link will expire in 24 hours.

If you did not register for this account, please ignore this email.

Best regards,
LLM Diet Planner Team
                        ''',
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[user.email],
                        fail_silently=False,
                    )
                    email_sent = True
                except Exception as sync_email_error:
                    logger.error(f"Failed to send verification email synchronously: {str(sync_email_error)}")
                    email_sent = False
            
            # Return standardized response
            response_data: Dict[str, Any] = {
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "message": "Registration successful. Please check your email to verify your account."
            }
            
            # If email couldn't be sent, still return success but log the issue
            # Admin can manually verify or fix email configuration
            if not email_sent:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(
                    f"User {user.username} ({user.email}) registered but verification email could not be sent. "
                    f"Manual verification may be required."
                )
            
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
            import traceback
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

