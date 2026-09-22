# Promo codes — design

Date: 2026-09-22. Status: approved by owner in brainstorming, pending spec review.

## Problem

There is no way to hand a user a code that unlocks a paid tier. Stripe
Checkout already accepts Stripe Promotion Codes (`allow_promotion_codes=True`),
but that path always collects a card and cannot express "100 % off, no card,
forever". The owner's first use case is exactly that: one code, shared by
word of mouth, redeemable by up to 20 accounts, granting Premium for life
with no payment details.

## Decisions made by the owner

- Redemption happens in **our UI** (`/pricing`), not on the Stripe page.
- A 100 % code grants the tier directly, **never touching Stripe**.
- First code: 100 %, lifetime, any tier, max 20 redemptions, no expiry.
- Every attribute above is a **per-code admin field**; future codes may
  differ (partial %, timed, tier-locked, expiring).
- When a timed grant ends the user drops to the free path and sees the
  existing "subscribe now" prompts.
- Google sign-in must work: the code is remembered in the browser and
  applied after any successful authentication.

## Approach

Django owns codes and redemptions. For 1–99 % codes Django mirrors each code
to a Stripe Coupon and attaches it to Checkout server-side, so Stripe handles
renewals and pro-rating. For 100 % codes Django writes the existing
`Subscription` entitlement row itself. Nothing downstream of that row changes.

The rejected alternative, mirroring everything to Stripe Promotion Codes and
relying on Checkout's "collect card only if required", still creates a Stripe
customer and a zero-value subscription for every free user and makes the
no-card behaviour depend on Stripe's per-duration rules.

## Data model (`billing/models.py`)

### `PromoCode`

| field | type | notes |
|---|---|---|
| `code` | CharField(40), unique | stored uppercase; input is stripped and upper-cased before lookup |
| `percent_off` | PositiveSmallIntegerField | 1–100, validated |
| `duration_kind` | choices `lifetime` / `months` / `first_invoice` | `first_invoice` maps to Stripe coupon `once` |
| `duration_months` | PositiveSmallIntegerField, null | required iff `duration_kind == months` |
| `tiers` | JSONField, default `[]` | subset of `['standard','premium']`; empty = any tier |
| `max_redemptions` | PositiveIntegerField, null | null = unlimited |
| `expires_at` | DateTimeField, null | null = never |
| `is_active` | BooleanField, default True | kill switch |
| `note` | TextField, blank | admin memo (who got it, campaign) |
| `stripe_coupon_id` | CharField(255), blank | set automatically for `percent_off < 100`; always blank for 100 |
| `created_at`, `updated_at` | auto | |

Model helpers:

- `redemption_count()` → count of `PromoRedemption` rows.
- `allows_tier(tier)` → `not self.tiers or tier in self.tiers`.
- `check_redeemable(now)` → returns `None` when redeemable, else one of the
  reason codes `inactive`, `expired`, `exhausted`.
- `grant_expiry(now)` → `None` for lifetime, `now + duration_months` months
  for months, `now + 1 month` for `first_invoice` (a 100 % first-invoice
  code equals one free month).

### `PromoRedemption`

| field | type | notes |
|---|---|---|
| `promo_code` | FK PromoCode, CASCADE | |
| `user` | FK User, CASCADE | |
| `tier` | CharField(20) | tier chosen at redemption |
| `redeemed_at` | DateTimeField, auto | |
| `stripe_checkout_session_id` | CharField(255), blank | set for percent codes |

`unique_together = (promo_code, user)`. This table is the counter for
`max_redemptions`.

**When the row is written.** For 100 % codes: at redeem time, inside the
same transaction as the grant. For percent codes: in the
`checkout.session.completed` webhook handler, keyed on the
`promo_code_id` metadata, so an abandoned Checkout does not consume a slot.
The pre-checkout redeemable check therefore counts committed redemptions
only; two users racing for the last slot of a percent code can both reach
Stripe, and the second one's webhook still records the redemption (we never
refuse a paid customer). This over-run is accepted for percent codes.

### `Subscription` changes

| change | why |
|---|---|
| `source` CharField choices `stripe` / `promo`, default `stripe` | tells the gate and the UI which rules apply |
| `grant_expires_at` DateTimeField, null | promo rows only; null = lifetime |
| `promo_code` FK PromoCode, null, SET_NULL | audit link |
| `stripe_customer_id` → `blank=True` | promo rows have no Stripe customer |
| `stripe_subscription_id` → `null=True, blank=True` (unique kept; Postgres allows multiple NULLs) | promo rows have no Stripe subscription |

Behaviour changes on the model:

- `is_entitled()`: for `source == promo` return `status == active and
  (grant_expires_at is None or grant_expires_at > now)`. Stripe rows keep
  the existing `current_period_end` rule.
