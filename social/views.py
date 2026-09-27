"""HTTP surface of the social pipeline: the card image Slack embeds, and the
button clicks Slack sends back. Both are unauthenticated by design — the card
path is signed, the interaction body is signed."""
from __future__ import annotations

import hmac
import json
import logging
from urllib.parse import parse_qs

from django.conf import settings
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .cards import card_signature
from .interact import handle_action, verify_slack_signature
from .models import SocialPost

logger = logging.getLogger(__name__)


@require_GET
def card_png(request, pk: int, sig: str):
    if not hmac.compare_digest(sig, card_signature(pk)):
        raise Http404
    post = SocialPost.objects.filter(pk=pk).only('image').first()
    if post is None or not post.image:
        raise Http404
    response = HttpResponse(post.image_bytes, content_type='image/png')
    # A retried draft re-renders its card under the same URL; a day of caching
    # is plenty for Slack's own fetch and avoids serving stale art for good.
    response['Cache-Control'] = 'public, max-age=86400'
    return response


class SlackInteractView(APIView):
    """Slack posts `payload=<json>` (form-encoded) for every button click and
    expects a 200 within 3 s. Signature-verified; no session, no CSRF — the
    same shape as billing's Stripe webhook receiver."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        secret = settings.SLACK_SIGNING_SECRET
        if not secret:
            logger.error('SLACK_SIGNING_SECRET not set; rejecting Slack interaction')
            return Response(status=503)
        body = request.body
        if not verify_slack_signature(secret, request.META.get('HTTP_X_SLACK_REQUEST_TIMESTAMP', ''),
                                      request.META.get('HTTP_X_SLACK_SIGNATURE', ''), body):
            logger.warning('Slack interaction signature verification failed')
            return Response({'error': 'invalid signature'}, status=400)
        try:
            payload = json.loads(parse_qs(body.decode('utf-8')).get('payload', ['{}'])[0])
        except (ValueError, UnicodeDecodeError):
            payload = {}
        if not isinstance(payload, dict) or payload.get('type') != 'block_actions':
            return Response(status=200)
        user_id = (payload.get('user') or {}).get('id', '')
        for action in payload.get('actions') or []:
            handle_action(action.get('action_id', ''), action.get('value', ''), user_id)
        return Response(status=200)
