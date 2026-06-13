# Stripe Billing Integration Plan — LLM Diet Planner

**Status:** Plan for execution · **Date:** 2026-06-10 · **Rail decided:** Stripe Billing (supersedes Shopify for billing)

Goal: take the app from "pricing CTAs that dead-end at `/login`, no payment anywhere" to **selling monthly recurring subscriptions through Stripe**, with a real `Subscription` entitlement that gates meal-plan generation, and a provable "first paying customer" journey.

> **Why Stripe, not Shopify:** see memory `billing-stripe-decision` and `docs/shopify-integration.md`. Short version: this is a SaaS, not a catalog store; Shopify can't run recurring billing without a paid third-party app, Stripe does it natively in CZK. The entitlement architecture below is identical to `docs/shopify-subscription-integration-plan.md` §2.1 — only the payment rail changed. `shopifyin/` is shelved for billing (its one-time-cart code is not reused).

---

## 1. Success metric

**First paying customer activated** = a real `Subscription` row with `status=active`, `tier in {standard, premium}`, non-null `current_period_end`, AND ≥1 `DietaryGoal` reaching `status=completed` for that user, AND a welcome email sent.

North-star journey (must be provable end-to-end in Stripe **test mode** first, then live):
> `/pricing` → pick Standard (99) or Premium (199) → pay on Stripe Checkout (recurring) → `checkout.session.completed` webhook provisions `Subscription` in Django → user returns to app → onboarding → generates first plan (entitlement gate passes) → welcome email.

---

## 2. Architecture

### 2.1 The core shift: free-credit counter → user-level entitlement

Today there is **no paywall**. `diet_planner/views.py:92` reads `profile.has_free_generations()` only to *tag* the goal (`is_free_generation`) and decrement the counter (`:141-142`); it **never blocks** when credits hit zero. Anyone can generate unlimited plans.

New model — a **user-level, time-bounded `Subscription`** that generation checks. Free tier keeps the existing `UserProfile.free_generations_remaining` counter. The gate becomes:

```python
def allow_generation(user) -> bool:
    sub = active_subscription(user)              # status=active AND current_period_end > now
    if sub and sub.within_monthly_quota():       # paid path
        return True
    return user.profile.has_free_generations()   # free path (unchanged)
```

On reject: return a **402-style** response the frontend turns into a redirect to `/pricing`. This is the real enforcement that does not exist today.

### 2.2 Stripe is the system of record for *billing*; Django is the system of record for *entitlement*

Stripe runs the billing clock (charges, retries/dunning, card updates). Django never runs a billing timer — it only **reacts to webhooks** and flips the `Subscription` row. This separation is the whole point and keeps our code small.

### 2.3 The six Stripe objects (mapping)

| Stripe | Ours |
|---|---|
| Product ×2 | "Eatalníček Standard", "Eatalníček Premium" (created once in Stripe Dashboard, test + live) |
| Price ×2 (recurring, CZK, monthly) | 99 CZK/mo, 199 CZK/mo — IDs stored in settings/env (`STRIPE_PRICE_STANDARD`, `STRIPE_PRICE_PREMIUM`) |
| Customer | one per Django user; `stripe_customer_id` stored on profile/subscription |
| Checkout Session (`mode=subscription`) | created by our checkout endpoint; we redirect the browser to `session.url` |
| Subscription | mirrored into our `Subscription` model via webhooks |
| Customer Portal session | created by our portal endpoint; Stripe-hosted cancel/update-card/invoices |

---

## 3. Data model (new — in a new `billing/` app, or appended to an existing app)

### `Subscription` (user-level, system of record for entitlement)
| Field | Type | Notes |
|---|---|---|
| `user` | FK(User, unique) | one active sub per user |
| `tier` | TextChoices `STANDARD`/`PREMIUM` | |
| `status` | TextChoices `ACTIVE`/`PAST_DUE`/`CANCELED`/`EXPIRED` | mirrors Stripe sub status |
| `stripe_customer_id` | str, indexed | |
| `stripe_subscription_id` | str, unique, indexed | webhook idempotency key |
| `current_period_end` | datetime | from Stripe; the entitlement expiry |
| `cancel_at_period_end` | bool | set when user cancels in portal |
| `plans_used_this_period` | int | reset to 0 on each `invoice.paid` renewal |
| `created_at` / `updated_at` | datetime | |

### `SubscriptionPlan` (tier config — replaces hardcoded `PLANS` in `Pricing.tsx`)
`tier`, `name`, `price_czk`, `stripe_price_id`, `monthly_plan_quota` (Standard 7, Premium 30), `edits_per_plan` (Standard 10, Premium 5), `allow_multi_store` (Premium only). Source of truth for both the pricing page (served via API) and the quota gate. Seed via data migration / fixture.

> Quotas taken verbatim from `frontend/src/pages/Pricing.tsx` PLANS (Standard: 7 plans / 10 edits / single-store; Premium: 30 plans / 5 edits / all-store).

---

## 4. Backend endpoints (`/api/billing/`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `plans/` | public | Serve tiers from `SubscriptionPlan` (frontend reads instead of hardcoding) |
| POST | `checkout/` | user (JWT) | Create Stripe Checkout Session (`mode=subscription`, price=tier), return `{url}` |
| POST | `portal/` | user | Create Customer Portal session, return `{url}` |
| POST | `webhook/` | Stripe signature | Handle billing lifecycle events (idempotent) |
| GET | `me/` | user | Current user's subscription status + remaining quota (for UI badges/gating) |