- `current_period_end` on a promo row is the **rolling quota window**
  (30 days from grant). `within_monthly_quota()` and `remaining_quota()`
  call `_roll_quota_window_if_due()` first: if `source == promo` and
  `current_period_end <= now`, set `current_period_end += 30 days`
  (repeated until in the future), reset `plans_used_this_period = 0`,
  save. Stripe rows are never rolled this way; `invoice.paid` still owns
  their reset.
- `upsert_subscription()` (Stripe provisioning) sets `source='stripe'`
  and `grant_expires_at=None` in its defaults, so a later paid subscription
  overwrites a promo grant. `promo_code` is left as-is for audit.

## Precedence rules

1. Redeem is refused with `already_subscribed` when the user already holds an
   entitled subscription of either source.
2. An expired or canceled promo row is overwritten by a new redemption
   (different code, or same code is blocked by the unique constraint).
3. A paid Stripe subscription always wins over a promo row (rule in
   `upsert_subscription`).
4. A promo row is never sent to Stripe: `cancel_subscription_for_user`
   (account deletion) skips Stripe for `source == promo` and just deletes
   the row via cascade.

## Stripe coupon sync (`billing/services.py`)

`ensure_stripe_coupon(promo) -> str | None`:

- No-op when `percent_off == 100`, when billing is not configured, or when
  `stripe_coupon_id` is already set.
- Creates `stripe.Coupon` with `percent_off`, `duration` = `forever` /
  `repeating` (+ `duration_in_months`) / `once`, `name = code`,
  `metadata = {promo_code_id}`; stores the id.
- Called from `PromoCodeAdmin.save_model` after save. Stripe coupons are
  immutable, so when `percent_off`, `duration_kind` or `duration_months`
  change on a code that already has a coupon, `save_model` clears
  `stripe_coupon_id` first and a new coupon is created. Old coupons are
  left in Stripe (harmless).
- Admin action "Vytvořit Stripe kupón" re-runs it for selected rows.
- Expiry and max uses are enforced in Django before Checkout is created.
  The Stripe coupon carries neither `redeem_by` nor `max_redemptions`.

## API (`billing/urls.py`, mounted at `/api/billing/`)

### `GET promo/validate/?code=X` — public

Response 200 always (never leaks existence via status codes):

```json
{"valid": true, "code": "LETO2026", "percent_off": 100,
 "duration_kind": "lifetime", "duration_months": null,
 "tiers": [],
 "prices": {"standard": {"original": 99, "discounted": 0},
            "premium":  {"original": 199, "discounted": 0}}}
```

or `{"valid": false, "reason": "not_found" | "inactive" | "expired" | "exhausted"}`.
`prices` lists only the tiers the code allows; `discounted` is
`round(original * (100 - percent_off) / 100)`.

### `POST promo/redeem/` — authenticated

Body `{"code": "...", "tier": "standard" | "premium"}`.

Steps, inside `transaction.atomic()` with `select_for_update()` on the
`PromoCode` row:

1. Normalise code, load it; 400 `not_found` if missing.
2. `check_redeemable(now)`; 400 with its reason.
3. `allows_tier(tier)`; 400 `tier_not_allowed`.
4. Existing `PromoRedemption(code, user)`; 400 `already_redeemed`.
5. `active_subscription(user)`; 400 `already_subscribed`.
6. If `percent_off == 100`: `update_or_create` the `Subscription` for the
   user with `source=promo, tier, status=active, stripe_customer_id='',
   stripe_subscription_id=None, current_period_end=now+30d,
   grant_expires_at=promo.grant_expiry(now), promo_code=promo,
   plans_used_this_period=0, cancel_at_period_end=False`; create the
   `PromoRedemption`; return 200 `{"granted": true, "tier": tier}`.
7. Else: create Stripe Checkout exactly as `CheckoutView` does today but
   with `discounts=[{"coupon": promo.stripe_coupon_id}]`,
   `allow_promotion_codes` omitted (Stripe forbids both), and
   `promo_code_id` added to session and subscription metadata. Call
   `ensure_stripe_coupon` first if the id is blank. Return 200
   `{"granted": false, "url": session.url}`.

Error body shape: `{"status": "error", "reason": "<code>", "error": "<Czech
message>"}`. Stripe failures return 400 like `CheckoutView` (App Platform
replaces 5xx bodies).

`CheckoutView` is refactored so both views share one
`services.create_checkout_session(user, tier, promo=None)` helper.

### Webhook

`handle_checkout_completed`: after provisioning, if
`session.metadata.promo_code_id` is present, `get_or_create` the
`PromoRedemption` with `stripe_checkout_session_id`. Idempotent via the
unique constraint and the existing event ledger.

### `GET me/`

`SubscriptionSerializer` adds `source` and `grant_expires_at`.

## Frontend

### `lib/promo.ts`

