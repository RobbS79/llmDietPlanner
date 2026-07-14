# Meta Pixel + CAPI + Consent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Instrument the acquisition funnel with a browser Meta Pixel (client events) plus server-side Conversions API for the money events (`signup`, `plan_generated`, `paid`), gated behind a GDPR-correct binary consent banner — so the FB/IG pilot produces real attribution and willingness-to-pay learning.

**Architecture:** New Django `analytics` app owns a `MarketingAttribution` model (one-to-one with `User`) and a CAPI service that fires server events via Celery. Three existing hook points call it: `login_app` registration (`signup`), the plan-generation Celery task (`plan_generated`), the billing Stripe webhook (`paid`). A first-party React consent banner mounted at app root gates a Pixel loader; the Pixel fires client events (`landing_view`, `quiz_started`, `checkout_started`). No event fires from both client and server → no dedup. Everything ships behind `ANALYTICS_ENABLED=false`.

**Tech Stack:** Django 5.1 + DRF, Celery (`llm_diet_planner_project.celery_compat.shared_task`), python-decouple `config()`, Django `TestCase`/`APIClient` (run via `python manage.py test`); React 18 + Vite + TypeScript, axios, react-query, Vitest + testing-library.

**Design spec:** `docs/superpowers/specs/2026-07-14-meta-pixel-capi-consent-design.md`

---

## Prerequisite (user-owned, does NOT block this build)

Meta Events Manager setup — Business+ad account, dataset (Pixel ID), CAPI access token, eatalnicek.eu domain verification. The build proceeds with `ANALYTICS_ENABLED=false` and placeholder env values; real IDs are plugged in and the flag flipped at rollout.

## File Structure

**Backend (new `analytics` app):**
- Create `analytics/__init__.py`, `analytics/apps.py`
- Create `analytics/models.py` — `MarketingAttribution` model
- Create `analytics/hashing.py` — `hash_email()` (SHA-256, normalized)
- Create `analytics/capi.py` — payload builder + send function (consent-gated)
- Create `analytics/tasks.py` — `send_capi_event_task` Celery task
- Create `analytics/events.py` — thin helpers `track_signup/plan_generated/paid(...)` that enqueue the task
- Create `analytics/views.py` — `ConsentView` (`POST /api/analytics/consent/`)
- Create `analytics/urls.py`
- Create `analytics/migrations/__init__.py` (+ generated migration)
- Create `analytics/tests.py`
- Modify `llm_diet_planner_project/settings.py` — register app, env vars, flag
- Modify `llm_diet_planner_project/urls.py` — mount `analytics.urls`
- Modify `llm_diet_planner_project/middleware.py` — CSP Facebook hosts
- Modify `login_app/views.py` — `signup` hook + attribution write
- Modify `login_app/schemas.py` — optional attribution fields on `RegistrationRequest`
- Modify `diet_planner/tasks.py` — `plan_generated` hook on successful completion
- Modify `billing/services.py` — `paid` hook in `handle_checkout_completed`

**Frontend:**
- Create `frontend/src/lib/analytics.ts` — Pixel loader + typed event helpers + `_fbp`/`_fbc`/UTM readers
- Create `frontend/src/lib/analytics.test.ts` — Vitest unit tests
- Create `frontend/src/components/ConsentBanner.tsx`
- Modify `frontend/src/App.tsx` — mount `<ConsentBanner/>` + analytics init at root
- Modify `frontend/src/pages/Landing.tsx` — `landing_view` + UTM capture
- Modify `frontend/src/pages/Onboarding.tsx` — `quiz_started`
- Modify `frontend/src/pages/Pricing.tsx` — `checkout_started`
- Modify `frontend/src/pages/Login.tsx` — attach attribution to register payload
- Modify `frontend/index.html` — CSP Facebook hosts

---

# Phase A — Backend foundation (ships dark)

## Task 1: Scaffold `analytics` app + `MarketingAttribution` model

**Files:**
- Create: `analytics/__init__.py` (empty), `analytics/apps.py`, `analytics/models.py`, `analytics/migrations/__init__.py`
- Modify: `llm_diet_planner_project/settings.py:81` (INSTALLED_APPS)
- Test: `analytics/tests.py`

- [ ] **Step 1: Create the app package**

`analytics/__init__.py`: empty file.

`analytics/apps.py`:
```python
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"
```

`analytics/migrations/__init__.py`: empty file.

- [ ] **Step 2: Register the app**

In `llm_diet_planner_project/settings.py`, add `"analytics",` to `INSTALLED_APPS` immediately after `"billing",` (line ~85).

- [ ] **Step 3: Write the model**

`analytics/models.py`:
```python
from django.conf import settings
from django.db import models


class MarketingAttribution(models.Model):
    """First-party attribution + consent record, one row per user.

    Populated at signup from the client-captured UTM/fbclid/consent payload,
    so we can answer "which campaign -> paid" in our own DB independent of Meta,
    and so webhook-time CAPI events can honor consent (no browser present then).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="marketing_attribution",
    )
    utm_source = models.CharField(max_length=255, blank=True, default="")
    utm_medium = models.CharField(max_length=255, blank=True, default="")
    utm_campaign = models.CharField(max_length=255, blank=True, default="")
    utm_content = models.CharField(max_length=255, blank=True, default="")
    utm_term = models.CharField(max_length=255, blank=True, default="")
    fbclid = models.CharField(max_length=512, blank=True, default="")
    fbp = models.CharField(max_length=255, blank=True, default="")
    fbc = models.CharField(max_length=512, blank=True, default="")
    landing_at = models.DateTimeField(null=True, blank=True)

    marketing_consent = models.BooleanField(default=False)
    consent_at = models.DateTimeField(null=True, blank=True)
    consent_version = models.CharField(max_length=20, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Attribution(user={self.user_id}, consent={self.marketing_consent})"
```

