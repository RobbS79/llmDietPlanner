# Shopify Subscription Integration Plan — LLM Diet Planner

**Status:** Draft for founder execution · **Date:** 2026-06-02 · **Author:** Digital Product Engineering

Goal: take the app from "one-time per-goal Shopify checkout (partially wired, not mounted)" to **selling monthly recurring subscriptions through Shopify**, with a verified, repeatable "first paying customer" journey.

> Scope note: this is a plan + test design only. No application code or migrations are written here.

---

## 1. Goal & success metric

**North-star acceptance journey (must be provable end-to-end):**

> Customer scans a QR / taps an Instastory link → lands on `/pricing` (UTM/QR source captured) → picks Standard (99 CZK) or Premium (199 CZK) → pays on Shopify (recurring) → Shopify webhook provisions a **user-level subscription entitlement** in Django → user lands back in app → completes onboarding quiz → generates first meal plan (entitlement gate passes) → receives a welcome/confirmation email.

**Primary success metric:** **First paying customer activated** = a real `Subscription` row with `status=active`, `tier in {standard, premium}`, a non-null `current_period_end`, AND ≥1 `DietaryGoal` reaching `status=completed` for that user, AND a welcome email recorded as sent.

**Activation funnel to instrument (P2):**
`landing_view → pricing_view → checkout_started → checkout_paid (webhook) → onboarding_completed → first_plan_completed`, each segmentable by `attribution.source` (instastory / qr / organic).

---

## 2. Architecture decision

### 2.1 The core shift: per-goal payment → user-level entitlement

Today "paid" is encoded per `DietaryGoal` (`is_free_generation`, `shopify_order_id`, `payment_confirmed_at`, statuses `AWAITING_PAYMENT`/`PAYMENT_PENDING`). The `order-paid` webhook extracts `goal_id` from order attributes and flips one goal. That model cannot express "this user may generate N plans this month because they pay 199 CZK/mo."

**New concept:** a **user-level, time-bounded entitlement** (`Subscription`) that meal-plan generation checks. Free tier stays as the existing `UserProfile.free_generations_remaining` counter. Generation gate becomes:

```
allow_generation(user) =
    active_subscription(user) AND within_tier_quota(user)   # paid path
    OR profile.has_free_generations()                       # free path (unchanged)
```

> ⚠️ **Current gate is permissive.** In `diet_planner/views.py` (~L90–142) the create flow only *reads* `has_free_generations()` to set `is_free_generation` and decrements it, but **never blocks** when credits are exhausted. There is no paywall today. Part of this work (P0-7) is to add real enforcement: no free credits AND no active entitlement ⇒ reject with a 402-style response that the frontend turns into a redirect to `/pricing`.

### 2.2 Subscription mechanism recommendation (Shopify side)

Shopify's Storefront **cart/checkout does not do native recurring billing** by itself. The current `shopify_service.py` builds one-time Storefront carts — that path **cannot** charge monthly. Recurring billing requires either:

| Option | What it is | Effort for solo founder | Trade-offs |
|---|---|---|---|
| **A. Subscription app (Appstle / Seal / Recharge / Awtomic)** ✅ **RECOMMENDED for P0** | Installed Shopify app that creates **selling plans**, manages **subscription contracts**, runs the dunning/billing engine, and emits webhooks. You attach a selling plan to your two products. | **S–M.** No subscription-billing code to own. Ship in days. | Monthly app fee + possible % of revenue. Must pick one that **supports CZK + Czech payment rails** and exposes contract/billing webhooks. **Verify** Czech-merchant availability per app. |
| **B. Custom/public app using Shopify Subscription APIs** (`SellingPlanGroup`, `SubscriptionContract`, `SubscriptionBillingAttempt`) | You build selling-plan groups and own contract creation/billing via Admin GraphQL with scopes `write_own_subscription_contracts`, `read_own_subscription_contracts`, `write_products`. | **L.** You own dunning, retries, payment-method vaulting edge cases. | Maximum control, no app fee, but materially more code + Shopify review. Wrong choice for "first paying customer fast." |
| C. Shopify Plus "Selling Plans" native UI only | Plus-only conveniences. | n/a | Plus pricing not justified at this stage. |

