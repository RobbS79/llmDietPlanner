# File: login_app/views.py
"""
Professional implementation of Authentication and Social OAuth2 views.
Includes standard Registration, Login, and secure Google OAuth handshake.
Follows strict API standardization: { "status": "success", "data": {}, "error": null }
"""
import requests
import uuid
import logging
from django.shortcuts import redirect
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import JsonResponse
from django.core.serializers.json import DjangoJSONEncoder

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from pydantic import ValidationError
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str

from .models import UserProfile
from .schemas import RegistrationRequest, LoginRequest, PasswordResetRequestSchema, PasswordResetConfirmSchema
from .utils import generate_email_verification_token, verify_email_token
from .tasks import send_verification_email_task, send_password_reset_email_task
from analytics.models import MarketingAttribution
from analytics.events import track_signup
from billing.services import cancel_subscription_for_user

logger = logging.getLogger(__name__)

class GoogleLoginRedirectView(APIView):
    """
    AUTHORITATIVE REDIRECT: Entry point for Google OAuth.
    Routes the browser to the Google Consent screen with forced HTTPS in production.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
        
        # Determine redirect URI and force HTTPS in production to match Google Console whitelist
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        if not settings.DEBUG:
            redirect_uri = redirect_uri.replace('http://', 'https://')
            
        logger.debug("OAuth redirect: client_id_present=%s redirect_uri=%s", bool(client_id), redirect_uri)

        if not client_id:
            logger.critical("OAuth Configuration Error: GOOGLE_CLIENT_ID is missing from environment.")
            return redirect('/login?error=google_not_configured')

        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&"
            f"scope=openid%20email%20profile&access_type=offline&prompt=select_account"
        )
        return redirect(auth_url)

class GoogleCallbackView(APIView):
    """
    RECEIVER: Handles the auth code sent back from Google.
    Exchanges the code for tokens and manages user creation/linking.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.GET.get('code')
        
        # Reconstruct the EXACT same redirect_uri used in the trigger (must match exactly)
        redirect_uri = request.build_absolute_uri('/api/auth/google/callback/')
        if not settings.DEBUG:
            redirect_uri = redirect_uri.replace('http://', 'https://')
            
        logger.debug("OAuth callback: code_present=%s", bool(code))

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
                logger.error("OAuth token exchange failed: status=%s", token_res.status_code)
                return redirect('/login?error=token_exchange_failed')
            
            token_data = token_res.json()
            access_token = token_data.get('access_token')

            # 2. Get User Profile from Google Identity API
            user_info = requests.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=10
            ).json()
            
            email = user_info.get('email')
            if not email:
                logger.warning("OAuth callback: Google did not provide email")
                return redirect('/login?error=email_access_denied')

            # 3. User Management (Atomic Transaction)
            with transaction.atomic():
                user = User.objects.filter(email=email).first()
                if not user:
                    logger.info("OAuth: creating new user for email")
                    username = email.split('@')[0]
                    # Ensure username uniqueness
                    base_username = username
                    while User.objects.filter(username=username).exists():
                        username = f"{base_username}_{uuid.uuid4().hex[:4]}"
                    user = User.objects.create_user(username=username, email=email, is_active=True)
                
                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.primary_auth_provider = 'google'
                profile.email_verified = True
                profile.save()

            # 4. Issue JWT tokens and redirect back to the React success handler
            refresh = RefreshToken.for_user(user)
            logger.info("OAuth: authentication successful for user_id=%s", user.id)
            frontend_url = getattr(settings, 'FRONTEND_URL', '')
            return redirect(f"{frontend_url}/login-success?access={str(refresh.access_token)}&refresh={str(refresh)}")

        except Exception as e:
            logger.exception("OAuth callback error")
            return redirect('/login?error=auth_failed')