### `checkout/` — request/response
```jsonc
// POST /api/billing/checkout/  { "tier": "standard" }
// → resolve price_id from SubscriptionPlan, get-or-create Stripe Customer for user,
//   stripe.checkout.Session.create(mode="subscription", line_items=[{price, quantity:1}],
//       customer=cust, success_url=".../app?sub=success", cancel_url=".../pricing",
//       client_reference_id=str(user.id), metadata={"user_id": user.id, "tier": tier})
{ "url": "https://checkout.stripe.com/c/pay/cs_test_..." }
```
Frontend redirects `window.location = url`.

### `webhook/` — events to handle (the core of the integration)
| Event | Django action |
|---|---|
| `checkout.session.completed` | Create/activate `Subscription` (tier from metadata, `stripe_subscription_id`, `current_period_end`), send welcome email |
| `invoice.paid` | Renewal success → extend `current_period_end`, reset `plans_used_this_period=0` |
| `invoice.payment_failed` | Mark `PAST_DUE` (Stripe auto-retries per dunning settings) |
| `customer.subscription.updated` | Sync `status`, `current_period_end`, `cancel_at_period_end` |
| `customer.subscription.deleted` | Mark `EXPIRED`/`CANCELED` (entitlement ends) |

**Verification (mandatory):** `stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)` — rejects forged calls. Same trust model as the Shopify HMAC webhook you already have, just Stripe's helper does it. Handler must be **idempotent** keyed on `stripe_subscription_id` + event id (Stripe retries on non-2xx).

---

## 5. Generation gate (enforcement — the behavior change)

In `diet_planner/views.py` (~L90–142), before creating/triggering the goal:
1. Compute `allow = allow_generation(request.user)` (§2.1).
2. If not `allow` → return HTTP 402 `{"status":"error","code":"PAYMENT_REQUIRED"}` and **do not** create the goal or enqueue Celery.
3. If allowed via paid path → increment `Subscription.plans_used_this_period`; if via free path → keep existing `use_free_generation()` decrement.
4. Edits gate: enforce `edits_per_plan` per tier on the plan-edit endpoint similarly.

Frontend `ProtectedRoute`/API layer maps 402 → redirect to `/pricing`.

---

## 6. Frontend changes

- `Pricing.tsx`: paid CTAs (`Vybrat Standard` L161-area, `Vybrat Premium`) currently `navigate('/login')`. Change to:
  - if logged out → `/login?next=/pricing` (so they return to buy);
  - if logged in → `POST /api/billing/checkout/ {tier}` then `window.location = url`.
  - Free CTA (`Začít zdarma`) stays → signup.
- Optionally fetch tiers from `GET /api/billing/plans/` instead of the hardcoded `PLANS` array (keeps price/quota in one place).
- Add a "Manage subscription" link in account settings → `POST /api/billing/portal/` → redirect.
- Handle `?sub=success` return param → toast + refresh entitlement.

---

## 7. Config / setup

1. `pip install stripe`; add to `requirements.txt`.
2. **Stripe Dashboard (test mode first):** create 2 Products + recurring CZK Prices; copy price IDs.
3. **Env:** `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` (if needed client-side), `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD`, `STRIPE_PRICE_PREMIUM`. Add to `.env`, `docker-compose`, DO App Platform (per `env-config` memory). Keep test vs live keys separate.
4. **Webhook endpoint:** register `…/api/billing/webhook/` in Stripe Dashboard for the 5 events in §4. For local dev use `stripe listen --forward-to localhost:8000/api/billing/webhook/`.
5. **Customer Portal:** enable + configure (allowed actions: cancel, update payment method, invoice history) in Stripe Dashboard.
6. **Czech specifics to confirm:** Shopify Payments unused; for Stripe enable Stripe Tax for Czech VAT on invoices, and confirm CZK + card/Apple Pay/Google Pay in the Stripe account. Business must be a registered CZ entity (same requirement as any rail).

---

## 8. Phased checklist

- **P0 — Spike (test mode, no app code yet):** create test Products/Prices, run one Checkout with card `4242…`, watch `checkout.session.completed` land via `stripe listen`. *Goal: see the objects move.*
- **P1 — Models:** `SubscriptionPlan` + `Subscription`, migration, seed tiers, admin.
- **P2 — Endpoints:** `checkout/`, `webhook/` (all 5 events, idempotent, signature-verified), `portal/`, `me/`, `plans/`. Mount at `/api/billing/`.
- **P3 — Gate:** implement `allow_generation`, wire 402 into `diet_planner/views.py` create + edit flows.
- **P4 — Frontend:** rewire paid CTAs → checkout; manage-subscription link; 402→`/pricing`; success toast.
- **P5 — Emails:** welcome on activation, optional payment-failed notice.
- **P6 — E2E verify (test mode):** full north-star journey green; then flip to live keys, repeat with a real 99 CZK charge, refund it.
- **P7 — Instrumentation:** funnel events `pricing_view → checkout_started → checkout_paid → first_plan_completed`, segmentable by attribution source.

---

## 9. Known gaps / open questions

- **Czech VAT invoicing** — confirm Stripe Tax covers CZ B2C recurring invoices, or whether a separate invoicing step is needed (founder decision).
- **Proration / tier switching** (Standard ↔ Premium) — Stripe handles proration; decide UX (immediate vs period-end). Defer past P0.
- **Free→paid migration** of existing users — they keep `free_generations_remaining`; no action needed until they subscribe.
- **`shopifyin/`** — leave mounted-or-not as-is; it is orthogonal now. Do not invest further in it for billing.