**Decision: Option A for P0** (subscription app provides the billing engine + webhooks), keep **Option B as a documented fallback** if no app meets the CZK requirement. Either way, Django remains the **system of record for entitlement** and reacts to webhooks; it never runs the billing clock itself.

**CZK / Czech payment considerations (verify before committing to an app):**
- Store currency must be **CZK**; products priced 99 / 199 CZK.
- Payment methods: card (Visa/Mastercard), **Apple Pay / Google Pay**, ideally a Czech-friendly gateway. Shopify Payments availability for CZ + the chosen subscription app's gateway support is the gating constraint — **verify**.
- VAT/invoicing: recurring B2C invoices with Czech VAT — likely needs a Shopify invoicing app or the subscription app's invoice feature. **Open question for founder (§6).**

**Webhooks required by path (register to `/api/shopifyin/webhooks/...`):**

| Event | Path A (subscription app) | Path B (custom) | Django action |
|---|---|---|---|
| First payment / signup | `orders/paid` (initial order) | `orders/paid` | Create/activate `Subscription`, set `current_period_end`, send welcome email |
| Contract created | app-specific or `subscription_contracts/create` | `subscription_contracts/create` | Link `shopify_contract_id` to `Subscription` |
| Renewal success | `orders/paid` (recurring) and/or `subscription_billing_attempts/success` | `subscription_billing_attempts/success` | Extend `current_period_end`, reset monthly quota |
| Renewal failure | `subscription_billing_attempts/failure` | `subscription_billing_attempts/failure` | Mark `past_due`; after grace, `expired` |
| Cancellation | app-specific / `subscription_contracts/update` | `subscription_contracts/update` | Set `cancel_at_period_end` or `canceled` |
| App removed | `app/uninstalled` | `app/uninstalled` | Flag store inactive, alert founder |

> Several exact topic names depend on the chosen app — items marked here and in §6 must be **verified against the app's docs** once selected.

### 2.3 New entitlement data model

Add to `shopifyin/models.py` (new app config not needed; reuse `shopifyin`). All money/identifier fields below are proposals.

**`SubscriptionPlan`** — backend source of truth for the tiers (replaces hardcoded `PLANS` in `Pricing.tsx`):
- `tier` (`TextChoices`: `STANDARD`, `PREMIUM`)
- `name`, `description`
- `price_czk` (Decimal), `currency` (default `CZK`)
- `shopify_variant_id` (the variant the selling plan is attached to) — replaces manual `ShopifyStore.meal_plan_variant_id`
- `shopify_selling_plan_id` (nullable; from app/API) — **verify naming per path**
- `monthly_plan_quota` (int — e.g. Standard 7, Premium 30, per Pricing copy), `edits_per_plan` (int), `allow_multi_store` (bool — gates `store_mode != single`)
- `is_active` (bool), timestamps

**`Subscription`** — the user-level entitlement (the heart of the shift):
- `user` (FK→User, `related_name='subscription'`; effectively one active per user)
- `plan` (FK→SubscriptionPlan)
- `tier` (denormalized for fast gating)
- `status` (`TextChoices`: `INCOMPLETE`, `ACTIVE`, `PAST_DUE`, `CANCELED`, `EXPIRED`)
- `shopify_contract_id` (CharField, unique-nullable), `shopify_customer_id`, `shopify_order_id` (initial order)
- `current_period_start`, `current_period_end` (DateTime — the time bound the gate checks)
- `cancel_at_period_end` (bool)
- `plans_generated_this_period` (int — monthly quota counter; reset on renewal)
- `attribution` (JSONField — `{source, medium, campaign, qr_id}` threaded from landing; see §4)
- timestamps; `Meta.indexes` on `(user, status)` and `(status, current_period_end)`