- `validatePromo(code)`, `redeemPromo(code, tier)` API wrappers.
- `getPendingPromo()`, `setPendingPromo(code)`, `clearPendingPromo()` on
  localStorage key `pending_promo`, all wrapped in try/catch.
- `discountedPrice(original, percent)` mirroring the backend rounding.

### `/pricing`

- Below the plan cards: "Mám promo kód" — input, "Použít" button, result
  line. `?promo=KOD` in the URL pre-fills and auto-validates; a stored
  pending code does the same on mount.
- Valid code: `setPendingPromo`, allowed cards show `original` struck
  through and `discounted` (0 renders as "0 Kč" with sub-line "bez platební
  karty"), disallowed cards are unchanged. Invalid: Czech reason text,
  pending code cleared if it was the stored one.
- CTA on a discounted card, logged in: `redeemPromo(code, tier)`.
  `granted` → `clearPendingPromo`, navigate `/?promo=granted`; `url` →
  `window.location.href = url` (pending code cleared by the success page).
  Redeem error → reason text under the card, pending cleared for terminal
  reasons (`exhausted`, `expired`, `already_redeemed`, `already_subscribed`).
- CTA, logged out: navigate `/login?next=/pricing` as today; the pending
  code survives in storage.
- `trackCheckoutStarted()` fires only on the Stripe path.

### Login / signup

- Banner on `/login` (both tabs) when a pending code exists: "Kód X se
  uplatní po přihlášení." plus a small "zrušit" that clears it.
- Post-auth routing: both the email login success branch and
  `LoginSuccess.tsx` (Google) navigate to `/pricing` instead of `/` when
  `getPendingPromo()` is set. `/pricing` is a public route, so the
  onboarding redirect in `ProtectedRoute` does not intercept it; onboarding
  runs when the user next enters the app.
- `/billing/success` clears the pending code.

### Dashboard

`/?promo=granted` shows a one-time toast "Máte aktivní Premium přes promo
kód." (existing toast mechanism), then strips the param.

### Settings › SubscriptionSection

For `source === 'promo'`: label "přes promo kód", sub-line "platí navždy" or
"platí do DD. MM. YYYY", and the Stripe portal button is hidden (no customer
exists). Quota display unchanged.

## Admin (`billing/admin.py`)

- `PromoCodeAdmin`: list `code, percent_off, duration_kind, tiers, used /
  max, expires_at, is_active, stripe_coupon_id`; filters on `is_active,
  duration_kind`; search on `code, note`; read-only `stripe_coupon_id,
  created_at, updated_at`; inline read-only `PromoRedemption` rows; action
  "Vytvořit Stripe kupón". `save_model` calls `ensure_stripe_coupon`.
- `PromoRedemptionAdmin`: read-only list with search on user and code.
- `SubscriptionAdmin`: add `source`, `grant_expires_at`, `promo_code` to
  list and filters.

## Error handling

- All reason codes are stable strings; the frontend maps them to Czech.
- Stripe unavailable on a percent redeem → 400 with `stripe_error`; the
  100 % path has no Stripe dependency and works when billing is
  unconfigured.
- Lock contention on the code row is a normal wait, not an error.

## Out of scope

- Referral attribution (who shared with whom).
- Per-user codes generated in bulk.
- Applying a code to an already active paid subscription.
- Any change to the free-generation counter.

## Testing

Backend (`billing/tests.py`, run in CI):

- `PromoCode.check_redeemable`: inactive, expired, exhausted, ok.
- `grant_expiry` for each duration kind.
- Validate endpoint: prices per tier, tier filter, each invalid reason.
- Redeem 100 %: creates promo subscription + redemption; `is_entitled`
  true; lifetime has null expiry; `me/` reports `source=promo`.
- Redeem refusals: tier_not_allowed, already_redeemed, already_subscribed
  (Stripe and promo), exhausted at exactly `max_redemptions`.
- Concurrency: two threads redeem the last slot, exactly one succeeds.
- Timed grant: entitled before `grant_expires_at`, not after.
- Quota window: promo row past `current_period_end` rolls forward and
  resets usage on read; Stripe row does not.
- Percent redeem: Checkout created with `discounts` and metadata, no
  `allow_promotion_codes` (Stripe mocked); blank coupon triggers
  `ensure_stripe_coupon`.
- Webhook `checkout.session.completed` with `promo_code_id` writes the
  redemption once across duplicate deliveries.
- `upsert_subscription` over a promo row flips `source` to stripe.
- `cancel_subscription_for_user` skips Stripe for promo rows.

Frontend (vitest): `promo.ts` storage helpers and `discountedPrice`;
Pricing renders struck-through and discounted prices for a valid code.

Post-deploy: `/qa-prod` covering `/pricing?promo=<test code>` validate,
Google-style pending-code round trip, and Settings rendering for a promo
subscriber.
