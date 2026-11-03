"""Abuse limits for /api/discover/: daily LLM budget, result cache, Turnstile.

Everything lives in the shared Django cache (Redis on prod via CACHE_URL), so
limits hold across Gunicorn workers. Without TURNSTILE_SECRET_KEY the bot
check is off and only the throttles apply.
"""
import hashlib
import logging
import unicodedata
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)
_DAY = 60 * 60 * 24
SITEVERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
_MAX_TOKEN_LEN = 2048
# Day boundaries follow the audience, not settings.TIME_ZONE (left at Chicago).
_PRAGUE = ZoneInfo('Europe/Prague')


def _today() -> str:
    return timezone.now().astimezone(_PRAGUE).date().isoformat()


def _alert(count: int, budget: int) -> None:
    from diet_planner.services.llm_health import default_post, notify_slack
    notify_slack(
        f':warning: Uvařto discover: {count}/{budget} LLM calls used today ({_today()}). '
        'Past the budget, search switches to text matching.',
        webhook_url=getattr(settings, 'LLM_HEALTH_SLACK_WEBHOOK_URL', ''),
        bot_token=getattr(settings, 'SLACK_BOT_TOKEN', ''),
        channel=getattr(settings, 'LLM_HEALTH_SLACK_CHANNEL', ''),
        post=default_post)


def take_llm_slot() -> bool:
    """Count one discover LLM call against today's budget. False when spent."""
    budget = int(getattr(settings, 'DISCOVER_DAILY_LLM_BUDGET', 500))
    key = f'discover:llm:{_today()}'
    cache.add(key, 0, _DAY)
    count = cache.incr(key)
    if count >= int(budget * 0.8) and cache.add(f'discover:llm-alert:{_today()}', 1, _DAY):
        try:
            _alert(count, budget)
        except Exception:  # noqa: BLE001 - an alert must never break search
            logger.exception('discover budget alert failed')
    return count <= budget


def _fold(q: str) -> str:
    q = unicodedata.normalize('NFD', (q or '').lower())
    return ' '.join(''.join(c for c in q if not unicodedata.combining(c)).split())


def result_key(q: str) -> str:
    """One key per normalised query; pages are sliced from the cached ranking."""
    digest = hashlib.sha256(_fold(q).encode()).hexdigest()[:32]
    return f'discover:result:v2:{digest}'


def _siteverify(token: str, ip: str) -> bool:
    """Cloudflare's answer. Fails open (True) ONLY when Cloudflare is
    unreachable or erroring (timeout, connection error, 5xx) so an outage
    leaves the throttles in charge; a 4xx or junk body is a refusal."""
    try:
        resp = requests.post(SITEVERIFY_URL, timeout=5, data={
            'secret': settings.TURNSTILE_SECRET_KEY, 'response': token, 'remoteip': ip})
    except (requests.Timeout, requests.ConnectionError):
        logger.warning('turnstile siteverify unreachable: failing open')
        return True
    if resp.status_code >= 500:
        logger.warning('turnstile siteverify returned %s: failing open', resp.status_code)
        return True
    if resp.status_code >= 400:
        logger.warning('turnstile siteverify returned %s', resp.status_code)
        return False
    try:
        body = resp.json()
    except ValueError:
        logger.warning('turnstile siteverify body is not JSON')
        return False
    return isinstance(body, dict) and body.get('success') is True


def challenge_needed(ident: str) -> bool:
    """Count one search; True once past the free searches and not verified."""
    if not getattr(settings, 'TURNSTILE_SECRET_KEY', ''):
        return False
    if cache.get(f'discover:verified:{ident}'):
        return False
    key = f'discover:searches:{ident}'
    cache.add(key, 0, 60 * 60)
    count = cache.incr(key)
    return count > int(getattr(settings, 'DISCOVER_FREE_SEARCHES_BEFORE_CHALLENGE', 3))


def verify_challenge(token, ident: str) -> bool:
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LEN:
        return False
    if cache.get(f'discover:verified:{ident}'):
        return True
    try:
        ok = _siteverify(token, ident)
    except Exception:  # noqa: BLE001 - outages fail open inside _siteverify; anything else refuses
        logger.exception('turnstile siteverify failed')
        ok = False
    if ok:
        cache.set(f'discover:verified:{ident}', 1, 60 * 60)
    return ok