**`SubscriptionEvent`** — append-only audit / idempotency log of webhooks processed:
- `subscription` (FK, nullable until linked), `event_type`, `shopify_event_id` (unique — idempotency key), `payload` (JSON), `created_at`

**Helper methods on `Subscription`:** `is_entitled()` (`status==ACTIVE and current_period_end > now`), `within_quota()` (`plans_generated_this_period < plan.monthly_plan_quota`), `consume_quota()`, `renew(period_end)`, `cancel(at_period_end: bool)`.

**Free vs paid coexistence:** the free counter on `UserProfile` is untouched. Gate prefers paid entitlement; if none, falls back to free credits. A user who subscribes does **not** lose remaining free credits (no migration of free credits needed).

### 2.4 Reuse vs replace table for existing `shopifyin` code

| Existing artifact | Verdict | Notes |
|---|---|---|
| `ShopifyStore` model (encrypted tokens, `webhook_secret`, `admin_api_*`) | **REUSE** | Already holds encrypted admin token + webhook secret needed for subscription/Admin API + HMAC. |
| `ShopifyStore.meal_plan_variant_id` | **DEPRECATE** | Superseded by per-tier `SubscriptionPlan.shopify_variant_id`. Keep column for back-compat, stop using. |
| `verify_shopify_webhook()` (HMAC-SHA256, base64, `compare_digest`) in `webhooks.py` | **REUSE as-is** | Correct and timing-safe. Extract into a shared util so all new webhook handlers call it. |
| `shopify_order_paid_webhook` (goal_id extraction → flips one DietaryGoal) | **REPLACE / REPURPOSE** | New `orders/paid` handler must provision/renew the **user-level `Subscription`**, not a single goal. Add idempotency via `SubscriptionEvent.shopify_event_id` (header `X-Shopify-Webhook-Id`) in addition to existing `select_for_update`. |
| `shopify_order_cancelled_webhook` | **REPLACE** | Cancellation now operates on subscription lifecycle, not goal status. |
| `shopify_service.py` Storefront cart/checkout create | **REUSE for redirect-to-checkout only** | Still used to build the cart that carries the **selling plan**; remove reliance on it for "is the user paid." **Verify** the GraphQL cart mutation accepts `sellingPlanId` on the line item (Storefront API `cartLinesAdd` supports `sellingPlanId`). |
| `ShopifyCheckout` model + create/status/list views | **REUSE (reduced role)** | Keep as a record of checkout sessions + attribution capture; it is **no longer** the entitlement source of truth. |
| `ShopifyProduct` cache model + product views | **REUSE (optional)** | Fine for admin/debug; not on the critical path. |
| `ShopifyTestConnectionView`, `ShopifyDebugView` | **REUSE** | Extend `test/` to also verify selling-plan + subscription webhook config. |
| `diet_planner` payment fields on `DietaryGoal` (`is_free_generation`, `shopify_*`, `payment_confirmed_at`, payment statuses) | **KEEP, REDUCED** | Still useful for free-vs-paid provenance per plan; `is_free_generation` stays meaningful. The per-goal `AWAITING_PAYMENT`/`PAYMENT_PENDING` flow is no longer the gate. `PAYMENT_CONFIRMED` (currently unused) can be retired or repurposed. |
| **`shopifyin/urls.py` not mounted in root urlconf** | **FIX — BLOCKER** | `llm_diet_planner_project/urls.py` includes `login_app.urls` and `diet_planner.urls` only; `shopifyin.urls` is **never included**, so checkout + webhook endpoints are currently unreachable. Must `path("api/shopifyin/", include("shopifyin.urls"))`. This alone blocks any payment flow. |
| `UserProfile.free_generations_remaining` / `has_free_generations` / `use_free_generation` | **REUSE unchanged** | Free tier mechanics. |
| `UserProfile.onboarding_completed` / `dietary_preferences` + `UserProfileView` GET/PATCH (`/api/auth/profile/`) | **REUSE** | Onboarding endpoint already exists and is wired into the frontend (`App.tsx` redirects to `/onboarding`). No new endpoint needed — just ensure post-payment routing lands users here. |
| `login_app/tasks.py` email tasks + `EmailMultiAlternatives` + `utils.get_*_email_content` | **REUSE pattern** | Add a `send_welcome_email_task` mirroring `send_password_reset_email_task`; email infra (Celery + SMTP via `EMAIL_*` env, console backend in dev) is already configured in `settings.py` (L302–309). |

