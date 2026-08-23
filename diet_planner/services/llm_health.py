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


SLACK_POST_MESSAGE_URL = 'https://slack.com/api/chat.postMessage'


def notify_slack(text, *, webhook_url='', bot_token='', channel='',
                 post) -> bool:
    """Deliver `text` to Slack. True only when Slack actually accepted it.

    Two transports. A bot token + channel wins when both are set, because it
    reuses the credentials slack_bot already holds — nothing new to create.
    An incoming webhook is the fallback.

    Unconfigured is a normal state, not an error: the canary must still run
    (and still fail the job) before anyone wires up Slack.
    """
    if bot_token and channel:
        url = SLACK_POST_MESSAGE_URL
        payload = {'channel': channel, 'text': text}
        headers = {'Content-Type': 'application/json; charset=utf-8',
                   'Authorization': f'Bearer {bot_token}'}
    elif webhook_url:
        url = webhook_url
        payload = {'text': text}
        headers = {'Content-Type': 'application/json'}
    else:
        return False

    try:
        body = post(url, payload, headers) or {}
    except Exception as exc:
        # Never let the alert channel mask the outage it is reporting: the
        # command still logs and still exits non-zero.
        logger.warning('[llm_health] Slack notify failed: %s', exc)
        return False

    # chat.postMessage answers HTTP 200 even when it refuses the message
    # ({"ok": false, "error": "not_in_channel"}), so status alone would lie.
    if body.get('ok') is False:
        logger.warning('[llm_health] Slack rejected the message: %s',
                       body.get('error') or body)
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


def default_post(url: str, payload: dict, headers: dict) -> dict:
    """Minimal Slack POST. No SDK, no new dependency.

    Returns the parsed JSON body when there is one — chat.postMessage reports
    refusals in the body, not the status code. A webhook answers plain "ok",
    which parses to {} and is treated as delivered.
    """
    import json
    import urllib.request

    request = urllib.request.Request(
        url, data=json.dumps(payload).encode('utf-8'), headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read().decode('utf-8', 'replace')
    try:
        return json.loads(raw)
    except ValueError:
        return {}