- [ ] **Step 4: Write a failing test for the model**

`analytics/tests.py`:
```python
from django.contrib.auth.models import User
from django.test import TestCase

from analytics.models import MarketingAttribution


class MarketingAttributionModelTests(TestCase):
    def test_defaults(self):
        user = User.objects.create_user(username="u1", email="u1@example.com")
        attr = MarketingAttribution.objects.create(user=user)
        self.assertFalse(attr.marketing_consent)
        self.assertEqual(attr.utm_source, "")
        self.assertEqual(user.marketing_attribution, attr)
```

- [ ] **Step 5: Make the migration**

Run: `python manage.py makemigrations analytics`
Expected: creates `analytics/migrations/0001_initial.py`.

- [ ] **Step 6: Run the test**

Run: `python manage.py test analytics -v 2`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add analytics/ llm_diet_planner_project/settings.py
git commit -m "feat(analytics): scaffold app + MarketingAttribution model"
```

## Task 2: Email hashing helper

**Files:**
- Create: `analytics/hashing.py`
- Test: `analytics/tests.py` (add class)

- [ ] **Step 1: Write the failing test**

Add to `analytics/tests.py`:
```python
from analytics.hashing import hash_email


class HashEmailTests(TestCase):
    def test_normalizes_then_sha256(self):
        # Meta requires lowercase + trimmed before SHA-256.
        import hashlib
        expected = hashlib.sha256("user@example.com".encode()).hexdigest()
        self.assertEqual(hash_email("  User@Example.com "), expected)

    def test_empty_returns_empty(self):
        self.assertEqual(hash_email(""), "")
        self.assertEqual(hash_email(None), "")
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python manage.py test analytics.tests.HashEmailTests -v 2`
Expected: FAIL — `ModuleNotFoundError: analytics.hashing`.

- [ ] **Step 3: Implement**

`analytics/hashing.py`:
```python
import hashlib


def hash_email(email: str | None) -> str:
    """Lowercase + trim + SHA-256 hex, per Meta CAPI advanced-matching spec."""
    if not email:
        return ""
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python manage.py test analytics.tests.HashEmailTests -v 2`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analytics/hashing.py analytics/tests.py
git commit -m "feat(analytics): SHA-256 email hashing for CAPI matching"
```

## Task 3: CAPI payload builder + send (consent-gated)

**Files:**
- Create: `analytics/capi.py`
- Test: `analytics/tests.py` (add class)

- [ ] **Step 1: Write the failing test**

Add to `analytics/tests.py`:
```python
from unittest.mock import patch
from django.test import override_settings

from analytics import capi


class BuildPayloadTests(TestCase):
    def test_build_payload_hashes_email_and_sets_action_source(self):
        payload = capi.build_payload(
            event_name="Purchase",
            event_id="evt-1",
            email="Buyer@Example.com",
            fbp="fb.1.123.456",
            fbc="fb.1.123.abc",
            client_ip="203.0.113.5",
            user_agent="UA/1.0",
            event_source_url="https://eatalnicek.eu/pricing",
            custom_data={"value": 99, "currency": "CZK"},
        )
        from analytics.hashing import hash_email
        data = payload["data"][0]
        self.assertEqual(data["event_name"], "Purchase")
        self.assertEqual(data["event_id"], "evt-1")
        self.assertEqual(data["action_source"], "website")
        self.assertEqual(data["user_data"]["em"], [hash_email("Buyer@Example.com")])
        self.assertEqual(data["user_data"]["fbp"], "fb.1.123.456")
        self.assertEqual(data["custom_data"], {"value": 99, "currency": "CZK"})


@override_settings(
    ANALYTICS_ENABLED=True, FB_PIXEL_ID="123", FB_CAPI_ACCESS_TOKEN="tok",
    FB_CAPI_TEST_EVENT_CODE="",
)
class SendEventTests(TestCase):
    @patch("analytics.capi.requests.post")
    def test_send_posts_to_graph(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"events_received": 1}
        ok = capi.send_event(event_name="CompleteRegistration", event_id="e1",
                             email="a@b.com")
        self.assertTrue(ok)
        url = mock_post.call_args[0][0]
        self.assertIn("/123/events", url)

    @patch("analytics.capi.requests.post")
    def test_disabled_flag_short_circuits(self, mock_post):
        with override_settings(ANALYTICS_ENABLED=False):
            ok = capi.send_event(event_name="CompleteRegistration", event_id="e1",
                                 email="a@b.com")
        self.assertFalse(ok)
        mock_post.assert_not_called()

    @patch("analytics.capi.requests.post")
    def test_missing_credentials_short_circuits(self, mock_post):
        with override_settings(FB_CAPI_ACCESS_TOKEN=""):
            ok = capi.send_event(event_name="CompleteRegistration", event_id="e1",
                                 email="a@b.com")
        self.assertFalse(ok)
        mock_post.assert_not_called()
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python manage.py test analytics.tests.BuildPayloadTests analytics.tests.SendEventTests -v 2`
Expected: FAIL — `ModuleNotFoundError: analytics.capi`.

- [ ] **Step 3: Implement**

`analytics/capi.py`:
```python
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
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python manage.py test analytics.tests.BuildPayloadTests analytics.tests.SendEventTests -v 2`
Expected: PASS (4 tests).

- [ ] **Step 5: Add settings + env vars**

In `llm_diet_planner_project/settings.py`, near the other `config(...)` blocks (after `FRONTEND_URL`, ~line 138):
```python
# --- Analytics / Meta Pixel + CAPI ---
ANALYTICS_ENABLED = config('ANALYTICS_ENABLED', default=False, cast=bool)
FB_PIXEL_ID = config('FB_PIXEL_ID', default='')
FB_CAPI_ACCESS_TOKEN = config('FB_CAPI_ACCESS_TOKEN', default='')
FB_CAPI_TEST_EVENT_CODE = config('FB_CAPI_TEST_EVENT_CODE', default='')
```

