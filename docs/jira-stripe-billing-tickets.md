# Jira tickets — Stripe Billing Integration

Paste-ready. One **Epic** + **8 Stories** (P0–P7) mirroring `docs/stripe-billing-plan.md`.
Suggested labels: `billing`, `stripe`, `monetization`. Components: `backend`, `frontend`.

---

## EPIC — Stripe Billing: monthly subscriptions (Standard 99 / Premium 199 CZK)

**Summary:** Stripe Billing: monthly subscription monetization

**Description:**
Take the app from "pricing CTAs dead-end at /login, no payment anywhere" to selling monthly recurring subscriptions via Stripe Billing, with a user-level `Subscription` entitlement that gates meal-plan generation.

Rail decision: **Stripe**, not Shopify (SaaS, not a catalog store; Stripe does native CZK recurring billing; Shopify needs a paid 3rd-party subscription app). See `docs/stripe-billing-plan.md` and `docs/shopify-integration.md`.

**Success metric (Definition of Done for the Epic):** a real `Subscription` row with `status=active`, `tier in {standard,premium}`, non-null `current_period_end`, AND ≥1 `DietaryGoal` reaching `status=completed` for that user, AND a welcome email sent — proven in test mode, then live with a real 99 CZK charge (refunded).

---

## STORY P0 — Stripe test-mode spike (no app code)

**Description:** Validate the mechanism before writing Django. Create 2 test Products + recurring CZK Prices (99, 199) in the Stripe Dashboard, run one Checkout with test card `4242 4242 4242 4242`, and observe `checkout.session.completed` arrive via `stripe listen --forward-to localhost:8000/api/billing/webhook/`.
**Acceptance:** a completed test Checkout Session exists; the webhook event is observed locally; price IDs recorded.
**Estimate:** S

## STORY P1 — Subscription data model

**Description:** Add `Subscription` (user-level entitlement, system of record) and `SubscriptionPlan` (tier config replacing hardcoded `PLANS` in `Pricing.tsx`). Migration, seed tiers (Standard: 7 plans/10 edits/single-store; Premium: 30 plans/5 edits/all-store), Django admin.
**Acceptance:** models migrate; tiers seeded; visible in admin.
**Estimate:** M
**Depends on:** P0

## STORY P2 — Billing API endpoints

**Description:** Implement `/api/billing/`: `checkout/` (create Checkout Session, mode=subscription), `webhook/` (signature-verified, idempotent; handle `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`), `portal/` (Customer Portal session), `me/`, `plans/`. Mount in project urlconf.
**Acceptance:** test-mode checkout creates a real `Subscription` via webhook; renewal/failure/cancel events update it correctly; replayed events are idempotent.
**Estimate:** L
**Depends on:** P1

## STORY P3 — Generation entitlement gate (enforcement)

**Description:** Replace today's permissive gate (`diet_planner/views.py:92` reads `has_free_generations()` but never blocks). Implement `allow_generation(user)` = active subscription within quota OR free credits. Return HTTP 402 `PAYMENT_REQUIRED` when neither; increment `plans_used_this_period` on paid path. Apply same logic to the plan-edit endpoint (`edits_per_plan`).
**Acceptance:** user with no credits and no active sub is blocked with 402; paid user generates within quota; quota resets on renewal.
**Estimate:** M
**Depends on:** P1

## STORY P4 — Frontend: wire pricing CTAs to checkout

**Description:** `Pricing.tsx` paid CTAs (`Vybrat Standard`/`Vybrat Premium`) currently `navigate('/login')`. Change to: logged-out → `/login?next=/pricing`; logged-in → `POST /api/billing/checkout/` then redirect to Stripe. Add "Manage subscription" → `portal/`. Map 402 → redirect to `/pricing`. Handle `?sub=success` return. Optionally source tiers from `GET /api/billing/plans/`.
**Acceptance:** clicking a paid tier reaches Stripe Checkout; post-pay returns to app with entitlement active; manage link opens portal.
**Estimate:** M
**Depends on:** P2

## STORY P5 — Transactional emails

**Description:** Welcome email on subscription activation; optional payment-failed notice on `invoice.payment_failed`.
**Acceptance:** welcome email recorded as sent on activation.
**Estimate:** S
**Depends on:** P2

## STORY P6 — End-to-end verification (test → live)

**Description:** Prove the full north-star journey in test mode (pricing → checkout → webhook → entitlement → onboarding → first plan completed → welcome email). Then flip to live keys, repeat with a real 99 CZK charge and refund it. Configure live webhook endpoint + Customer Portal + Stripe Tax (CZ VAT).
**Acceptance:** Epic success metric met in test mode and once live.
**Estimate:** M
**Depends on:** P3, P4, P5

## STORY P7 — Funnel instrumentation

**Description:** Track `pricing_view → checkout_started → checkout_paid → first_plan_completed`, segmentable by attribution source (instastory/qr/organic).
**Acceptance:** funnel events fire and are queryable by source.
**Estimate:** S
**Depends on:** P4

---

## Config sub-task (attach to P0/P2)
Env vars across `.env`, docker-compose, DO App Platform: `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_STANDARD`, `STRIPE_PRICE_PREMIUM`. Add `stripe` to `requirements.txt`. Keep test vs live keys separate.