---

## 3. Sequenced action steps

Effort: **S** ≈ ≤0.5d, **M** ≈ 0.5–2d, **L** ≈ >2d.

### Phase P0 — Minimum path to first paying customer

| # | Step | Files / modules | Effort | Depends on |
|---|---|---|---|---|
| P0-1 | **Mount shopifyin URLs** under `/api/shopifyin/`. Verify checkout + webhook endpoints resolve. | `llm_diet_planner_project/urls.py` | **S** | — |
| P0-2 | **Choose subscription app** (Option A) supporting CZK + Czech payments; install on the store; create selling plans for the two products (99/199 CZK monthly). Record variant + selling-plan IDs. | Shopify admin (no code) | **M** | — |
| P0-3 | **Add `SubscriptionPlan`, `Subscription`, `SubscriptionEvent` models** + migration; admin registration. Seed two `SubscriptionPlan` rows with quotas/edits from `Pricing.tsx`. | `shopifyin/models.py`, `shopifyin/admin.py`, new migration | **M** | P0-2 |
| P0-4 | **Pricing tiers API**: `GET /api/shopifyin/plans/` returns active `SubscriptionPlan`s (tier, price, features). Replaces hardcoded `PLANS`. | `shopifyin/views.py`, `serializers.py`, `urls.py` | **S** | P0-3 |
| P0-5 | **Checkout-initiation endpoint** `POST /api/shopifyin/subscribe/` `{tier, attribution}` → builds a Storefront cart line carrying the tier's `shopify_variant_id` + `sellingPlanId` + note_attributes (`user_id`, `tier`, attribution) → returns `checkout_url`. Persist a `ShopifyCheckout` with metadata. | `shopifyin/views.py`, `shopify_service.py` (add selling-plan support), `serializers.py`, `urls.py` | **M** | P0-3, P0-2 |
| P0-6 | **Wire Pricing → checkout** in frontend: tier buttons call `/subscribe/` (auth-gated; unauth users sent to `/login?next=/pricing&tier=…`), then `window.location = checkout_url`. Read tiers/prices from P0-4. | `frontend/src/pages/Pricing.tsx`, api client | **M** | P0-4, P0-5 |
| P0-7 | **`orders/paid` webhook → provision Subscription.** New handler: HMAC verify (reuse `verify_shopify_webhook`), idempotency via `SubscriptionEvent.shopify_event_id`, map order → user (by `note_attributes.user_id`, fallback email), create/activate `Subscription` (`ACTIVE`, set `current_period_end` ≈ +1 month — **verify** exact period from contract/app payload), persist attribution, fire `send_welcome_email_task.delay()`. | `shopifyin/webhooks.py`, `shopifyin/services/subscription.py` (new), `shopifyin/urls.py` | **L** | P0-3 |
| P0-8 | **Entitlement gate on generation.** Add `allow_generation(user)` helper; enforce in create flow: paid+in-quota OR free credits, else **402-style reject** with `{redirect: '/pricing'}`. Increment `plans_generated_this_period` on paid generation. | `diet_planner/views.py` (~L90–142), `shopifyin/services/subscription.py` | **M** | P0-3, P0-7 |
| P0-9 | **Welcome/confirmation email.** Add `send_welcome_email_task` + `get_welcome_email_content` (CZ copy, EN gloss for founder). Sent on first activation. | `login_app/tasks.py`, `login_app/utils.py` | **S** | P0-7 |
| P0-10 | **Post-payment return routing.** Shopify thank-you/return URL → app route that confirms subscription, then routes to `/onboarding` (existing) → first plan. | `frontend` (return/success route), Shopify checkout settings | **M** | P0-6, P0-7 |
| P0-11 | **Register webhooks in Shopify** (manual or via Admin API) pointing at the mounted endpoints; store `webhook_secret` on `ShopifyStore`. | Shopify admin / one-off mgmt command | **S** | P0-1, P0-7 |
| P0-12 | **First-paying-customer smoke test** (real Shopify test/sandbox order) — see §5 checklist. | manual + Playwright | **M** | all P0 |