Add to `.env` (local, placeholder values so nothing breaks):
```
ANALYTICS_ENABLED=false
FB_PIXEL_ID=
FB_CAPI_ACCESS_TOKEN=
FB_CAPI_TEST_EVENT_CODE=
VITE_FB_PIXEL_ID=
```

- [ ] **Step 6: Commit**

```bash
git add analytics/capi.py analytics/tests.py llm_diet_planner_project/settings.py .env
git commit -m "feat(analytics): CAPI payload builder + consent-gated send"
```

## Task 4: Celery task + event helpers

**Files:**
- Create: `analytics/tasks.py`, `analytics/events.py`
- Test: `analytics/tests.py` (add class)

- [ ] **Step 1: Write the failing test**

Add to `analytics/tests.py`:
```python
from analytics import events


class EventHelperTests(TestCase):
    @patch("analytics.tasks.send_capi_event_task.delay")
    def test_track_paid_enqueues_purchase(self, mock_delay):
        user = User.objects.create_user(username="p1", email="p1@example.com")
        MarketingAttribution.objects.create(
            user=user, marketing_consent=True, fbp="fb.1.1.1", fbc="fb.1.1.c",
        )
        events.track_paid(user, value=99, currency="CZK")
        self.assertTrue(mock_delay.called)
        kwargs = mock_delay.call_args.kwargs
        self.assertEqual(kwargs["event_name"], "Purchase")
        self.assertEqual(kwargs["email"], "p1@example.com")
        self.assertEqual(kwargs["custom_data"], {"value": 99, "currency": "CZK"})
        self.assertEqual(kwargs["fbp"], "fb.1.1.1")

    @patch("analytics.tasks.send_capi_event_task.delay")
    def test_no_consent_skips(self, mock_delay):
        user = User.objects.create_user(username="p2", email="p2@example.com")
        MarketingAttribution.objects.create(user=user, marketing_consent=False)
        events.track_paid(user, value=99, currency="CZK")
        mock_delay.assert_not_called()

    @patch("analytics.tasks.send_capi_event_task.delay")
    def test_no_attribution_row_skips(self, mock_delay):
        user = User.objects.create_user(username="p3", email="p3@example.com")
        events.track_signup(user)
        mock_delay.assert_not_called()
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python manage.py test analytics.tests.EventHelperTests -v 2`
Expected: FAIL — `ModuleNotFoundError: analytics.events`.

- [ ] **Step 3: Implement the task**

`analytics/tasks.py`:
```python
from llm_diet_planner_project.celery_compat import shared_task
from analytics import capi


@shared_task
def send_capi_event_task(**kwargs) -> bool:
    """Fire-and-forget CAPI send. kwargs match capi.send_event signature."""
    return capi.send_event(**kwargs)
```

- [ ] **Step 4: Implement the helpers**

`analytics/events.py`:
```python
"""Consent-gated helpers that enqueue server CAPI events.

Callers pass a Django User. We read the user's MarketingAttribution row for
consent + fbp/fbc; if there is no row or consent is false, we do nothing.
Event ids are derived deterministically so a retry can't double-count.
"""
import logging

from analytics.models import MarketingAttribution
from analytics.tasks import send_capi_event_task

logger = logging.getLogger(__name__)


def _attribution(user):
    return MarketingAttribution.objects.filter(user=user).first()


def _enqueue(user, *, event_name, event_id, custom_data=None):
    attr = _attribution(user)
    if attr is None or not attr.marketing_consent:
        return
    send_capi_event_task.delay(
        event_name=event_name,
        event_id=event_id,
        email=user.email or "",
        fbp=attr.fbp,
        fbc=attr.fbc,
        event_source_url="https://eatalnicek.eu/",
        custom_data=custom_data,
    )


def track_signup(user):
    _enqueue(user, event_name="CompleteRegistration",
             event_id=f"signup-{user.id}")


def track_plan_generated(user, goal_id):
    _enqueue(user, event_name="PlanGenerated",
             event_id=f"plan-{goal_id}")


def track_paid(user, *, value, currency="CZK"):
    _enqueue(user, event_name="Purchase",
             event_id=f"paid-{user.id}-{value}",
             custom_data={"value": value, "currency": currency})
```

- [ ] **Step 5: Run it, verify it passes**

Run: `python manage.py test analytics.tests.EventHelperTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add analytics/tasks.py analytics/events.py analytics/tests.py
git commit -m "feat(analytics): Celery task + consent-gated signup/plan/paid helpers"
```

## Task 5: Consent endpoint

**Files:**
- Create: `analytics/views.py`, `analytics/urls.py`
- Modify: `llm_diet_planner_project/urls.py:38` (mount)
- Test: `analytics/tests.py` (add class)

- [ ] **Step 1: Write the failing test**

Add to `analytics/tests.py`:
```python
from rest_framework.test import APIClient


class ConsentEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="c1", email="c1@example.com",
                                              password="pw12345x")

    def test_requires_auth(self):
        resp = self.client.post("/api/analytics/consent/",
                                {"consent": True, "version": "1"}, format="json")
        self.assertIn(resp.status_code, (401, 403))

    def test_records_consent(self):
        self.client.force_authenticate(self.user)
        resp = self.client.post("/api/analytics/consent/",
                                {"consent": True, "version": "1"}, format="json")
        self.assertEqual(resp.status_code, 200)
        attr = MarketingAttribution.objects.get(user=self.user)
        self.assertTrue(attr.marketing_consent)
        self.assertEqual(attr.consent_version, "1")
        self.assertIsNotNone(attr.consent_at)

    def test_withdraw_consent(self):
        self.client.force_authenticate(self.user)
        MarketingAttribution.objects.create(user=self.user, marketing_consent=True)
        resp = self.client.post("/api/analytics/consent/",
                                {"consent": False, "version": "1"}, format="json")
        self.assertEqual(resp.status_code, 200)
        attr = MarketingAttribution.objects.get(user=self.user)
        self.assertFalse(attr.marketing_consent)
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python manage.py test analytics.tests.ConsentEndpointTests -v 2`
Expected: FAIL — 404 (URL not mounted).