@method_decorator(csrf_exempt, name='dispatch')
class RegistrationView(APIView):
    """
    SECURE REGISTRATION: Handles new user creation and triggers email verification.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        # Validate input FIRST so field errors (weak password, mismatch, bad
        # email) surface as a 400 with the real message instead of being caught
        # by the generic handler below and returned as an opaque 500.
        try:
            schema = RegistrationRequest(**request.data)
        except ValidationError as e:
            errs = e.errors()
            # Pydantic prefixes custom ValueError messages with "Value error, ";
            # strip it so the client sees the clean message.
            msg = (errs[0].get('msg') if errs else '') or 'Invalid registration data'
            msg = msg.replace('Value error, ', '')
            return Response({"status": "error", "data": None, "error": msg}, status=400)

        try:
            if User.objects.filter(username=schema.username).exists():
                return Response({"status": "error", "data": None, "error": "Username already exists"}, status=400)

            if User.objects.filter(email=schema.email).exists():
                return Response({"status": "error", "data": None, "error": "Email already registered"}, status=400)

            # Active immediately so the user can log in and explore. Email
            # verification (UserProfile.email_verified) is NOT a login gate — it
            # gates plan generation (see DietaryGoalCreateView).
            user = User.objects.create_user(
                username=schema.username,
                email=schema.email,
                password=schema.password,
                is_active=True,
            )

            # Persist marketing attribution (optional, untrusted client input) so
            # webhook-time CAPI events can honor consent later. This must never
            # break registration, so failures here are logged and swallowed.
            try:
                attr_in = schema.attribution
                MarketingAttribution.objects.create(
                    user=user,
                    utm_source=(attr_in.utm_source if attr_in else ""),
                    utm_medium=(attr_in.utm_medium if attr_in else ""),
                    utm_campaign=(attr_in.utm_campaign if attr_in else ""),
                    utm_content=(attr_in.utm_content if attr_in else ""),
                    utm_term=(attr_in.utm_term if attr_in else ""),
                    fbclid=(attr_in.fbclid if attr_in else ""),
                    fbp=(attr_in.fbp if attr_in else ""),
                    fbc=(attr_in.fbc if attr_in else ""),
                    landing_at=timezone.now(),
                    marketing_consent=(attr_in.consent if attr_in else False),
                    consent_at=(timezone.now() if (attr_in and attr_in.consent) else None),
                    consent_version=(attr_in.consent_version if attr_in else ""),
                )
                track_signup(user)
            except Exception:
                logger.exception("Failed to persist marketing attribution / fire signup event for user_id=%s", user.id)

            # Send the verification email (offloaded to Celery). A broker hiccup
            # must NEVER 500 an otherwise-successful registration, so failures to
            # enqueue are logged and swallowed — the account still exists and the
            # user can request a resend.
            try:
                uid, token = generate_email_verification_token(user)
                # rstrip('/') — build_absolute_uri('/') has a trailing slash and
                # the task appends "/api/auth/verify-email/...", which would make
                # a "//api/..." link that resolves to the SPA catch-all instead
                # of this API view.
                base_url = request.build_absolute_uri('/').rstrip('/')
                send_verification_email_task.delay(user.id, uid, token, base_url)
            except Exception:
                logger.exception("Failed to enqueue verification email for user_id=%s", user.id)

            return Response({
                "status": "success", 
                "data": {"username": user.username, "email": user.email},
                "error": None
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Registration Exception: {str(e)}")
            return Response({"status": "error", "data": None, "error": "Internal registration error"}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class VerifyEmailView(APIView):
    """Confirm a user's email from the emailed link, then redirect to the
    frontend login page (?verified=1 on success, 0 otherwise).

    Sets UserProfile.email_verified, which gates plan generation — NOT login —
    so it deliberately does NOT touch is_active (never un-bans an
    admin-disabled account). The token is checked BEFORE anything else, and
    EVERY failure mode (missing params, unknown uid, bad token, already
    verified) yields the identical redirect, so the endpoint cannot be used to
    enumerate which accounts exist or are verified. Restored after the endpoint
    was dropped in earlier churn while registration still emailed a link to it.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def _redirect(self, ok: bool):
        # Relative redirect: the SPA is served from the same host, so this lands
        # the user on the real /login page rather than a raw JSON body.
        return redirect(f"/login?verified={'1' if ok else '0'}")

    def get(self, request):
        uid = request.query_params.get('uid')
        token = request.query_params.get('token')
        if not uid or not token:
            return self._redirect(False)

        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return self._redirect(False)

        # Token first — a caller without a valid token always gets the failure
        # redirect, whether or not the account exists / is already verified.
        if not verify_email_token(user, uid, token):
            return self._redirect(False)

        profile, _ = UserProfile.objects.get_or_create(user=user)
        if not profile.email_verified:
            profile.email_verified = True
            profile.save(update_fields=['email_verified'])
        return self._redirect(True)


