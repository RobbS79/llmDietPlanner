"""Is the LLM actually answering right now?

Four Gemini outages were each discovered by accident, days late, because
nothing asks this question on a schedule. See docs and the `check_llm_health`
management command.
"""
import logging
from dataclasses import dataclass

#: Deliberately trivial — this measures reachability, not quality.
PROMPT = 'Reply with the single word: ok'

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    detail: str = ''
    error_type: str = ''


def probe_llm(generate) -> HealthResult:
    try:
        text = generate(PROMPT)
    except Exception as exc:
        return HealthResult(ok=False, detail=str(exc),
                            error_type=type(exc).__name__)
    # A 200 that carries no text is still an outage — safety blocks and empty
    # candidate lists fail this way, and an exception-only check calls them
    # healthy.
    if not (text or '').strip():
        return HealthResult(ok=False, detail='empty response body',
                            error_type='EmptyResponse')
    return HealthResult(ok=True, detail=(text or '').strip()[:200])


def notify_slack(text, *, webhook_url, post) -> bool:
    """Post `text` to a Slack incoming webhook. True when it went out.

    Unconfigured is a normal state, not an error: the canary must still run
    (and still fail the job) before anyone wires up a webhook.
    """
    if not webhook_url:
        return False
    try:
        post(webhook_url, {'text': text})
    except Exception as exc:
        # Never let the alert channel mask the outage it is reporting: the
        # command still logs and still exits non-zero.
        logger.warning('[llm_health] Slack notify failed: %s', exc)
        return False
    return True


def default_generate(prompt: str) -> str:
    """The real Gemini call, resolved exactly like every other call site."""
    import google.generativeai as genai
    from django.conf import settings

    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    response = model.generate_content(prompt)
    return getattr(response, 'text', '') or ''


def default_post(url: str, payload: dict) -> None:
    """Minimal Slack incoming-webhook POST. No SDK, no new dependency."""
    import json
    import urllib.request

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    urllib.request.urlopen(request, timeout=10).close()
