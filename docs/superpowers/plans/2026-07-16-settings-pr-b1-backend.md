# Settings PR B — Phase 1 (Backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add the backend the Settings page needs — merge-PATCH for preferences, an extended profile payload, a self-service account-delete endpoint (with re-auth + Stripe cancel + anonymized audit), and a data-export endpoint.

**Architecture:** All new endpoints live in `login_app` (mounted at `/api/auth/`), reusing the app's `{"status","data","error"}` envelope and DRF `IsAuthenticated` (JWT). Stripe cancellation is delegated to a new `billing/services.py` helper so `login_app` never imports Stripe directly. Deletion is a hard `User.delete()` (cascade is clean — no `PROTECT` FKs). An anonymized `AccountDeletion` row is written before deletion for chargeback defense.

**Tech Stack:** Django 5.1, DRF, SimpleJWT, Stripe (via `billing/stripe_client`). Tests: Django `TestCase` + `rest_framework.test.APIClient` (`force_authenticate`), run with `python3 manage.py test`.

**Runs on branch:** `feat/settings-page` (already checked out). This is Phase 1 of PR B; Phase 2 (frontend) builds on it on the same branch. No deploy until both phases are done.

---

## Conventions (read before starting)

- Response envelope: raw `Response({"status": "success"|"error", "data": {...}|None, "error": None|str}, status=...)`. No helper function exists — match the shape exactly, and ALWAYS include all three keys (the existing PATCH error branch omits `data` — do NOT copy that bug).
- Auth: `permission_classes = [IsAuthenticated]`; `request.user` is the JWT user.
- Tests authenticate with `self.client.force_authenticate(self.user)` (not real JWTs). Create users with `User.objects.create_user(...)`.
- Run a single test module: `python3 manage.py test login_app.tests` (or `billing.tests`). Run one class: `python3 manage.py test login_app.tests.AccountDeleteTests`.
- `diet_planner` models are a package (`diet_planner/models/core.py`), NOT a single `models.py`. `DietaryGoal` is at `diet_planner/models/core.py`, importable as `from diet_planner.models import DietaryGoal` (confirm the export in `diet_planner/models/__init__.py` when you get there).

---

## File Structure

- **Modify** `login_app/views.py` — merge PATCH (Task 1); extend GET profile (Task 2); add `AccountDeleteView` (Task 4) + `DataExportView` (Task 5).
- **Modify** `login_app/models.py` — add `AccountDeletion` audit model (Task 3).
- **Create** `login_app/migrations/000X_accountdeletion.py` — via `makemigrations` (Task 3).
- **Modify** `billing/services.py` — add `cancel_subscription_for_user()` (Task 3).
- **Modify** `login_app/urls.py` — wire `account/` and `export/` routes (Task 6).
- **Modify** `llm_diet_planner_project/settings.py` — add `account_delete` throttle rate (Task 4).
- **Create** `login_app/tests.py` additions (or a new `login_app/test_settings_backend.py`) — tests per task.

---

## Task 1: Merge-PATCH for dietary_preferences (B3)

**Why:** the Settings prefs form sends only edited keys; whole-dict replace would drop the system-set `shop` key and the new `num_days`. Merge fixes the whole class.

**Files:**
- Modify: `login_app/views.py` (`UserProfileView.patch`, ~L321-344)
- Test: `login_app/tests.py` (add `ProfilePatchMergeTests`)

- [ ] **Step 1: Write the failing test**