- [ ] **Step 3: Implement view + urls**

`analytics/views.py`:
```python
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.models import MarketingAttribution


class ConsentView(APIView):
    """Record a post-authentication consent change (opt-in or withdrawal)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        consent = bool(request.data.get("consent"))
        version = str(request.data.get("version", ""))[:20]
        attr, _ = MarketingAttribution.objects.get_or_create(user=request.user)
        attr.marketing_consent = consent
        attr.consent_version = version
        attr.consent_at = timezone.now()
        attr.save(update_fields=["marketing_consent", "consent_version",
                                 "consent_at", "updated_at"])
        return Response({"status": "success", "data": {"consent": consent},
                        "error": None})
```

`analytics/urls.py`:
```python
from django.urls import path

from analytics.views import ConsentView

app_name = "analytics"

urlpatterns = [
    path("consent/", ConsentView.as_view(), name="consent"),
]
```

In `llm_diet_planner_project/urls.py`, add after the billing include (line ~37):
```python
    path("api/analytics/", include("analytics.urls")),
```

- [ ] **Step 4: Run it, verify it passes**

Run: `python manage.py test analytics.tests.ConsentEndpointTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add analytics/views.py analytics/urls.py llm_diet_planner_project/urls.py analytics/tests.py
git commit -m "feat(analytics): authenticated consent endpoint"
```

---

# Phase B — Wire server events into existing flows

## Task 6: `signup` hook + attribution write at registration

**Files:**
- Modify: `login_app/schemas.py:8` (`RegistrationRequest`)
- Modify: `login_app/views.py:143-171` (`RegistrationView.post`)
- Test: `login_app/tests.py` (add class) or `analytics/tests.py`

- [ ] **Step 1: Write the failing test**

Add to `login_app/tests.py` (top imports as needed):
```python
from unittest.mock import patch
from analytics.models import MarketingAttribution


class RegistrationAttributionTests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

    @patch("login_app.views.track_signup")
    def test_registration_persists_attribution_and_fires_signup(self, mock_track):
        payload = {
            "username": "newuser", "email": "new@example.com",
            "password": "Abcd1234", "passwordConfirm": "Abcd1234",
            "attribution": {
                "utm_source": "facebook", "utm_campaign": "pilot",
                "fbclid": "abc", "fbp": "fb.1.2.3", "fbc": "fb.1.2.c",
                "consent": True, "consent_version": "1",
            },
        }
        resp = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        from django.contrib.auth.models import User
        user = User.objects.get(username="newuser")
        attr = MarketingAttribution.objects.get(user=user)
        self.assertEqual(attr.utm_source, "facebook")
        self.assertTrue(attr.marketing_consent)
        self.assertEqual(attr.fbp, "fb.1.2.3")
        mock_track.assert_called_once_with(user)

    @patch("login_app.views.track_signup")
    def test_registration_without_attribution_still_works(self, mock_track):
        payload = {"username": "plain", "email": "plain@example.com",
                   "password": "Abcd1234", "passwordConfirm": "Abcd1234"}
        resp = self.client.post("/api/auth/register/", payload, format="json")
        self.assertEqual(resp.status_code, 201)
        # No consent -> track_signup called but helper no-ops (row has consent=False)
        # Row still created so later consent changes have somewhere to write.
        from django.contrib.auth.models import User
        user = User.objects.get(username="plain")
        self.assertTrue(MarketingAttribution.objects.filter(user=user).exists())
```

> NOTE for implementer: confirm the exact password rules in `login_app/schemas.py` `RegistrationRequest` and use a password string that passes them. Adjust `"Abcd1234"` if validation differs.

- [ ] **Step 2: Run it, verify it fails**

Run: `python manage.py test login_app.tests.RegistrationAttributionTests -v 2`
Expected: FAIL — attribution not persisted / `track_signup` not imported.

- [ ] **Step 3: Add the optional attribution schema**

In `login_app/schemas.py`, add near `RegistrationRequest`:
```python
from typing import Optional
from pydantic import BaseModel


class AttributionPayload(BaseModel):
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    utm_content: str = ""
    utm_term: str = ""
    fbclid: str = ""
    fbp: str = ""
    fbc: str = ""
    consent: bool = False
    consent_version: str = ""
```

Add an optional field to `RegistrationRequest`:
```python
    attribution: Optional[AttributionPayload] = None
```

- [ ] **Step 4: Wire the view**

In `login_app/views.py`, add imports at top:
```python
from django.utils import timezone
from analytics.models import MarketingAttribution
from analytics.events import track_signup
```

In `RegistrationView.post`, immediately after `user = User.objects.create_user(...)` (line ~159), before generating verification artifacts:
```python
            # Persist first-party attribution + consent (safe defaults if absent).
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
            # Server-side CAPI signup event (no-ops unless consent granted).
            track_signup(user)
```

- [ ] **Step 5: Run it, verify it passes**

Run: `python manage.py test login_app.tests.RegistrationAttributionTests -v 2`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the whole login_app suite (regression)**

Run: `python manage.py test login_app -v 2`
Expected: PASS (no existing tests broken).

- [ ] **Step 7: Commit**

```bash
git add login_app/schemas.py login_app/views.py login_app/tests.py
git commit -m "feat(analytics): persist attribution + fire signup CAPI at registration"
```

## Task 7: `paid` hook in Stripe webhook

**Files:**
- Modify: `billing/services.py` (`handle_checkout_completed`, ~line 201-223)
- Test: `billing/tests.py` (add to webhook test class, or new class)