### Phase P1 — Lifecycle: renewals, cancellation, failures

| # | Step | Files | Effort | Depends |
|---|---|---|---|---|
| P1-1 | **Renewal webhook** (`subscription_billing_attempts/success` and/or recurring `orders/paid`): extend `current_period_end`, reset `plans_generated_this_period`. | `shopifyin/webhooks.py`, services | **M** | P0-7 |
| P1-2 | **Payment-failure webhook** (`subscription_billing_attempts/failure`): `PAST_DUE`, grace window, then `EXPIRED`; optional dunning email. | `shopifyin/webhooks.py`, `login_app/tasks.py` | **M** | P0-7 |
| P1-3 | **Cancellation** (`subscription_contracts/update` / app event + in-app "cancel" calling Admin API): `cancel_at_period_end` then `CANCELED`; entitlement persists until `current_period_end`. | `shopifyin/webhooks.py`, `views.py` | **M** | P0-7 |
| P1-4 | **Expiry sweep** Celery Beat task: nightly set `ACTIVE→EXPIRED` where `current_period_end < now` (safety net vs missed webhooks). | `shopifyin/tasks.py`, `settings.py` `CELERY_BEAT_SCHEDULE` | **S** | P0-7 |
| P1-5 | **`app/uninstalled`** handler: flag store inactive, alert founder. | `shopifyin/webhooks.py` | **S** | P0-1 |
| P1-6 | **Billing/account UI**: show tier, renewal date, quota used, cancel button. | `frontend` (account page) | **M** | P1-3 |

### Phase P2 — Attribution analytics & polish

| # | Step | Files | Effort | Depends |
|---|---|---|---|---|
| P2-1 | **Capture attribution at landing** (UTM + `qr` param) → cookie/localStorage; thread into `/subscribe/` and onto `Subscription.attribution`. | `frontend` (landing + api), P0-5/P0-7 | **M** | P0-7 |
| P2-2 | **Conversion reporting**: admin view / mgmt command counting funnel by `attribution.source`. | `shopifyin/admin.py` or mgmt command | **M** | P2-1 |
| P2-3 | **QR generation**: stable `qr_id` per printed batch mapping to campaign. | mgmt command / docs | **S** | P2-1 |
| P2-4 | **Resilience polish**: webhook retry/DLQ logging, refund/`orders/refunded` handling, invoice/VAT follow-up. | `shopifyin/webhooks.py` | **M** | P1 |

---

## 4. Attribution / analytics

**Capture (landing):** Instastory links and QR codes carry `?utm_source=instagram&utm_medium=story&utm_campaign=<x>&qr=<batch_id>`. On first landing, frontend parses `window.location.search`, stores `{source, medium, campaign, qr_id, landed_at}` in a first-party cookie/localStorage (GDPR: see §6).

