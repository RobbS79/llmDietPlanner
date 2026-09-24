"""Slack interactivity: the signature check and what a button click does to
a row. Kept apart from the view so the decision logic is testable without
HTTP and the view stays a thin, signed doorway."""
from __future__ import annotations

import hmac
import logging
import time
from hashlib import sha256
from typing import Optional

from .models import SocialPost
from .slack import APPROVE_ACTION, REJECT_ACTION, SlackDrafts

logger = logging.getLogger(__name__)

MAX_SKEW_SECONDS = 300


def verify_slack_signature(secret: str, timestamp: str, signature: str, body: bytes,
                           now: Optional[float] = None) -> bool:
    """Slack's v0 scheme: HMAC-SHA256(secret, 'v0:<ts>:<body>'), plus a replay window."""
    if not (secret and timestamp.isdigit() and signature):
        return False
    if abs((now or time.time()) - int(timestamp)) > MAX_SKEW_SECONDS:
        return False
    expected = 'v0=' + hmac.new(secret.encode(), f'v0:{timestamp}:'.encode() + body, sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def handle_action(action_id: str, value: str, user_id: str) -> str:
    """Returns 'approved' | 'rejected' | 'refreshed' | 'ignored'. The status
    change is saved before the card is redrawn, and a redraw failure is
    logged, never raised — the row is the truth."""
    if action_id not in (APPROVE_ACTION, REJECT_ACTION) or not str(value).isdigit():
        return 'ignored'
    post = SocialPost.objects.filter(pk=int(value)).first()
    if post is None:
        return 'ignored'
    outcome = 'refreshed'
    if post.status == SocialPost.Status.DRAFT:
        post.status = (SocialPost.Status.APPROVED if action_id == APPROVE_ACTION
                       else SocialPost.Status.REJECTED)
        post.approved_by, post.error = user_id[:32], ''
        post.save(update_fields=['status', 'approved_by', 'error'])
        outcome = str(post.status)
    try:
        SlackDrafts().update_card(post)
    except Exception as exc:   # noqa: BLE001 — cosmetic; the decision is already saved
        logger.warning('card redraw after %s on post %s failed: %s', action_id, post.pk, exc)
    return outcome