- [ ] **Step 1: Write the failing test**

`handle_checkout_completed(event)` (billing/services.py:201) reads `event['data']['object']` for `mode`/`customer`/`subscription`/`id`/`metadata`, calls `stripe.Subscription.retrieve(...)`, resolves the user from `metadata.user_id`, then `upsert_subscription(...)` and `_send_welcome_email(...)`. We patch the Stripe call + the two heavy collaborators so only the `track_paid` wiring is under test.

Add to `billing/tests.py`:
```python
from unittest.mock import patch
from analytics.models import MarketingAttribution


class PaidEventTests(TestCase):
    @patch("billing.services._send_welcome_email")
    @patch("billing.services.upsert_subscription")
    @patch("billing.services.stripe.Subscription.retrieve")
    @patch("billing.services.track_paid")
    def test_checkout_completed_fires_paid_with_tier_price(
        self, mock_paid, mock_retrieve, mock_upsert, mock_welcome,
    ):
        from django.contrib.auth.models import User
        from billing import services
        from billing.models import SubscriptionPlan, Tier

        user = User.objects.create_user(username="buyer", email="buyer@example.com")
        MarketingAttribution.objects.create(user=user, marketing_consent=True)
        SubscriptionPlan.objects.create(
            tier=Tier.STANDARD, name="Vařto Standard", price_czk=99,
            stripe_price_id="price_std", monthly_plan_quota=7, edits_per_plan=10,
        )
        mock_retrieve.return_value = {
            "id": "sub_1", "status": "active",
            "items": {"data": [{"price": {"id": "price_std"}}]},
        }
        mock_upsert.return_value = object()  # non-None => provisioned

        event = {"data": {"object": {
            "mode": "subscription", "customer": "cus_1", "subscription": "sub_1",
            "id": "cs_1",
            "metadata": {"user_id": str(user.id), "tier": Tier.STANDARD},
        }}}
        services.handle_checkout_completed(event)

        mock_paid.assert_called_once()
        self.assertEqual(mock_paid.call_args.args[0], user)
        self.assertEqual(mock_paid.call_args.kwargs["value"], 99)
        self.assertEqual(mock_paid.call_args.kwargs["currency"], "CZK")
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python manage.py test billing.tests.PaidEventTests -v 2`
Expected: FAIL — `track_paid` not imported/called.

- [ ] **Step 3: Wire the handler**

In `billing/services.py`, add import near the top:
```python
from analytics.events import track_paid
```

In `handle_checkout_completed`, after the successful `upsert_subscription(...)` / `logger.info('Provisioned ...')` and alongside `_send_welcome_email(user, tier)` (line ~222):
```python
    # Fire server-side Purchase (no-ops unless the user consented).
    plan = SubscriptionPlan.objects.filter(tier=tier).first()
    value = plan.price_czk if plan else 0
    track_paid(user, value=value, currency="CZK")
```

> Confirm `SubscriptionPlan` is imported in this module; if not, add it to the existing model imports.

- [ ] **Step 4: Run it, verify it passes**

Run: `python manage.py test billing.tests.PaidEventTests -v 2`
Expected: PASS.

- [ ] **Step 5: Regression — whole billing suite**

Run: `python manage.py test billing -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add billing/services.py billing/tests.py
git commit -m "feat(analytics): fire paid CAPI on Stripe checkout completion"
```

## Task 8: `plan_generated` hook in the generation tasks

There are **two** completion points, both in `diet_planner/tasks.py`, both using local var `goal`:
- `process_dietary_goal_task` — line **882–884** (`goal.status = COMPLETED; goal.save(...)`)
- `process_dietary_goal_catalog_task` — line **1323–1325** (prod uses this one; `CATALOG_CONSTRAINED_GENERATION`)

The hook goes after **both** saves.

**Files:**
- Modify: `diet_planner/tasks.py` (import + both completion points)
- Test: `diet_planner/tests/test_plan_generated_event.py` (new)

- [ ] **Step 1: Wire the hook**

In `diet_planner/tasks.py`, add near the top imports:
```python
from analytics.events import track_plan_generated
```

Immediately after **each** completion save — after line 884 (`goal.save(update_fields=['status', 'completed_at'])` in `process_dietary_goal_task`) and after line 1325 (the identical save in `process_dietary_goal_catalog_task`) — add:
```python
        try:
            track_plan_generated(goal.user, goal.id)
        except Exception:
            logger.exception("track_plan_generated failed (non-fatal)")
```
(Analytics must never break generation — hence the try/except.)

- [ ] **Step 2: Write the test (mirrors the existing catalog-task test pattern)**

Model this on `diet_planner/tests/test_catalog_task_restrictions.py` — copy its `setUp` (builds `self.goal` with a user + canonical ingredients) and its mock scaffolding verbatim, changing only the assertion. New file `diet_planner/tests/test_plan_generated_event.py`:
```python
from unittest.mock import patch

from django.test import TestCase

# COPY the exact setUp + fixtures from test_catalog_task_restrictions.py so
# self.goal is a valid, catalog-ready DietaryGoal owned by a real User.


class PlanGeneratedEventTests(TestCase):
    def setUp(self):
        ...  # <- paste setUp body from test_catalog_task_restrictions.py

    @patch("diet_planner.tasks.track_plan_generated")
    def test_catalog_task_fires_plan_generated(self, mock_track):
        from diet_planner.llm_service import GeminiService
        from diet_planner.tasks import process_dietary_goal_catalog_task

        def _capture(*args, **kwargs):
            # minimal valid plan payload — copy the _capture return shape used in
            # test_catalog_task_restrictions.py so the task reaches COMPLETED
            ...

        with patch.object(GeminiService, "generate_catalog_constrained_plan", _capture), \
             patch("diet_planner.services.recipe_retrieval.grounding_enabled", return_value=False):
            result = process_dietary_goal_catalog_task.apply(args=[self.goal.id]).get()

        self.assertEqual(result["status"], "success", result)
        mock_track.assert_called_once()
        self.assertEqual(mock_track.call_args.args[0], self.goal.user)
        self.assertEqual(mock_track.call_args.args[1], self.goal.id)
```

