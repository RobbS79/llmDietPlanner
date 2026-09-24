"""HTTP surface of the social pipeline: the card image Slack embeds, and the
button clicks Slack sends back. Both are unauthenticated by design — the card
path is signed, the interaction body is signed."""
from __future__ import annotations

import hmac
import logging

from django.http import Http404, HttpResponse
from django.views.decorators.http import require_GET

from .cards import card_signature
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
