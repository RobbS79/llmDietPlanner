# Billing / Stripe Webhook Investigation — 2026-06-16

Status: **code fix merged to `develop` (PR #19); prod verification pending.**

## Symptom

Reported as: *"the user path is broken — a user paid but gets no service, and we
can't maintain it from the admin panel."* Concretely, the meal-plan generation
endpoint `/api/goals/` returns **HTTP 402 Payment Required** for a logged-in
user, and there's no working admin lever to inspect/repair entitlement.

## How entitlement works (recap)

- **Stripe = system of record for billing**; **Django = system of record for
  entitlement.** The generation gate (`diet_planner/views.py`) allows a plan only
  if the user has an active `billing.Subscription` row within quota **or**
  remaining `UserProfile.free_generations_remaining` (default **2 lifetime**).
- The `Subscription` row is created/updated **only** by Stripe webhooks
  (`billing/services.py::HANDLERS`).

## Investigation timeline & evidence

1. **Prod logs** showed repeated `WARNING django.request Payment Required:
   /api/goals/` for **`user_id=14`** (a Google-OAuth account). Initial (wrong)
   assumption: this was the paying customer.
2. **Code read** revealed the provisioning gap: entitlement was created in
   exactly one handler — `handle_checkout_completed`
   (`checkout.session.completed`). Every other handler only **updated** an
   existing row and returned early if none existed; `customer.subscription.created`
   wasn't handled at all. So a lost/late checkout event, or a subscription made
   outside checkout, → Stripe active but Django no row → permanent 402.
3. **Stripe (via Claude's Stripe MCP)** showed an active Standard subscription —
   but in a **sandbox** account (`mealPlanner sandbox`, `acct_1Thr0gPLWe9Clmm3`,
   `livemode:false`). **This was a red herring.** The MCP is connected only to the
   sandbox and cannot see live data.
4. **DO app spec** (readable, non-secret values) proved prod runs **LIVE** Stripe:
   - `STRIPE_PUBLISHABLE_KEY = pk_live_51Thr0DAUVVtUs6xl…`
   - `STRIPE_PRICE_STANDARD = price_1ThuFOAUVVtUs6xl…`, `STRIPE_PRICE_PREMIUM = price_1ThuX5AUVVtUs6xl…`
   - Live account fragment `…AUVVtUs6xl` ≠ sandbox `…PLWe9Clmm3`.
5. **Live dashboard (supplied by operator)** — the real subscription:
   - `sub_1TiX8xAUVVtUs6xlv03usc0s`, Standard, **Active**, started **Jun 15**.
   - Customer **`admin@kentakin.eu`** (name `admin_5a65`, `cus_UhKqoewUHMDv7E`).
   - Invoice `J72K1HIA-0001` — **Kč99.00 Paid** on Jun 15 11:48. Real payment.
   - Webhook endpoint **`brilliant-bliss`** → `https://eatalnicek.eu/api/billing/webhook/`,
     Active. Event deliveries:
     - **Jun 15 11:49:28** `checkout.session.completed` → **200 OK**
     - **Jun 15 11:49:28** `invoice.paid` → **200 OK**
     - **Jun 16 (manual resend)** `checkout.session.completed` → **200 OK ("Recovered")**
   - The Jun 15 `checkout.session.completed` payload carried
     `client_reference_id: "20"` and `metadata: {tier: "standard", user_id: "20"}`,
     `livemode: true`.

## Findings (corrected)

- **The webhook pipeline is healthy.** Endpoint, signing secret, and mode are
  correct — Stripe delivered **200 OK** at payment time with a valid `user_id`.
  Earlier worries about a missing endpoint / signing-secret / live-vs-test
  mismatch were **wrong**, driven by sandbox-only tooling.
- **The paying customer is `user_id=20` (`admin@kentakin.eu`) — not `user_id=14`.**
  The 402 in the logs was a *different, unpaid* account (user 14) that had
  exhausted its 2 free generations. For user 14, **402 is correct paywall
  behavior, not a bug.**
- **The manual resend was a no-op.** Prod logged
  `Duplicate webhook evt_1TiX90AUVVtUs6xltKkWfCBN ignored` — the idempotency
  ledger (`ProcessedWebhookEvent`) had already recorded that event id on Jun 15,
  so reprocessing was short-circuited.

## The one open question

Did Jun 15's **200 OK** actually create user 20's `Subscription` row, or did it
return 200 **without** provisioning (handler early-return after logging an
error)? Prod was redeployed on Jun 16 morning, so the Jun 15 log lines are gone
with the previous container — logs can't answer it.

**Decisive test (no prod access needed):** log into eatalnicek.eu as
`admin@kentakin.eu` and attempt to generate a plan.

| Result | Meaning | Action |
|--------|---------|--------|
| ✅ generates | Jun 15 provisioning succeeded; the paying customer was always fine | none — the 402 was user 14 (unpaid) |
| ⛔ 402 | Jun 15 returned 200 but didn't provision; idempotency now blocks any resend | deploy PR #19, then reconcile (below) |

## The code fix — PR #19 (`fix/billing-webhook-provisioning`, merged to `develop`)

Hardens the exact trap above (a 200-but-failed delivery that idempotency then
prevents retrying) and adds a recovery tool. Changes in `billing/services.py`:

- Extract a shared `upsert_subscription()` — one provisioning path for all handlers.
- `customer.subscription.updated` now **creates-if-missing** (out-of-order / lost
  checkout still provisions) instead of silently dropping the user.
- Register **`customer.subscription.created`** so dashboard-made subs provision.
- Stop resetting `plans_used_this_period` on update events — only `invoice.paid`
  renewals reset it (previously any Stripe tweak refunded the monthly quota).
- New management command **`reconcile_subscription`** (recovery / drift repair):

  ```bash
  python manage.py reconcile_subscription <sub_id> [--email X | --user-id N]
  ```

  Retrieves the live subscription via prod's Stripe key, resolves the Django user
  (explicit flag → sub metadata → customer mapping), and upserts the entitlement
  row — bypassing webhooks and the idempotency ledger entirely.

14 billing tests pass (9 original + 5 new).

### Remediation for the ⛔ case

1. Promote `develop` → `prod` (DO deploys from the **`prod`** branch,
   `deploy_on_push: true` — merging to `develop` does **not** deploy).
2. Run in prod:
   ```bash
   python manage.py reconcile_subscription sub_1TiX8xAUVVtUs6xlv03usc0s --email admin@kentakin.eu
   ```
3. Verify `GET /api/billing/me` shows the active subscription and `/api/goals/`
   no longer 402s for that user.

## Operational gotchas surfaced

- **Prod admin is hard to reach:** `/admin/` is TOTP-gated (django-otp, local WIP,
  not yet deployed), the DO App Platform web console is effectively unusable
  (frozen websocket + interleaved access logs), and the dev-droplet's DO token is
  read-only (403 on `doctl apps console`/exec). Console-free levers exist via DO
  dashboard env vars consumed by `start.sh` (superuser bootstrap via
  `DJANGO_SUPERUSER_PASSWORD`; `ADMIN_MFA_ENABLED=False` to bypass MFA).
- **Prod deploys from the `prod` branch, not `develop`.**
- **Claude's Stripe MCP is sandbox-only** (`mealPlanner sandbox`) — it cannot see
  or modify live data; live verification must happen in the live dashboard or in
  prod.
- **No test cards in live mode** — `4242…` only works in the sandbox; live
  end-to-end testing means a real (refundable) charge. Prefer the sandbox for
  full checkout-flow testing.

## Lessons

- Confirm **which Stripe mode/account** prod uses *before* reasoning about Stripe
  data — sandbox-only tooling produced a confident but wrong diagnosis.
- Match the **paying account** to the symptom: the 402 was a different user than
  the subscriber. Always pin the user id.
- A webhook **200** does not guarantee the side effect happened — combined with an
  idempotency ledger, a silent failure becomes unretryable. Hence create-if-missing
  handlers + an out-of-band reconcile command.