> The two `...` are filled by pasting the real `setUp` and `_capture` payload from `test_catalog_task_restrictions.py` (lines ~40–105). That existing test already drives this exact task to a successful COMPLETED result — reuse it rather than authoring new LLM mocks. `track_plan_generated` is a real import (added in Step 1); it is patched here so we assert the wiring without hitting the network.

- [ ] **Step 3: Run it, verify it fails first (comment out the Step 1 hook to confirm), then passes with the hook**

Run: `python manage.py test diet_planner.tests.test_plan_generated_event -v 2`
Expected: with the hook in place, PASS; `mock_track` called once with `(goal.user, goal.id)`.

- [ ] **Step 4: Commit**

```bash
git add diet_planner/tasks.py diet_planner/tests/test_plan_generated_event.py
git commit -m "feat(analytics): fire plan_generated CAPI on successful generation (both task paths)"
```

---

# Phase C — CSP (backend + frontend in lockstep)

## Task 9: Add Facebook hosts to CSP

**Files:**
- Modify: `llm_diet_planner_project/middleware.py:15-29`
- Modify: `frontend/index.html:8`
- Test: `analytics/tests.py` (add class)

- [ ] **Step 1: Write the failing test**

Add to `analytics/tests.py`:
```python
class CSPHeaderTests(TestCase):
    def test_csp_allows_facebook_pixel(self):
        resp = self.client.get("/health/")
        csp = resp.headers.get("Content-Security-Policy", "")
        self.assertIn("https://connect.facebook.net", csp)
        self.assertIn("https://www.facebook.com", csp)
```

> If `/health/` doesn't emit CSP in the test env, use any non-`/admin/` path that returns a response through the middleware (e.g. `/api/billing/plans/`).

- [ ] **Step 2: Run it, verify it fails**

Run: `python manage.py test analytics.tests.CSPHeaderTests -v 2`
Expected: FAIL — Facebook hosts absent.

- [ ] **Step 3: Update the middleware**

In `llm_diet_planner_project/middleware.py`, edit the CSP string:
```python
                "script-src 'self' https://connect.facebook.net; "
                ...
                "img-src 'self' data: https://www.facebook.com; "
                ...
                "connect-src 'self' https://www.facebook.com; "
```
(Keep every other directive exactly as-is; only these three gain a host.)

- [ ] **Step 4: Update index.html meta CSP (lockstep)**

In `frontend/index.html:8`, mirror the same three additions in the `<meta http-equiv="Content-Security-Policy">` content so the meta and header agree (the fonts-bug lesson).

- [ ] **Step 5: Run it, verify it passes**

Run: `python manage.py test analytics.tests.CSPHeaderTests -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add llm_diet_planner_project/middleware.py frontend/index.html analytics/tests.py
git commit -m "feat(analytics): allow Meta Pixel hosts in CSP (header + meta)"
```

---

# Phase D — Frontend

## Task 10: Analytics lib (Pixel loader + helpers + readers)

**Files:**
- Create: `frontend/src/lib/analytics.ts`
- Test: `frontend/src/lib/analytics.test.ts`

- [ ] **Step 1: Write the failing test**

`frontend/src/lib/analytics.test.ts`:
```typescript
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readUtmParams, getConsent, setConsent, CONSENT_KEY } from './analytics';

describe('analytics utils', () => {
  beforeEach(() => { localStorage.clear(); });

  it('reads utm params + fbclid from a query string', () => {
    const utm = readUtmParams('?utm_source=facebook&utm_campaign=pilot&fbclid=xyz');
    expect(utm.utm_source).toBe('facebook');
    expect(utm.utm_campaign).toBe('pilot');
    expect(utm.fbclid).toBe('xyz');
  });

  it('returns empty strings for missing params', () => {
    const utm = readUtmParams('?foo=bar');
    expect(utm.utm_source).toBe('');
    expect(utm.fbclid).toBe('');
  });

  it('persists and reads consent decision', () => {
    expect(getConsent()).toBeNull();
    setConsent(true);
    expect(getConsent()).toBe(true);
    setConsent(false);
    expect(getConsent()).toBe(false);
    expect(localStorage.getItem(CONSENT_KEY)).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run it, verify it fails**

Run: `cd frontend && npx vitest run src/lib/analytics.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`frontend/src/lib/analytics.ts`:
```typescript
// Meta Pixel loader + funnel event helpers. Everything is a no-op unless the
// user has granted consent AND VITE_FB_PIXEL_ID is set.

export const CONSENT_KEY = 'mkt_consent_v1';
export const CONSENT_VERSION = '1';
const UTM_KEY = 'mkt_attribution_v1';

export type UtmParams = {
  utm_source: string; utm_medium: string; utm_campaign: string;
  utm_content: string; utm_term: string; fbclid: string;
};

const EMPTY_UTM: UtmParams = {
  utm_source: '', utm_medium: '', utm_campaign: '',
  utm_content: '', utm_term: '', fbclid: '',
};

const PIXEL_ID = import.meta.env.VITE_FB_PIXEL_ID as string | undefined;

declare global { interface Window { fbq?: (...args: unknown[]) => void; } }

export function readUtmParams(search: string): UtmParams {
  const p = new URLSearchParams(search);
  return {
    utm_source: p.get('utm_source') ?? '',
    utm_medium: p.get('utm_medium') ?? '',
    utm_campaign: p.get('utm_campaign') ?? '',
    utm_content: p.get('utm_content') ?? '',
    utm_term: p.get('utm_term') ?? '',
    fbclid: p.get('fbclid') ?? '',
  };
}

// Capture UTM/fbclid once at landing; keep the first-touch values.
export function captureAttribution(search: string): void {
  if (localStorage.getItem(UTM_KEY)) return;
  const utm = readUtmParams(search);
  const anySet = Object.values(utm).some((v) => v !== '');
  if (anySet) localStorage.setItem(UTM_KEY, JSON.stringify(utm));
}

export function getStoredAttribution(): UtmParams {
  try { return { ...EMPTY_UTM, ...JSON.parse(localStorage.getItem(UTM_KEY) || '{}') }; }
  catch { return EMPTY_UTM; }
}

export function getConsent(): boolean | null {
  const raw = localStorage.getItem(CONSENT_KEY);
  if (raw === null) return null;
  try { return JSON.parse(raw).consent === true; } catch { return null; }
}

export function setConsent(consent: boolean): void {
  localStorage.setItem(CONSENT_KEY,
    JSON.stringify({ consent, version: CONSENT_VERSION, ts: Date.now() }));
}

// Read the pixel's first-party cookies (available only after the pixel loads).
export function readCookie(name: string): string {
  const m = document.cookie.match(new RegExp('(^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[2]) : '';
}

let loaded = false;
export function loadPixel(): void {
  if (loaded || !PIXEL_ID || getConsent() !== true) return;
  loaded = true;
  /* eslint-disable */
  (function (f: any, b, e, v, n?: any, t?: any, s?: any) {
    if (f.fbq) return; n = f.fbq = function () {
      n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
    };
    if (!f._fbq) f._fbq = n; n.push = n; n.loaded = true; n.version = '2.0';
    n.queue = []; t = b.createElement(e); t.async = true;
    t.src = v; s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s);
  })(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');
  /* eslint-enable */
  window.fbq!('init', PIXEL_ID);
  window.fbq!('track', 'PageView');
}

function track(event: string, params?: Record<string, unknown>): void {
  if (getConsent() !== true || !window.fbq) return;
  window.fbq('track', event, params);
}
function trackCustom(event: string, params?: Record<string, unknown>): void {
  if (getConsent() !== true || !window.fbq) return;
  window.fbq('trackCustom', event, params);
}

export const trackLandingView = () => track('PageView');
export const trackQuizStarted = () => trackCustom('QuizStarted');
export const trackCheckoutStarted = () => track('InitiateCheckout');
```