Add to `login_app/tests.py` (create the file with `from django.test import TestCase`, `from rest_framework.test import APIClient`, `from django.contrib.auth.models import User`, `from login_app.models import UserProfile` at top if it doesn't already import them):

```python
class ProfilePatchMergeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="m1", email="m1@example.com", password="pw12345x")
        self.client.force_authenticate(self.user)

    def test_patch_merges_keys_and_preserves_existing(self):
        profile = self.user.profile
        profile.dietary_preferences = {"goal": "lose_weight", "shop": "ROHLIK"}
        profile.save(update_fields=["dietary_preferences"])
        # patch only 'goal' — 'shop' must survive
        resp = self.client.patch("/api/auth/profile/",
                                 {"dietary_preferences": {"goal": "eat_healthy"}}, format="json")
        self.assertEqual(resp.status_code, 200)
        profile.refresh_from_db()
        self.assertEqual(profile.dietary_preferences["goal"], "eat_healthy")
        self.assertEqual(profile.dietary_preferences["shop"], "ROHLIK")

    def test_patch_rejects_non_dict_prefs(self):
        resp = self.client.patch("/api/auth/profile/",
                                 {"dietary_preferences": ["not", "a", "dict"]}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["status"], "error")
        self.assertIsNone(resp.json()["data"])  # error branch must include data:None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 manage.py test login_app.tests.ProfilePatchMergeTests -v2`
Expected: `test_patch_merges_keys_and_preserves_existing` FAILS (shop dropped by whole-replace); `test_patch_rejects_non_dict_prefs` fails on the `data:None` assert (current error branch omits `data`).

- [ ] **Step 3: Implement the merge**

In `login_app/views.py`, replace the `dietary_preferences` block inside `UserProfileView.patch` with a merge, and fix the error envelope:

```python
        if 'dietary_preferences' in request.data:
            prefs = request.data['dietary_preferences']
            if not isinstance(prefs, dict):
                return Response(
                    {"status": "error", "data": None,
                     "error": "dietary_preferences must be a JSON object"},
                    status=400,
                )
            merged = dict(profile.dietary_preferences or {})
            merged.update(prefs)
            profile.dietary_preferences = merged
            update_fields.append('dietary_preferences')
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 manage.py test login_app.tests.ProfilePatchMergeTests -v2`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add login_app/views.py login_app/tests.py
git commit -m "feat(profile): merge dietary_preferences on PATCH instead of replace"
```

---

## Task 2: Extend GET profile payload (B4)

**Why:** the Settings Account section needs `primary_auth_provider` + `email_verified`; the Privacy section needs current `marketing_consent`/`consent_version` (the consent endpoint is POST-only, so the profile GET is how the toggle hydrates from the server).

**Files:**
- Modify: `login_app/views.py` (`UserProfileView.get`, ~L306-319)
- Test: `login_app/tests.py` (add `ProfileGetExtendedTests`)

- [ ] **Step 1: Write the failing test**

```python
from analytics.models import MarketingAttribution  # add to imports if absent

class ProfileGetExtendedTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="g1", email="g1@example.com", password="pw12345x")
        self.client.force_authenticate(self.user)

    def test_get_includes_provider_verified_and_consent(self):
        prof = self.user.profile
        prof.primary_auth_provider = "google"
        prof.email_verified = True
        prof.save(update_fields=["primary_auth_provider", "email_verified"])
        MarketingAttribution.objects.create(user=self.user, marketing_consent=True, consent_version="1")
        resp = self.client.get("/api/auth/profile/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(data["primary_auth_provider"], "google")
        self.assertTrue(data["email_verified"])
        self.assertTrue(data["marketing_consent"])
        self.assertEqual(data["consent_version"], "1")

    def test_get_consent_defaults_when_no_attribution(self):
        resp = self.client.get("/api/auth/profile/")
        data = resp.json()["data"]
        self.assertEqual(data["primary_auth_provider"], "email")  # model default
        self.assertFalse(data["marketing_consent"])
        self.assertEqual(data["consent_version"], "")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 manage.py test login_app.tests.ProfileGetExtendedTests -v2`
Expected: FAILS with KeyError on `primary_auth_provider` (not in payload yet).

- [ ] **Step 3: Implement**

In `login_app/views.py`, `UserProfileView.get`, add the fields to the `data` dict:

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 manage.py test login_app.tests.ProfileGetExtendedTests -v2`
Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add login_app/views.py login_app/tests.py
git commit -m "feat(profile): expose auth provider, email_verified, marketing consent"
```

---

## Task 3: AccountDeletion audit model + Stripe cancel helper

**Files:**
- Modify: `login_app/models.py` (add `AccountDeletion`)
- Create: migration via `makemigrations login_app`
- Modify: `billing/services.py` (add `cancel_subscription_for_user`)
- Test: `billing/tests.py` (add `CancelSubscriptionHelperTests`)

- [ ] **Step 1: Add the audit model**

Append to `login_app/models.py`:

```python
class AccountDeletion(models.Model):
    """Anonymized record of a self-service account deletion (chargeback defense).
    Deliberately holds NO PII — only the Stripe customer id, tier, provider, timestamp."""
    deleted_at = models.DateTimeField(auto_now_add=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    tier = models.CharField(max_length=20, blank=True, default="")
    auth_provider = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        verbose_name = "Account Deletion"
        verbose_name_plural = "Account Deletions"

    def __str__(self):
        return f"AccountDeletion {self.deleted_at:%Y-%m-%d} ({self.tier or 'free'})"
```

- [ ] **Step 2: Make the migration**

Run: `python3 manage.py makemigrations login_app`
Expected: creates `login_app/migrations/000X_accountdeletion.py` (one CreateModel). Verify it exists.

- [ ] **Step 3: Write the failing helper test**

Add to `billing/tests.py` (top imports: `from unittest.mock import patch, MagicMock`, `from django.test import TestCase`, `from django.contrib.auth.models import User`, `from billing.models import Subscription`):

```python
class CancelSubscriptionHelperTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="d1", email="d1@example.com", password="pw12345x")

    def test_noop_when_no_subscription(self):
        from billing.services import cancel_subscription_for_user
        # must not raise, must not call stripe
        cancel_subscription_for_user(self.user)  # no subscription exists

    @patch("billing.services.is_configured", return_value=True)
    @patch("billing.services.stripe")
    def test_cancels_active_subscription(self, mock_stripe, _cfg):
        Subscription.objects.create(user=self.user, tier="standard", status="active",
                                    stripe_customer_id="cus_x", stripe_subscription_id="sub_x")
        from billing.services import cancel_subscription_for_user
        cancel_subscription_for_user(self.user)
        mock_stripe.Subscription.cancel.assert_called_once_with("sub_x")

    @patch("billing.services.is_configured", return_value=True)
    @patch("billing.services.stripe")
    def test_idempotent_on_already_canceled(self, mock_stripe, _cfg):
        import stripe as real_stripe
        mock_stripe.error = real_stripe.error
        mock_stripe.Subscription.cancel.side_effect = real_stripe.error.InvalidRequestError("No such subscription", param=None)
        Subscription.objects.create(user=self.user, tier="standard", status="active",
                                    stripe_customer_id="cus_x", stripe_subscription_id="sub_gone")
        from billing.services import cancel_subscription_for_user
        cancel_subscription_for_user(self.user)  # must NOT raise
```

- [ ] **Step 4: Run to verify it fails**

Run: `python3 manage.py test billing.tests.CancelSubscriptionHelperTests -v2`
Expected: FAILS — `cancel_subscription_for_user` does not exist (ImportError).

- [ ] **Step 5: Implement the helper**

Add to `billing/services.py` (confirm the file already has `from .stripe_client import stripe, is_configured` near the top; if it imports only `stripe`, add `is_configured`):

```python
def cancel_subscription_for_user(user) -> None:
    """Immediately cancel the user's Stripe subscription, if any.

    Idempotent: an already-canceled / missing subscription is treated as success.
    Does NOT delete the Stripe customer (Czech invoice/VAT retention; GDPR 17(3)(b)).
    Raises on a genuine (non-idempotent) StripeError so the caller can abort deletion.
    """
    sub = Subscription.objects.filter(user=user).first()
    if not sub or not sub.stripe_subscription_id:
        return
    if not is_configured():
        return
    try:
        stripe.Subscription.cancel(sub.stripe_subscription_id)
    except stripe.error.InvalidRequestError:
        # Already canceled or no longer exists — idempotent success.
        return
```

(Let any other `stripe.error.StripeError` propagate — the delete view catches it and aborts.)

- [ ] **Step 6: Run to verify it passes**

Run: `python3 manage.py test billing.tests.CancelSubscriptionHelperTests -v2`
Expected: all three PASS.

- [ ] **Step 7: Commit**

```bash
git add login_app/models.py login_app/migrations/ billing/services.py billing/tests.py
git commit -m "feat(billing): AccountDeletion audit model + idempotent cancel helper"
```

---

## Task 4: Account-delete endpoint (B1)

**Files:**
- Modify: `login_app/views.py` (add `AccountDeleteView`)
- Modify: `llm_diet_planner_project/settings.py` (add `account_delete` throttle rate)
- Test: `login_app/tests.py` (add `AccountDeleteTests`)

- [ ] **Step 1: Add the throttle rate**

In `llm_diet_planner_project/settings.py`, inside `REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']`, add:

```python
        'account_delete': '5/hour',
```

- [ ] **Step 2: Write the failing tests**

Add to `login_app/tests.py` (imports: `from unittest.mock import patch`):

```python
class AccountDeleteTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="del1", email="del1@example.com", password="rightpw123")
        self.client.force_authenticate(self.user)

    def _url(self):
        return "/api/auth/account/"

    @patch("login_app.views.cancel_subscription_for_user")
    def test_email_user_wrong_password_rejected(self, mock_cancel):
        resp = self.client.delete(self._url(), {"password": "WRONG"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        mock_cancel.assert_not_called()

    @patch("login_app.views.cancel_subscription_for_user")
    def test_email_user_correct_password_deletes(self, mock_cancel):
        uid = self.user.pk
        resp = self.client.delete(self._url(), {"password": "rightpw123"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(pk=uid).exists())
        mock_cancel.assert_called_once()

    @patch("login_app.views.cancel_subscription_for_user")
    def test_deletion_writes_anonymized_audit_row(self, mock_cancel):
        from login_app.models import AccountDeletion
        self.client.delete(self._url(), {"password": "rightpw123"}, format="json")
        self.assertEqual(AccountDeletion.objects.count(), 1)
        rec = AccountDeletion.objects.first()
        self.assertEqual(rec.auth_provider, "email")

    @patch("login_app.views.cancel_subscription_for_user", side_effect=__import__("stripe").error.APIConnectionError("boom"))
    def test_stripe_failure_aborts_delete(self, mock_cancel):
        uid = self.user.pk
        resp = self.client.delete(self._url(), {"password": "rightpw123"}, format="json")
        self.assertEqual(resp.status_code, 502)
        self.assertTrue(User.objects.filter(pk=uid).exists())  # NOT deleted

    @patch("login_app.views.requests.get")
    @patch("login_app.views.cancel_subscription_for_user")
    def test_google_user_requires_matching_token(self, mock_cancel, mock_get):
        self.user.profile.primary_auth_provider = "google"
        self.user.profile.save(update_fields=["primary_auth_provider"])
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"email": "del1@example.com"}
        uid = self.user.pk
        resp = self.client.delete(self._url(), {"google_access_token": "tok"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(User.objects.filter(pk=uid).exists())

    @patch("login_app.views.requests.get")
    @patch("login_app.views.cancel_subscription_for_user")
    def test_google_user_wrong_email_rejected(self, mock_cancel, mock_get):
        self.user.profile.primary_auth_provider = "google"
        self.user.profile.save(update_fields=["primary_auth_provider"])
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"email": "someone-else@example.com"}
        resp = self.client.delete(self._url(), {"google_access_token": "tok"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
```

- [ ] **Step 3: Run to verify it fails**

Run: `python3 manage.py test login_app.tests.AccountDeleteTests -v2`
Expected: FAILS (404/405 — route + view don't exist yet).

- [ ] **Step 4: Implement `AccountDeleteView`**

In `login_app/views.py`, add near the other views (and add imports at top: `from rest_framework.throttling import ScopedRateThrottle`, and `from billing.services import cancel_subscription_for_user`; `requests` and `Subscription` — import `Subscription` lazily inside the method to avoid a hard billing import at module load: `from billing.models import Subscription`):

```python
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

        # 4. Anonymized audit row, then hard delete (cascade handles dependents).
        from .models import AccountDeletion
        AccountDeletion.objects.create(
            stripe_customer_id=customer_id or '', tier=tier or '',
            auth_provider=profile.primary_auth_provider,
        )
        user.delete()
        return Response({"status": "success", "data": {"deleted": True}, "error": None})
```

- [ ] **Step 5: Run to verify it passes**

Wire the route first (needed for the tests to hit it): temporarily jump to Task 6 Step 1 to add the `account/` path, then:
Run: `python3 manage.py test login_app.tests.AccountDeleteTests -v2`
Expected: all six PASS.

- [ ] **Step 6: Commit**

```bash
git add login_app/views.py llm_diet_planner_project/settings.py login_app/tests.py login_app/urls.py
git commit -m "feat(auth): self-service account delete (re-auth, Stripe cancel, audit)"
```

---

## Task 5: Data-export endpoint (B2)

**Files:**
- Modify: `login_app/views.py` (add `DataExportView`)
- Test: `login_app/tests.py` (add `DataExportTests`)

- [ ] **Step 1: Write the failing tests**

```python
class DataExportTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="e1", email="e1@example.com", password="pw12345x")
        self.other = User.objects.create_user(username="e2", email="e2@example.com", password="pw12345x")

    def test_requires_auth(self):
        resp = self.client.get("/api/auth/export/")
        self.assertIn(resp.status_code, (401, 403))

    def test_exports_only_own_data_as_attachment(self):
        self.client.force_authenticate(self.user)
        prof = self.user.profile
        prof.dietary_preferences = {"goal": "lose_weight"}
        prof.save(update_fields=["dietary_preferences"])
        resp = self.client.get("/api/auth/export/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("attachment", resp["Content-Disposition"])
        import json
        body = json.loads(resp.content)
        self.assertEqual(body["account"]["email"], "e1@example.com")
        self.assertEqual(body["preferences"]["goal"], "lose_weight")
        # must not leak the other user
        self.assertNotIn("e2@example.com", resp.content.decode())
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 manage.py test login_app.tests.DataExportTests -v2`
Expected: FAILS (404 — route/view absent).

- [ ] **Step 3: Implement `DataExportView`**

In `login_app/views.py` (add import at top: `from django.http import JsonResponse`, `from django.core.serializers.json import DjangoJSONEncoder`):

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `python3 manage.py test login_app.tests.DataExportTests -v2`
Expected: all PASS. (If `DietaryGoal` import path differs, check `diet_planner/models/__init__.py` for the actual export and adjust the import.)

- [ ] **Step 5: Commit**

```bash
git add login_app/views.py login_app/tests.py
git commit -m "feat(auth): self-service JSON data export endpoint"
```

---

## Task 6: URL wiring + full verification

**Files:**
- Modify: `login_app/urls.py`

- [ ] **Step 1: Wire the routes** (do this during Task 4 Step 5 if not already)

In `login_app/urls.py`, add BEFORE the `path('', include('dj_rest_auth.urls'))` line:

```python
    path('account/', views.AccountDeleteView.as_view(), name='account-delete'),
    path('export/', views.DataExportView.as_view(), name='data-export'),
```

- [ ] **Step 2: Run the full affected suites**

Run: `python3 manage.py test login_app billing analytics -v1`
Expected: all green, including the new `ProfilePatchMergeTests`, `ProfileGetExtendedTests`, `AccountDeleteTests`, `DataExportTests`, `CancelSubscriptionHelperTests`, and every pre-existing test in those apps (no regressions).

- [ ] **Step 3: Migration check**

Run: `python3 manage.py makemigrations --check --dry-run`
Expected: "No changes detected" (the `AccountDeletion` migration from Task 3 already exists and models match).

- [ ] **Step 4: Commit any remaining wiring**

```bash
git add login_app/urls.py
git commit -m "chore(auth): wire account-delete and export routes"
```

---

## Self-Review

- **Spec coverage:** implements B1 (delete — re-auth email+google, Stripe cancel idempotent + don't-delete-customer, anonymized audit, abort-on-stripe-error, rate limit), B2 (export, auth-isolated, blob attachment), B3 (PATCH merge), B4 (profile extension incl. consent). Cascade confirmed clean (Task context). Webhook-200-on-unknown-customer check is NOT in this plan — it's a separate verification note carried to the deploy checklist (we don't delete the customer, which sharply lowers that risk).
- **Placeholder scan:** every code + test step is complete; every run step has an exact command + expected result. No TBD.
- **Type/name consistency:** `cancel_subscription_for_user` defined in Task 3, imported/patched by that exact name in Tasks 4; `AccountDeletion` fields (`stripe_customer_id`, `tier`, `auth_provider`, `deleted_at`) consistent across model, migration, view, and test; envelope keys uniform.
- **Ambiguity:** `DietaryGoal` import path flagged (package, not `models.py`) with a fallback instruction; `Subscription`/`billing` imported lazily inside methods to avoid module-load coupling.