**Thread-through:**
1. `/subscribe/` request body includes the stored `attribution` object → persisted on the `ShopifyCheckout.metadata` **and** echoed into Shopify cart `note_attributes` (so it survives the Shopify round-trip even if the session is lost).
2. `orders/paid` webhook reads attribution from `note_attributes` (authoritative) or matches back the `ShopifyCheckout` by `user_id`/order, and writes it to **`Subscription.attribution`**.

**Result:** every paid subscription carries its acquisition source, making "Instastory conversion" measurable as `count(Subscription where attribution.source='instagram') / pricing_views[source=instagram]`. QR batches are distinguishable via `qr_id`.

---

## 5. Test plan

Backend tests use Django `TestCase` / DRF `APIClient`; **place subscription tests in `shopifyin/tests.py` (currently an empty stub)** — split into a `shopifyin/tests/` package as it grows. E2E uses the existing Playwright harness in `/opt/llmDietPlanner/e2e/` (config `e2e/playwright.config.ts`, tests in `e2e/tests/`, helpers in `e2e/helpers/`).

### 5.1 Unit tests — `shopifyin/tests/test_models.py`, `test_gating.py`

- **Entitlement model:** `Subscription.is_entitled()` true when `ACTIVE` and `current_period_end>now`; false when expired/canceled/past_due-after-grace.
- **Quota:** `within_quota()` boundary at `plan.monthly_plan_quota`; `consume_quota()` increments; renewal resets to 0.
- **State transitions:** `INCOMPLETE→ACTIVE→PAST_DUE→ACTIVE` (recovery), `ACTIVE→CANCELED (cancel_at_period_end)→EXPIRED`, illegal transitions rejected.
- **Tier gating / feature flags:** Premium ⇒ `allow_multi_store True` (permits `store_mode != single`); Standard ⇒ blocked.
- **HMAC verify:** `verify_shopify_webhook` accepts a correctly base64-HMAC-SHA256-signed body, rejects tampered body / wrong secret / missing header.
- **Idempotency:** processing the same `shopify_event_id` twice creates exactly one `SubscriptionEvent` and applies the effect once.

### 5.2 Integration tests — `shopifyin/tests/test_webhooks.py`, `test_subscribe_flow.py`

- **Pricing→checkout:** `POST /api/shopifyin/subscribe/` (authed) with `{tier:'standard'}` returns a `checkout_url` and creates a `ShopifyCheckout` with attribution metadata; unauth → 401/redirect.
- **`orders/paid` create:** POST a fixture order payload with valid HMAC → `Subscription` created `ACTIVE`, `current_period_end` set, `plans_generated_this_period=0`, attribution persisted, **welcome email in `mail.outbox`** (assert subject/recipient).
- **Invalid HMAC:** same payload, wrong signature → `401`, **no** `Subscription` created.
- **Renewal:** billing-success payload → `current_period_end` extended, quota counter reset.
- **Cancel:** cancellation payload → `cancel_at_period_end=True`, entitlement still valid until period end; after expiry sweep → `EXPIRED`, gate denies.
- **Payment failure:** failure payload → `PAST_DUE`; after grace → `EXPIRED`.
- **Gate enforcement:** authed user, no free credits, no active sub → plan-create returns 402-style `{redirect:'/pricing'}`; with active sub in-quota → 201 and quota increments; quota-exhausted paid user → 402.

### 5.3 End-to-end journey test — `e2e/tests/subscription.spec.ts`

Playwright drives the real frontend. **Shopify is stubbed** for CI (the actual hosted Shopify checkout cannot run headless deterministically): intercept `/api/shopifyin/subscribe/` to return a fake `checkout_url`, then **simulate the paid webhook** by POSTing a signed fixture to `/api/shopifyin/webhooks/orders-paid/` (server-side step in the test setup) to provision the subscription, then continue the in-app journey. A separate **manual/sandbox** run exercises the real Shopify checkout.

