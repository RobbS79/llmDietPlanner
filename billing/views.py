"""
Billing API views — /api/billing/.

  GET  plans/     public   tier catalog (frontend reads instead of hardcoding)
  POST checkout/  user      create Stripe Checkout Session (mode=subscription)
  POST portal/    user      create Customer Portal session
  POST webhook/   stripe    lifecycle events (signature-verified, idempotent)
  GET  me/        user      current entitlement + remaining quota
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

from .models import SubscriptionPlan, Subscription, ProcessedWebhookEvent, Tier
from .serializers import SubscriptionPlanSerializer, SubscriptionSerializer
from .stripe_client import stripe, is_configured
from . import services

logger = logging.getLogger(__name__)


def _frontend_url(path: str) -> str:
    base = (settings.FRONTEND_URL or '').rstrip('/')
    return f"{base}{path}"


class PlansView(APIView):
    """Public — serve active tiers from the DB."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        plans = SubscriptionPlan.objects.filter(is_active=True)
        return Response({'plans': SubscriptionPlanSerializer(plans, many=True).data})


class CheckoutView(APIView):
    """Create a subscription Checkout Session and return its hosted URL."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_configured():
            return Response(
                {'status': 'error', 'error': 'Billing is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        tier = (request.data.get('tier') or '').lower()
        if tier not in (Tier.STANDARD, Tier.PREMIUM):
            return Response(
                {'status': 'error', 'error': "tier must be 'standard' or 'premium'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        price_id = services.price_id_for_tier(tier)
        if not price_id:
            logger.error('No Stripe price configured for tier %s', tier)
            return Response(
                {'status': 'error', 'error': 'This plan is not available yet.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            customer_id = services.get_or_create_customer(request.user)
            session = stripe.checkout.Session.create(
                mode='subscription',
                customer=customer_id,
                line_items=[{'price': price_id, 'quantity': 1}],
                client_reference_id=str(request.user.id),
                metadata={'user_id': str(request.user.id), 'tier': tier},
                subscription_data={
                    'metadata': {'user_id': str(request.user.id), 'tier': tier},
                },
                success_url=_frontend_url('/?sub=success'),
                cancel_url=_frontend_url('/pricing?sub=cancelled'),
                allow_promotion_codes=True,
            )
        except stripe.error.StripeError as exc:
            logger.exception('Stripe checkout creation failed')
            # 400, not 502: App Platform replaces upstream 5xx bodies with its
            # own branded error page, so a 502 here hides our JSON from the SPA
            # (which then can't show its friendly message). This is a
            # request/config problem from our side anyway, not a gateway outage.
            return Response(
                {'status': 'error', 'error': 'Could not start checkout.',
                 'detail': str(getattr(exc, 'user_message', '') or '')},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({'url': session['url']})


class PortalView(APIView):
    """Create a Stripe Customer Portal session for self-service management."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_configured():
            return Response(
                {'status': 'error', 'error': 'Billing is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        sub = Subscription.objects.filter(user=request.user).first()
        customer_id = sub.stripe_customer_id if sub else None
        if not customer_id:
            mapping = getattr(request.user, 'stripe_customer', None)
            customer_id = mapping.stripe_customer_id if mapping else None
        if not customer_id:
            return Response(
                {'status': 'error', 'error': 'No billing account for this user.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=_frontend_url('/'),
            )
        except stripe.error.StripeError:
            logger.exception('Stripe portal creation failed')
            return Response(
                {'status': 'error', 'error': 'Could not open the billing portal.'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({'url': session['url']})


class MeView(APIView):
    """Current user's subscription status + remaining quota (UI gating)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sub = Subscription.objects.filter(user=request.user).first()
        free_remaining = 0
        profile = getattr(request.user, 'profile', None)
        if profile is not None:
            free_remaining = profile.free_generations_remaining
        data = {
            'subscription': SubscriptionSerializer(sub).data if sub else None,
            'free_generations_remaining': free_remaining,
        }
        return Response(data)


class WebhookView(APIView):
    """
    Stripe webhook receiver. Verifies the signature, then dispatches to an
    idempotent handler. Returns 200 quickly so Stripe doesn't retry on success.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
        secret = settings.STRIPE_WEBHOOK_SECRET
        if not secret:
            logger.error('STRIPE_WEBHOOK_SECRET not set; rejecting webhook')
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            event = stripe.Webhook.construct_event(payload, sig_header, secret)
        except ValueError:
            return Response({'error': 'invalid payload'}, status=status.HTTP_400_BAD_REQUEST)
        except stripe.error.SignatureVerificationError:
            logger.warning('Stripe webhook signature verification failed')
            return Response({'error': 'invalid signature'}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize StripeObject -> plain nested dict so handlers can use .get().
        event = services.as_dict(event)
        event_id = event['id']
        event_type = event['type']

        # Idempotency: claim the event id first; a duplicate delivery is a no-op.
        # Wrap in a savepoint so the IntegrityError can't poison an outer
        # transaction (ATOMIC_REQUESTS).
        try:
            with transaction.atomic():
                ProcessedWebhookEvent.objects.create(
                    stripe_event_id=event_id, event_type=event_type,
                )
        except IntegrityError:
            logger.info('Duplicate webhook %s ignored', event_id)
            return Response(status=status.HTTP_200_OK)

        handler = services.HANDLERS.get(event_type)
        if handler is None:
            return Response(status=status.HTTP_200_OK)  # event we don't act on
        try:
            handler(event)
        except Exception:
            # Drop the idempotency claim so Stripe's retry can re-attempt.
            ProcessedWebhookEvent.objects.filter(stripe_event_id=event_id).delete()
            logger.exception('Webhook handler failed for %s', event_type)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status=status.HTTP_200_OK)
