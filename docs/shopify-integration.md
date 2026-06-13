# Shopify Integration — Reference

**App:** `shopifyin/` · **Status:** implemented but **not mounted** (see [§7](#7-known-gaps--current-state)) · **Last verified against code:** 2026-06-10

This is the canonical reference for how Shopify payments are wired into the LLM Diet Planner today. It documents the code **as it actually is**, not as planned.

Related docs (not duplicated here):
- `shopifyin/SHOPIFY_SETUP_GUIDE.md` — step-by-step Shopify Admin UI setup (creating the custom app, getting tokens).
- `shopifyin/PARTNERS_DASHBOARD_SETUP.md` — alternative setup via the Shopify Partners dashboard.
- `docs/shopify-subscription-integration-plan.md` — **forward-looking plan** to move from one-time per-goal payment to recurring subscriptions. Not yet implemented.

---

## 1. What the integration does

The current model is **one-time, per-goal payment**: a user creates a `DietaryGoal`, pays for that specific goal through a Shopify-hosted checkout, and a Shopify webhook flips the goal to paid and triggers meal-plan generation.

End-to-end flow:

1. Backend creates a Shopify **cart** (via Storefront Cart API) for the meal-plan product variant, embedding the `goal_id` as a custom attribute.
2. User is redirected to the Shopify-hosted `checkoutUrl` and pays.
3. Shopify fires the **`orders/paid`** webhook → `shopify_order_paid_webhook`.
4. The webhook verifies the HMAC, extracts `goal_id`, flips the `DietaryGoal` to `PAYMENT_PENDING`, and enqueues `process_dietary_goal_task` (Celery) to generate the plan.
5. **`orders/cancelled`** → `shopify_order_cancelled_webhook` marks the goal `FAILED`.

> ⚠️ Despite the name, `ShopifyService.create_checkout()` uses the modern **Cart API** (`cartCreate` mutation), not the deprecated Checkout API. Variable/field names like `checkout_id`, `checkout_token`, `checkout_url` are kept for backward compatibility; the underlying object is a Shopify **cart**, and `checkout_token` is the cart GID's last path segment.

---

## 2. Components

| File | Responsibility |
|------|----------------|
| `shopifyin/models.py` | `ShopifyStore`, `ShopifyCheckout`, `ShopifyProduct` |
| `shopifyin/shopify_service.py` | `ShopifyService` — Storefront GraphQL client (cart create, get checkout, product search) |
| `shopifyin/views.py` | DRF API views (checkout create/status/list, product list, admin test/debug) |
| `shopifyin/webhooks.py` | `orders/paid` and `orders/cancelled` handlers + HMAC verification |
| `shopifyin/urls.py` | URL patterns (**currently not included by the project — see §7**) |
| `shopifyin/serializers.py` | Request/response serializers |
| `shopifyin/admin.py` | Django admin for the three models |

The `goal_id` linkage lives on `diet_planner` `DietaryGoal`: `shopify_checkout_id`, `shopify_order_id`, `payment_confirmed_at`, and statuses `AWAITING_PAYMENT` / `PAYMENT_PENDING` / `REFUND_ELIGIBLE` (`diet_planner/models/core.py`).

---

## 3. Data model

### `ShopifyStore`
Store config with **encrypted** credentials (`encrypted_model_fields`, requires `FIELD_ENCRYPTION_KEY`):
- `store_domain` (e.g. `mealprep-9693.myshopify.com`), `storefront_access_token` (encrypted).
- Optional encrypted `admin_api_key`, `admin_api_secret`, `webhook_secret`.
- `meal_plan_variant_id` — the Shopify ProductVariant GID sold as the meal-plan product.
- `is_active` — the views pick the first active store when no `store_id` is given.
- Properties: `storefront_api_url` / `admin_api_url` → pinned to API version **`2025-01`**.

### `ShopifyCheckout`
Tracks a cart/checkout session per user. Key fields: `checkout_id` (cart GID, unique), `checkout_token`, `checkout_url`, `status` (`created`/`pending`/`completed`/`expired`/`cancelled`), `total_price`, `currency` (default `USD`), `metadata` (JSON, holds `goal_id`), `order_id`, `order_number`.

### `ShopifyProduct`
Optional cache of products (`store` + `variant_id` unique). Populated on demand; not auto-synced.

---

## 4. API endpoints

All under the `shopifyin` app, intended to mount at `/api/shopify/` (see §7 — **not currently mounted**). User endpoints require JWT auth; test/debug require admin.

| Method | Path | View | Auth | Purpose |
|--------|------|------|------|---------|
| POST | `checkouts/` | `ShopifyCheckoutCreateView` | user | Create cart, return `checkout_url` |
| GET | `checkouts/<id>/` | `ShopifyCheckoutStatusView` | user | Get status; lazily syncs from Shopify |
| GET | `checkouts/list/` | `ShopifyCheckoutListView` | user | List user's checkouts (filter `status`, `limit`, `offset`) |
| GET | `products/` | `ShopifyProductListView` | user | List cached products |
| GET | `test/` | `ShopifyTestConnectionView` | admin | Diagnose store config + validate `meal_plan_variant_id` by test-creating a cart |
| POST | `webhooks/order-paid/` | `shopify_order_paid_webhook` | HMAC | Shopify `orders/paid` |
| POST | `webhooks/order-cancelled/` | `shopify_order_cancelled_webhook` | HMAC | Shopify `orders/cancelled` |

> Note: `ShopifyDebugView` exists in `views.py` (admin model-count check) but has **no URL route**.

### Create checkout — request/response

```jsonc
// POST /api/shopify/checkouts/
{
  "store_id": 1,                                          // optional; defaults to first active store
  "variant_ids": ["gid://shopify/ProductVariant/123"],
  "quantities": [1],
  "email": "user@example.com",                            // optional; falls back to request.user.email
  "metadata": { "goal_id": 1 }                            // becomes Shopify cart line attributes
}
```
```jsonc
{
  "status": "success",
  "data": {
    "checkout_id": 1,                                     // local ShopifyCheckout PK
    "checkout_url": "https://...myshopify.com/cart/c/...",
    "checkout_token": "...",
    "total_price": "29.99",
    "currency": "USD"
  },
  "error": null
}
```
The frontend redirects the browser to `data.checkout_url`.

---

## 5. Webhooks

Both handlers are `@csrf_exempt @require_POST`.

**`orders/paid`** (`shopify_order_paid_webhook`):
1. Parses JSON; resolves the `ShopifyStore` by matching `X-Shopify-Shop-Domain` against `store_domain` (active only).
2. **HMAC-SHA256 verification is mandatory** — base64 of `HMAC(webhook_secret, raw_body)` compared to `X-Shopify-Hmac-Sha256` via `hmac.compare_digest`. Missing/failing → 401.
3. Ignores orders not in `financial_status` `paid`/`partially_paid`.
4. Extracts `goal_id` from `note_attributes` → `custom_attributes` → line-item `properties` (`_extract_goal_id`).
5. Inside `transaction.atomic()` with `select_for_update()` (idempotent): if the goal is still `awaiting_payment`/`pending`/`payment_pending`, sets `shopify_order_id`, status `PAYMENT_PENDING`, `payment_confirmed_at`; updates the matching `ShopifyCheckout` to `completed`.
6. After commit, enqueues `process_dietary_goal_task.delay(goal.id)`. If enqueue fails → goal set to `REFUND_ELIGIBLE` with a support message.

**`orders/cancelled`** (`shopify_order_cancelled_webhook`): finds the `ShopifyCheckout` by `order_id`, reads `goal_id` from its `metadata`, and marks the goal `FAILED` if still unpaid. ⚠️ This handler does **not** verify HMAC.

---

## 6. Configuration & setup

1. **Create the Shopify custom app** and get a Storefront API token — follow `shopifyin/SHOPIFY_SETUP_GUIDE.md`. Required scope: `unauthenticated_write_checkouts`; optional `unauthenticated_read_product_listings` / `_inventory`.
2. **Env:** `FIELD_ENCRYPTION_KEY` must be set (credentials are encrypted at rest). `shopifyin` is already in `INSTALLED_APPS` and has a logger configured (`settings.py`).
3. **Django admin → Shopify Stores → Add:** name, `store_domain`, `storefront_access_token`, `meal_plan_variant_id`, `webhook_secret`, `is_active`.
4. **Register webhooks in Shopify** pointing at `…/api/shopify/webhooks/order-paid/` and `…/order-cancelled/`, using the same secret stored in `webhook_secret`.
5. **Verify** with `GET /api/shopify/test/` (admin) — confirms store config, API connectivity, and that `meal_plan_variant_id` can produce a cart.

---

## 7. Known gaps / current state

- **URLs are not mounted.** Neither `llm_diet_planner_project/urls.py` nor `diet_planner/urls.py` `include()`s `shopifyin.urls`. As written, **every endpoint and webhook above returns 404.** To activate, add e.g. `path("api/shopify/", include("shopifyin.urls"))` to the project urlconf.
- **No frontend usage.** No references to these endpoints exist under `frontend/src` — there is no "Buy now" UI calling `checkouts/`.
- **`orders/cancelled` skips HMAC verification** (unlike `orders/paid`).
- **`ShopifyDebugView` has no route.**
- **README is stale** — `shopifyin/README.md` describes the deprecated Checkout API and predates the webhook/goal-payment flow. Prefer this document.
- **Per-goal, not subscriptions.** Recurring billing is only a plan: see `docs/shopify-subscription-integration-plan.md`.