E2E flow:
1. Visit `/pricing?utm_source=instagram&utm_medium=story&qr=batchA`; assert tiers/prices render from API.
2. Click "Vybrat Standard" → (unauth) redirected to login; register/login.
3. Back on pricing → click tier → assert redirect to (stubbed) checkout URL.
4. Test harness fires signed `orders/paid` webhook for that user.
5. App return route → assert routed to `/onboarding`; complete quiz (PATCH `/api/auth/profile/`).
6. Create first plan → assert it is **allowed** (entitlement gate passes) and reaches `completed` (LLM/Celery stubbed per existing `e2e/helpers/mocks.ts`).
7. Assert subscription visible in account UI; assert `attribution.source='instagram'` recorded (via API/admin assertion).

**"First paying customer" smoke checklist (run once against real Shopify sandbox before launch):**
- [ ] Store currency = CZK; Standard 99 / Premium 199 selling plans live & published to Storefront.
- [ ] Webhooks registered to mounted `/api/shopifyin/webhooks/...`; `webhook_secret` stored; HMAC verifies on a real delivery.
- [ ] Real test card (Apple/Google Pay if enabled) completes recurring checkout.
- [ ] `Subscription` row appears `ACTIVE` with correct tier + `current_period_end`.
- [ ] Welcome email received (real SMTP, not console backend).
- [ ] Onboarding completes; first meal plan generates and reaches `completed`.
- [ ] Attribution source recorded on the subscription.
- [ ] Cancel from Shopify/app → entitlement persists to period end, then `EXPIRED`.

### 5.4 Example test skeletons (real names/paths)

```python
# shopifyin/tests/test_gating.py
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from shopifyin.models import Subscription, SubscriptionPlan
from login_app.models import UserProfile

class EntitlementGateTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("payer", "payer@example.com", "pw")
        self.plan = SubscriptionPlan.objects.create(
            tier=SubscriptionPlan.Tier.STANDARD, name="Standard",
            price_czk="99.00", monthly_plan_quota=7, edits_per_plan=10,
            allow_multi_store=False, is_active=True,
        )

    def test_active_subscription_is_entitled_and_within_quota(self):
        sub = Subscription.objects.create(
            user=self.user, plan=self.plan, tier=self.plan.tier,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30),
            plans_generated_this_period=0,
        )
        self.assertTrue(sub.is_entitled())
        self.assertTrue(sub.within_quota())

    def test_expired_subscription_falls_back_to_free_credits(self):
        Subscription.objects.create(
            user=self.user, plan=self.plan, tier=self.plan.tier,
            status=Subscription.Status.ACTIVE,
            current_period_start=timezone.now() - timedelta(days=40),
            current_period_end=timezone.now() - timedelta(days=10),
        )
        profile = UserProfile.objects.get(user=self.user)  # auto-created by signal
        self.assertTrue(profile.has_free_generations())     # free path still open
```