- [ ] **Step 4: Run it, verify it passes**

Run: `cd frontend && npx vitest run src/lib/analytics.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/analytics.ts frontend/src/lib/analytics.test.ts
git commit -m "feat(analytics): frontend pixel loader + funnel helpers + utm capture"
```

## Task 11: Consent banner component

**Files:**
- Create: `frontend/src/components/ConsentBanner.tsx`
- Modify: `frontend/src/App.tsx` (mount at root)

- [ ] **Step 1: Implement the banner**

`frontend/src/components/ConsentBanner.tsx`:
```tsx
import { useEffect, useState } from 'react';
import { getConsent, setConsent, loadPixel, CONSENT_VERSION } from '@/lib/analytics';
import { api } from '@/lib/api';

// Binary GDPR consent banner (Přijmout / Odmítnout, equal prominence).
// Shows until a decision exists in localStorage. Market-Paper themed.
export function ConsentBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => { setVisible(getConsent() === null); }, []);

  async function decide(consent: boolean) {
    setConsent(consent);
    setVisible(false);
    if (consent) loadPixel();
    // Best-effort server sync if authenticated; ignore failures/401.
    try { await api.post('/analytics/consent/', { consent, version: CONSENT_VERSION }); }
    catch { /* anonymous or offline — decision rides the signup payload */ }
  }

  if (!visible) return null;

  return (
    <div role="dialog" aria-label="Souhlas s cookies"
         className="fixed bottom-0 inset-x-0 z-50 border-t border-stone-300 bg-[#faf7f0] text-stone-800 px-4 py-4 shadow-lg">
      <div className="mx-auto max-w-4xl flex flex-col sm:flex-row sm:items-center gap-3">
        <p className="text-sm leading-snug flex-1">
          Používáme marketingové cookies (Meta Pixel), abychom měřili, jak lidé
          přicházejí z reklam. Bez vašeho souhlasu se nenačtou.{' '}
          <a href="/privacy" className="underline">Zásady ochrany údajů</a>.
        </p>
        <div className="flex gap-2 shrink-0">
          <button onClick={() => decide(false)}
                  className="px-4 py-2 text-sm rounded border border-stone-400 hover:bg-stone-100">
            Odmítnout
          </button>
          <button onClick={() => decide(true)}
                  className="px-4 py-2 text-sm rounded bg-stone-800 text-white hover:bg-stone-700">
            Přijmout
          </button>
        </div>
      </div>
    </div>
  );
}
```

> EN gloss for review: "We use marketing cookies (Meta Pixel) to measure how people arrive from ads. Without your consent they won't load. Privacy policy." Buttons: Odmítnout = Reject, Přijmout = Accept. Equal size/weight satisfies the no-dark-pattern rule.

- [ ] **Step 2: Mount at app root + init pixel on load if already consented**

In `frontend/src/App.tsx`, import and render `<ConsentBanner />` inside the top-level app tree (outside `<Routes>` so it shows on every route), and call `loadPixel()` once on mount so returning consented users get the pixel:
```tsx
import { ConsentBanner } from '@/components/ConsentBanner';
import { loadPixel } from '@/lib/analytics';
// ...in the App component body:
useEffect(() => { loadPixel(); }, []);
// ...in JSX, alongside <BrowserRouter>...</BrowserRouter> (as a sibling within the root wrapper):
<ConsentBanner />
```