@method_decorator(csrf_exempt, name='dispatch')
class ResendVerificationView(APIView):
    """Resend the verification email (recovery path: e.g. the enqueue failed at
    signup during a broker outage, or the first mail was lost). Always returns
    the same generic success so it cannot be used to enumerate accounts.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'resend_verification'

    def post(self, request) -> Response:
        email = (request.data.get('email') or '').strip()
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if user:
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if not profile.email_verified:
                    try:
                        uid, token = generate_email_verification_token(user)
                        base_url = request.build_absolute_uri('/').rstrip('/')
                        send_verification_email_task.delay(user.id, uid, token, base_url)
                    except Exception:
                        logger.exception("Failed to enqueue resend verification for user_id=%s", user.id)
        return Response({
            "status": "success",
            "data": {"message": "Pokud účet existuje a není ověřený, poslali jsme ověřovací e-mail."},
            "error": None,
        }, status=200)


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    """
    JWT ISSUER: Authenticates standard users and returns Bearer tokens.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    
    def post(self, request) -> Response:
        try:
            schema = LoginRequest(**request.data)
            # `request` is REQUIRED: AxesStandaloneBackend (now in
            # AUTHENTICATION_BACKENDS for admin brute-force lockout) raises if it
            # is missing, and Axes needs it to record the source IP per attempt.
            user = authenticate(request, username=schema.username, password=schema.password)
            
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
            logger.exception("Login error")
            return Response({"status": "error", "data": None, "error": "Internal server error"}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetRequestView(APIView):
    """Send a password reset link to the user's email."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        try:
            schema = PasswordResetRequestSchema(**request.data)
            user = User.objects.filter(email=schema.email).first()

            if user:
                uid, token = generate_email_verification_token(user)
                frontend_url = getattr(settings, 'FRONTEND_URL', request.build_absolute_uri('/').rstrip('/'))
                send_password_reset_email_task.delay(user.id, uid, token, frontend_url)

            return Response({
                "status": "success",
                "data": {"message": "If an account with that email exists, a reset link has been sent."},
                "error": None
            })
        except Exception as e:
            logger.exception("Password reset request error")
            return Response({"status": "error", "data": None, "error": "Failed to process request"}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class PasswordResetConfirmView(APIView):
    """Validate the reset token and set the new password."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request) -> Response:
        try:
            schema = PasswordResetConfirmSchema(**request.data)

            from django.utils.http import urlsafe_base64_decode
            from django.utils.encoding import force_str
            user_id = force_str(urlsafe_base64_decode(schema.uid))
            user = User.objects.get(pk=user_id)

            if not verify_email_token(user, schema.uid, schema.token):
                return Response({"status": "error", "data": None, "error": "Invalid or expired reset link"}, status=400)

            user.set_password(schema.password)
            user.save()

            return Response({
                "status": "success",
                "data": {"message": "Password has been reset successfully."},
                "error": None
            })
        except User.DoesNotExist:
            return Response({"status": "error", "data": None, "error": "Invalid reset link"}, status=400)
        except ValueError as e:
            return Response({"status": "error", "data": None, "error": str(e)}, status=400)
        except Exception as e:
            logger.exception("Password reset confirm error")
            return Response({"status": "error", "data": None, "error": "Failed to reset password"}, status=500)


class UserProfileView(APIView):
    """Returns user profile with generation credits and onboarding state."""
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        attr = getattr(request.user, 'marketing_attribution', None)
        return Response({
            "status": "success",
            "data": {
                "email": request.user.email,
                "username": request.user.username,
                "free_generations_remaining": profile.free_generations_remaining,
                "total_generations": profile.total_generations,
                "onboarding_completed": profile.onboarding_completed,
                "dietary_preferences": profile.dietary_preferences,
                "primary_auth_provider": profile.primary_auth_provider,
                "email_verified": profile.email_verified,
                "marketing_consent": attr.marketing_consent if attr else False,
                "consent_version": attr.consent_version if attr else "",
            },
            "error": None
        })

    def patch(self, request) -> Response:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        update_fields = ['updated_at']

        if 'onboarding_completed' in request.data:
            profile.onboarding_completed = request.data['onboarding_completed']
            update_fields.append('onboarding_completed')

        if 'dietary_preferences' in request.data:
            prefs = request.data['dietary_preferences']
            if not isinstance(prefs, dict):
                return Response(
                    {"status": "error", "data": None,
                     "error": "dietary_preferences must be a JSON object"},
                    status=400,
                )
            merged = dict(profile.dietary_preferences or {})
            # Shallow top-level merge only — a nested-object pref would be
            # replaced wholesale, not deep-merged, by this .update().
            merged.update(prefs)
            profile.dietary_preferences = merged
            update_fields.append('dietary_preferences')

        profile.save(update_fields=update_fields)
        return Response({
            "status": "success",
            "data": {
                "onboarding_completed": profile.onboarding_completed,
                "dietary_preferences": profile.dietary_preferences,
            },
            "error": None
        })


class AccountDeleteView(APIView):
    """Hard-delete the authenticated user's account (GDPR erasure).

    Re-auth: email users send `password`; Google users send a fresh
    `google_access_token` (verified against Google userinfo, email must match).
    Cancels any Stripe subscription (idempotent) but does NOT delete the Stripe
    customer (invoice retention). Writes an anonymized AccountDeletion audit row.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'account_delete'

    def delete(self, request):
        from billing.models import Subscription
        user = request.user
        profile, _ = UserProfile.objects.get_or_create(user=user)

        # 1. Re-authenticate.
        if profile.primary_auth_provider == 'google':
            token = str(request.data.get('google_access_token', '') or '')
            if not token:
                return Response({"status": "error", "data": None,
                                 "error": "Google re-authentication required."}, status=400)
            try:
                info = requests.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={'Authorization': f'Bearer {token}'}, timeout=10)
            except requests.RequestException:
                return Response({"status": "error", "data": None,
                                 "error": "Could not verify Google identity."}, status=502)
            email = (info.json().get('email') if info.status_code == 200 else None) or ''
            if info.status_code != 200 or email.lower() != (user.email or '').lower():
                return Response({"status": "error", "data": None,
                                 "error": "Re-authentication failed."}, status=403)
        else:
            password = str(request.data.get('password', '') or '')
            if not user.check_password(password):
                return Response({"status": "error", "data": None,
                                 "error": "Nesprávné heslo."}, status=403)

        # 2. Snapshot billing identifiers BEFORE any mutation.
        sub = Subscription.objects.filter(user=user).first()
        customer_id = sub.stripe_customer_id if sub else ''
        if not customer_id:
            mapping = getattr(user, 'stripe_customer', None)
            customer_id = mapping.stripe_customer_id if mapping else ''
        tier = sub.tier if sub else ''

        # 3. Cancel Stripe subscription — abort delete on a real Stripe error.
        try:
            cancel_subscription_for_user(user)
        except Exception:
            logger.exception("Account delete: Stripe cancel failed; aborting delete")
            return Response({"status": "error", "data": None,
                             "error": "Could not cancel your subscription. Account not deleted."},
                            status=502)

        # 4. Anonymized audit row + hard delete, atomically.
        from .models import AccountDeletion
        with transaction.atomic():
            AccountDeletion.objects.create(
                stripe_customer_id=customer_id or '', tier=tier or '',
                auth_provider=profile.primary_auth_provider,
            )
            user.delete()
        return Response({"status": "success", "data": {"deleted": True}, "error": None})


class DataExportView(APIView):
    """Return the authenticated user's data as a downloadable JSON file (GDPR portability)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from billing.models import Subscription
        from diet_planner.models import DietaryGoal
        user = request.user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        sub = Subscription.objects.filter(user=user).first()
        attr = getattr(user, 'marketing_attribution', None)
        goals = list(DietaryGoal.objects.filter(user=user)
                     .values('id', 'prompt', 'num_days', 'status', 'created_at'))

        payload = {
            "account": {
                "username": user.username,
                "email": user.email,
                "date_joined": user.date_joined,
                "auth_provider": profile.primary_auth_provider,
                "email_verified": profile.email_verified,
            },
            "preferences": profile.dietary_preferences,
            "usage": {
                "free_generations_remaining": profile.free_generations_remaining,
                "total_generations": profile.total_generations,
            },
            "subscription": None if not sub else {
                "tier": sub.tier, "status": sub.status,
                "current_period_end": sub.current_period_end,
                "cancel_at_period_end": sub.cancel_at_period_end,
            },
            "marketing_consent": None if not attr else {
                "consent": attr.marketing_consent,
                "version": attr.consent_version,
                "at": attr.consent_at,
            },
            "meal_plans": goals,
        }
        resp = JsonResponse(payload, encoder=DjangoJSONEncoder,
                            json_dumps_params={"indent": 2, "ensure_ascii": False})
        resp["Content-Disposition"] = 'attachment; filename="varto-my-data.json"'
        return resp