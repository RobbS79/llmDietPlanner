import logging
import time

import requests
from django.conf import settings

from analytics.hashing import hash_email

logger = logging.getLogger(__name__)

GRAPH_VERSION = "v19.0"
_TIMEOUT = 5  # seconds; server event, must never block the request path long


def build_payload(*, event_name, event_id, email=None, fbp="", fbc="",
                  client_ip="", user_agent="", event_source_url="",
                  custom_data=None):
    """Assemble a single-event Meta CAPI payload (advanced matching)."""
    user_data = {}
    hashed = hash_email(email)
    if hashed:
        user_data["em"] = [hashed]
    if fbp:
        user_data["fbp"] = fbp
    if fbc:
        user_data["fbc"] = fbc
    if client_ip:
        user_data["client_ip_address"] = client_ip
    if user_agent:
        user_data["client_user_agent"] = user_agent

    event = {
        "event_name": event_name,
        "event_time": int(time.time()),
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
    }
    if event_source_url:
        event["event_source_url"] = event_source_url
    if custom_data:
        event["custom_data"] = custom_data
    return {"data": [event]}


def send_event(*, event_name, event_id, email=None, fbp="", fbc="",
               client_ip="", user_agent="", event_source_url="",
               custom_data=None) -> bool:
    """POST one event to the Conversions API. Best-effort; never raises.

    Returns True on a 2xx from Meta, False if disabled/misconfigured/failed.
    Consent is enforced by CALLERS (they don't call this unless consent is
    true) — this function only guards on config.
    """
    if not getattr(settings, "ANALYTICS_ENABLED", False):
        return False
    pixel_id = getattr(settings, "FB_PIXEL_ID", "")
    token = getattr(settings, "FB_CAPI_ACCESS_TOKEN", "")
    if not pixel_id or not token:
        return False

    payload = build_payload(
        event_name=event_name, event_id=event_id, email=email, fbp=fbp, fbc=fbc,
        client_ip=client_ip, user_agent=user_agent,
        event_source_url=event_source_url, custom_data=custom_data,
    )
    test_code = getattr(settings, "FB_CAPI_TEST_EVENT_CODE", "")
    if test_code:
        payload["test_event_code"] = test_code

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{pixel_id}/events"
    try:
        resp = requests.post(url, params={"access_token": token}, json=payload,
                             timeout=_TIMEOUT)
        if resp.status_code >= 400:
            logger.warning("CAPI %s failed: %s %s", event_name,
                           resp.status_code, resp.text[:300])
            return False
        return True
    except requests.RequestException as exc:
        logger.warning("CAPI %s network error: %s", event_name, exc)
        return False