```python
# shopifyin/tests/test_webhooks.py
import json, hmac, hashlib, base64
from django.test import TestCase, Client
from django.core import mail
from django.contrib.auth.models import User
from shopifyin.models import ShopifyStore, Subscription, SubscriptionPlan

class OrdersPaidWebhookTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.secret = "whsec_test"
        self.store = ShopifyStore.objects.create(
            name="MealPrep", store_domain="mealprep-9693.myshopify.com",
            storefront_access_token="sf", webhook_secret=self.secret, is_active=True,
        )
        self.user = User.objects.create_user("buyer", "buyer@example.com", "pw")
        self.plan = SubscriptionPlan.objects.create(
            tier=SubscriptionPlan.Tier.PREMIUM, name="Premium",
            price_czk="199.00", monthly_plan_quota=30, edits_per_plan=5,
            allow_multi_store=True, is_active=True,
        )

    def _sign(self, body: bytes) -> str:
        return base64.b64encode(
            hmac.new(self.secret.encode(), body, hashlib.sha256).digest()
        ).decode()

    def test_valid_order_paid_provisions_subscription_and_emails(self):
        payload = {
            "id": 555, "name": "#1001", "financial_status": "paid",
            "note_attributes": [
                {"name": "user_id", "value": str(self.user.id)},
                {"name": "tier", "value": "premium"},
                {"name": "utm_source", "value": "instagram"},
            ],
        }
        body = json.dumps(payload).encode()
        resp = self.client.post(
            "/api/shopifyin/webhooks/orders-paid/", data=body,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256=self._sign(body),
            HTTP_X_SHOPIFY_SHOP_DOMAIN=self.store.store_domain,
            HTTP_X_SHOPIFY_WEBHOOK_ID="evt_abc123",
        )
        self.assertEqual(resp.status_code, 200)
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.status, Subscription.Status.ACTIVE)
        self.assertEqual(sub.tier, SubscriptionPlan.Tier.PREMIUM)
        self.assertEqual(sub.attribution.get("source"), "instagram")
        self.assertEqual(len(mail.outbox), 1)              # welcome email sent

    def test_invalid_hmac_creates_no_subscription(self):
        body = json.dumps({"id": 1, "financial_status": "paid"}).encode()
        resp = self.client.post(
            "/api/shopifyin/webhooks/orders-paid/", data=body,
            content_type="application/json",
            HTTP_X_SHOPIFY_HMAC_SHA256="deadbeef",
            HTTP_X_SHOPIFY_SHOP_DOMAIN=self.store.store_domain,
        )
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(Subscription.objects.exists())
```

```typescript
// e2e/tests/subscription.spec.ts (skeleton)
import { test, expect } from '@playwright/test';

test('instastory → pricing → (stubbed) checkout → onboarding → first plan', async ({ page, request }) => {
  await page.route('**/api/shopifyin/subscribe/', route =>
    route.fulfill({ json: { status: 'success', data: { checkout_url: '/e2e/fake-checkout' } } }));

  await page.goto('/pricing?utm_source=instagram&utm_medium=story&qr=batchA');
  await expect(page.getByText('99')).toBeVisible();           // tier price from API
  // ... login, click "Vybrat Standard", assert redirect to fake checkout ...
  // server-side: fire signed orders/paid webhook to provision the subscription
  // ... assert app routes to /onboarding, complete quiz, create first plan, assert allowed+completed ...
});
```

---

## 6. Risks & open questions for the founder

1. **Which subscription app?** Must support **CZK + Czech payment methods (card, Apple/Google Pay)** and expose contract/billing webhooks. Verify Appstle/Seal/Recharge availability for a Czech merchant before committing (drives P0-2). If none qualify, fall back to custom Subscription APIs (Option B, larger effort).
2. **Shopify plan cost + app fees** vs. 99/199 CZK price points — confirm unit economics (Shopify Payments availability for CZ, gateway %, app monthly fee).
3. **CZK VAT / invoicing** for recurring B2C — does the chosen app issue compliant Czech invoices, or is a separate invoicing app needed? (Legal/tax requirement.)
4. **Refund / dunning policy** — grace-period length on failed payment, refund handling (`orders/refunded`), and how each maps to entitlement revocation. Needed to finalize P1-2/P2-4.
5. **GDPR on attribution** — UTM/QR cookies need consent treatment consistent with the existing privacy policy; `Subscription.attribution` stores marketing source on a user record. Confirm lawful basis / disclosure.
6. **Webhook reliability** — Shopify retries failed deliveries; the nightly expiry sweep (P1-4) is the safety net for missed events. Confirm acceptable lag.
7. **Exact webhook topic names + subscription-period payload shape are app/path dependent** — every item marked "verify" above must be confirmed against the chosen app's docs (especially how `current_period_end` is derived) before P0-7 is final.
8. **One active subscription per user** assumption — confirm no plan-stacking / upgrade-downgrade mid-period is required for launch (upgrade/downgrade is out of P0 scope).