- [ ] **Step 3: Verify build compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ConsentBanner.tsx frontend/src/App.tsx
git commit -m "feat(analytics): consent banner mounted app-wide, gates pixel"
```

## Task 12: Wire client events + attach attribution to signup

**Files:**
- Modify: `frontend/src/pages/Landing.tsx` (`landing_view` + `captureAttribution`)
- Modify: `frontend/src/pages/Onboarding.tsx` (`quiz_started`)
- Modify: `frontend/src/pages/Pricing.tsx` (`checkout_started`)
- Modify: `frontend/src/pages/Login.tsx` (attribution on register)

- [ ] **Step 1: Landing — capture + view**

In `frontend/src/pages/Landing.tsx`, add on mount:
```tsx
import { useEffect } from 'react';
import { captureAttribution, trackLandingView } from '@/lib/analytics';
// ...inside the component:
useEffect(() => {
  captureAttribution(window.location.search);
  trackLandingView();
}, []);
```

- [ ] **Step 2: Onboarding — quiz_started**

In `frontend/src/pages/Onboarding.tsx`, on mount:
```tsx
import { useEffect } from 'react';
import { trackQuizStarted } from '@/lib/analytics';
// ...inside the component:
useEffect(() => { trackQuizStarted(); }, []);
```

- [ ] **Step 3: Pricing — checkout_started**

In `frontend/src/pages/Pricing.tsx`, call `trackCheckoutStarted()` in the click handler that initiates the Stripe checkout (immediately before the redirect/POST):
```tsx
import { trackCheckoutStarted } from '@/lib/analytics';
// ...in the checkout handler, before the request:
trackCheckoutStarted();
```

- [ ] **Step 4: Login — attach attribution to register payload**

In `frontend/src/pages/Login.tsx`, extend the register mutation payload. Import:
```tsx
import { getStoredAttribution, getConsent, CONSENT_VERSION, readCookie } from '@/lib/analytics';
```
Change the register `mutationFn` to include an `attribution` object:
```tsx
mutationFn: (data: { username: string; email: string; password: string; passwordConfirm: string }) => {
  const utm = getStoredAttribution();
  const attribution = {
    ...utm,
    fbp: readCookie('_fbp'),
    fbc: readCookie('_fbc'),
    consent: getConsent() === true,
    consent_version: CONSENT_VERSION,
  };
  return axios.post('/api/auth/register/', { ...data, attribution });
},
```

- [ ] **Step 5: Verify build + existing frontend tests**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: no type errors; all tests (incl. smoke) pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Landing.tsx frontend/src/pages/Onboarding.tsx frontend/src/pages/Pricing.tsx frontend/src/pages/Login.tsx
git commit -m "feat(analytics): wire landing/quiz/checkout events + signup attribution"
```

---

# Phase E — Verify

## Task 13: Full suite + config matrix + QA checklist

- [ ] **Step 1: Backend — full test run**

Run: `python manage.py test analytics login_app billing diet_planner -v 2`
Expected: all PASS. If `diet_planner` has slow/networked tests, at minimum run `analytics login_app billing` green + the one new `diet_planner` test.

- [ ] **Step 2: Frontend — full test run + typecheck**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: PASS.

- [ ] **Step 3: Document the env matrix for deploy**

Confirm these are set (placeholder/false locally; real values on DO `squid-app` at rollout):
`ANALYTICS_ENABLED`, `FB_PIXEL_ID`, `FB_CAPI_ACCESS_TOKEN`, `FB_CAPI_TEST_EVENT_CODE`, `VITE_FB_PIXEL_ID`. Add them to `docker-compose` env passthrough if backend/worker need them (they do: web + celery worker).

- [ ] **Step 4: Manual validation plan (post-deploy, gated on Meta prerequisite)**

Written checklist for when the Meta dataset exists and env is set with `ANALYTICS_ENABLED=true` + a `FB_CAPI_TEST_EVENT_CODE`:
1. Meta Events Manager → Test Events: accept consent on prod, walk landing → quiz → checkout; confirm `PageView`, `QuizStarted`, `InitiateCheckout` arrive (browser) and `CompleteRegistration` arrives (server).
2. Complete a real (test-mode) purchase; confirm `Purchase` server event with value + CZK.
3. Reject consent in a fresh browser profile; confirm ZERO events fire (client and server) — check Test Events shows nothing and DB `marketing_consent=False`.
4. Meta Pixel Helper extension shows the pixel firing only after Accept.

- [ ] **Step 5: Prod QA (per project rule — prod, all affected pages, Playwright)**

Drive the full funnel against `https://eatalnicek.eu` after deploy with `ANALYTICS_ENABLED` still `false` first (confirms nothing breaks / no pixel loads / no console errors), then flip to `true` and re-verify events land.

- [ ] **Step 6: Final commit / branch wrap**

```bash
git status   # ensure clean
```
Then use the finishing-a-development-branch skill to decide merge/PR.

---

## Rollout order (operational, after code merged)

1. Merge with `ANALYTICS_ENABLED=false` (dark) — nothing user-visible except the consent banner, which is harmless with no pixel.
2. User completes Meta prerequisite (Pixel ID + CAPI token + domain verification).
3. Set env on DO `squid-app`: `FB_PIXEL_ID`, `FB_CAPI_ACCESS_TOKEN`, `VITE_FB_PIXEL_ID`, optional `FB_CAPI_TEST_EVENT_CODE`; deploy.
4. Validate via Events Manager Test Events (Task 13 Step 4).
5. Flip `ANALYTICS_ENABLED=true`; run prod QA (Step 5); remove `FB_CAPI_TEST_EVENT_CODE`.

## Note on the consent banner scope (correction to spec)

The spec said the banner shows "only on the public surface." In implementation it mounts at the app **root** so the pixel works across public *and* authenticated routes (`/onboarding` and checkout are needed for `quiz_started` / `checkout_started`). The banner still only *appears* until a decision is stored — in practice on the first (usually public) visit — but it is not scoped to public routes. This is the correct behavior; the spec statement was imprecise.
