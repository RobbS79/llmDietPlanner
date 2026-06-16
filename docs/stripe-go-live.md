# Stripe go-live — create live prices & flip to real payments

Test mode is fully built and proven. This doc is the **launch-day checklist** to start
charging real money. Do it only when you're ready to take real payments.

---

## Step 1 — Find your LIVE secret key

The key we've used so far (`sk_test_…`) is from a **sandbox** (fake money). Real prices
need a **live** key from your *real, activated* Stripe account.

1. Go to **https://dashboard.stripe.com** and log in with your real business account.
2. Top-right: make sure the **"Test mode" toggle is OFF** (you want **Live mode**).
   - If you see a banner like *"Activate your account"* / *"Complete your profile"*, your
     account isn't live yet. You must submit business details (Czech business info) and a
     bank account for payouts before live keys will charge. Finish that first.
3. Left sidebar: **Developers → API keys** (or search "API keys").
4. Under **Standard keys**, find **Secret key** → click **Reveal live key** (or
   **Create secret key**). It looks like `sk_live_…`. Copy it.
   - ⚠️ Treat it like a password. Don't paste it into chat, commits, or screenshots.

> Note: the sandbox ("mealPlanner sandbox") is a separate fake environment. Live keys
> always come from the main account with the mode toggle on **Live**.

---

## ✅ LIVE prices created (2026-06-13)

Live account `acct_1Thr0DAUVVtUs6xl`. Both prices exist in live mode:

- `STRIPE_PRICE_STANDARD=price_1ThuFOAUVVtUs6xl3iz4STto` — 9900 CZK, monthly, `lookup_key=standard_monthly`
- `STRIPE_PRICE_PREMIUM=price_1ThuX5AUVVtUs6xlAwBa1sXu` — 19900 CZK, monthly (created via dashboard)
- `STRIPE_PUBLISHABLE_KEY=pk_live_51Thr0DAUVVtUs6xlfya8IfBP3hHBo0ihr3CxphhqOrpy01L7fNoPazlyDZ5YpBs4AtIhSgVei0HCuC8AW0X5mHf000uxuxfGmj`

Remaining go-live work: Steps 3–6 below (set DO env incl. `sk_live` + prod webhook secret, register webhook, portal/VAT, smoke test).

## Step 2 — Create the two LIVE prices (done — see above)

Paste your live key into the first line, then run the whole block in a terminal on this
server (the `stripe` CLI is already installed). It creates both products + monthly CZK
prices to exactly match the test ones, and prints the two env lines you need next.

```bash
LIVE=sk_live_PASTE_YOUR_LIVE_KEY_HERE

# --- Standard: 99 CZK / month ---
PROD_STD=$(stripe products create --api-key "$LIVE" \
  -d name="Eatalníček Standard" -d "metadata[tier]=standard" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
stripe prices create --api-key "$LIVE" \
  -d product="$PROD_STD" -d currency=czk -d unit_amount=9900 \
  -d "recurring[interval]=month" -d lookup_key=standard_monthly \
  | python3 -c "import sys,json;print('STRIPE_PRICE_STANDARD='+json.load(sys.stdin)['id'])"

# --- Premium: 199 CZK / month ---
PROD_PREM=$(stripe products create --api-key "$LIVE" \
  -d name="Eatalníček Premium" -d "metadata[tier]=premium" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
stripe prices create --api-key "$LIVE" \
  -d product="$PROD_PREM" -d currency=czk -d unit_amount=19900 \
  -d "recurring[interval]=month" -d lookup_key=premium_monthly \
  | python3 -c "import sys,json;print('STRIPE_PRICE_PREMIUM='+json.load(sys.stdin)['id'])"
```

It prints two lines, e.g.:

```
STRIPE_PRICE_STANDARD=price_1Live…
STRIPE_PRICE_PREMIUM=price_1Live…
```

Keep those — they go into the env in Step 3.

---

## Step 3 — Set live env vars on DigitalOcean App Platform

In the DO App Platform dashboard → your app → **Settings → App-Level Environment
Variables**, set these (mark each **Encrypted**), then deploy:

| Var | Value |
|-----|-------|
| `STRIPE_SECRET_KEY` | your `sk_live_…` |
| `STRIPE_PUBLISHABLE_KEY` | `pk_live_51Thr0DAUVVtUs6xlfya8IfBP3hHBo0ihr3CxphhqOrpy01L7fNoPazlyDZ5YpBs4AtIhSgVei0HCuC8AW0X5mHf000uxuxfGmj` |
| `STRIPE_PRICE_STANDARD` | `price_1ThuFOAUVVtUs6xl3iz4STto` |
| `STRIPE_PRICE_PREMIUM` | `price_1ThuX5AUVVtUs6xlAwBa1sXu` |
| `STRIPE_WEBHOOK_SECRET` | the **live** signing secret from Step 4 (NOT the local test one) |

The local `.env` test values stay as-is for local dev — only DO gets live values.

---

## Step 4 — Register the live webhook endpoint

The local `whsec_…` only works for the local `stripe listen`. Production needs its own:

1. Dashboard (Live mode) → **Developers → Webhooks → Add endpoint**.
2. Endpoint URL: `https://eatalnicek.eu/api/billing/webhook/`
3. Select events: `checkout.session.completed`, `invoice.paid`,
   `invoice.payment_failed`, `customer.subscription.updated`,
   `customer.subscription.deleted`.
4. After creating it, copy its **Signing secret** (`whsec_…`) → that's the
   `STRIPE_WEBHOOK_SECRET` for DO in Step 3.

---

## Step 5 — Other dashboard settings (live mode)

- **Customer Portal**: Settings → Billing → Customer portal → activate (lets users
  cancel/update card; our `/api/billing/portal/` opens it).
- **Tax / CZ VAT**: decide whether to enable Stripe Tax — see `docs/stripe-billing-plan.md` §9.

---

## Step 6 — Live smoke test

1. On `https://eatalnicek.eu/pricing`, subscribe to Standard with a **real card**.
2. Confirm a `Subscription` row goes `active` and the webhook fired (Dashboard → Webhooks → event log).
3. **Refund** the charge (Dashboard → Payments → the payment → Refund) so you're not out 99 CZK.
