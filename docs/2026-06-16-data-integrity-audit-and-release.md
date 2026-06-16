# Data-Integrity Audit, Restriction-Enforcement Completion & Prod Release — 2026-06-16

**Status:** Shipped to prod (deploy `00e2c720`, ACTIVE 6/6) and verified live.
**Branch flow:** `feature/restriction-enforcement` → `develop` (PR #18, merge `36e95fb`) → `prod` (merge `9bacaa4`).

This note records (1) the completion of the restriction-enforcement / shopping-list-parity work, (2) a data-integrity audit triggered by the question *"can mocked/fabricated plans, recipes, ingredients, or prices reach a paying user?"*, (3) the fixes that came out of it, and (4) the production deployment.

---

## 1. Question that started it

> Can mocked plans, recipes, ingredients, shopping lists, or items reach an actual prod user as something they pay for?

Short answer: **test mocks cannot** (they live only in `*/tests/`, never imported by app code). The audit did, however, surface real issues worth fixing — dead placeholder code, a missing catalog pre-filter, no estimated-price labeling, and no empty-plan guard.

---

## 2. Audit findings

### 2.1 Mocks are test-only
`grep` for `unittest.mock` / `MagicMock` / `monkeypatch` / `@patch` across `diet_planner/`, `billing/`, and the project package returns matches **only under `*/tests/`**. Test doubles (Gemini API, Stripe, pricing seams) are injected by the pytest runner; production code never imports them.

### 2.2 What a paying user actually receives

| Data | Source in prod | Fabrication risk |
|---|---|---|
| Meal plans / recipes | Gemini-generated (both paths). Curated real-recipe overlay active (`RECIPE_GROUNDING_ENABLED=true`). | AI-generated; coherence judge is advisory. |
| Prices — **catalog path** (prod default) | DB-resolved via `PriceResolver`, each item carries a source label. | Low — "zero LLM price fabrication." |
| Prices — **legacy path** | Gemini extracts from scraped leaflet HTML (with a source-evidence hallucination guard) **or** `estimate_product_price()` guesses from general knowledge. | The estimate path is true fabrication (no source grounding). |

**Prod runs the catalog path by default** (`CATALOG_CONSTRAINED_GENERATION`). The legacy/estimated-price path is still reachable via: catalog fallback when a store has `< 10` products, the Shopify webhook (likely dormant — billing moved to Stripe), and the `retry_goals` command.

### 2.3 Dead placeholder in production code
`generate_mock_llm_response()` (`diet_planner/tasks.py`) returned a hardcoded fake plan ("Greek Yogurt", "Grilled Chicken Salad"). Confirmed **uncalled** (grep), so it never reached a user — but it was a landmine. Removed.

### 2.4 Prod config posture (verified against the live `squid-app` DO spec)
- `CATALOG_CONSTRAINED_GENERATION` was **not set** → prod relied on the `settings.py` default `True`. Now **explicitly pinned `=true`** in the DO dashboard (deployment ACTIVE).
- `RECIPE_GROUNDING_ENABLED=true`, `GEMINI_MODEL=gemini-2.5-flash`.
- ⚠️ `.do/app.yaml` in the repo is **stale/orphaned** (app name `llm-diet-planner`, 22 env keys; live `squid-app` has 33+ and is dashboard-managed). Editing it does **not** affect prod.

---

## 3. Changes shipped this release

| Commit | Change |
|---|---|
| `660d9be` | test(restrictions): repair-loop unit coverage + unsatisfiable-goal E2E |
| `e2e6f97` | **fix(restrictions): filter catalog by exclusions in catalog task (Task 12 gap)** |
| `d810eec` | test: `get_or_create` for seeded stores in pricing/leaflet tests (pre-existing collision) |
| `e8f6c82` | chore(tasks): remove dead `generate_mock_llm_response` placeholder |
| `651a8ad` | **feat(plan-view): per-item "odhad" badge for estimated prices** |
| `0df4b67` | **fix(tasks): guard against shipping an empty/degenerate plan as COMPLETED** |

### 3.1 Task-12 catalog filter gap (`e2e6f97`)
`process_dietary_goal_catalog_task` built the LLM catalog via `build_catalog_for_prompt(goal)` with **no `exclusions`**. After the Task-5 refactor, that method only filters when handed a resolved restriction set — so the catalog shown to the LLM still listed forbidden products (e.g. chicken for a vegetarian). The system-prompt block + repair loop still kept the *final* plan compliant, but the "constrain the LLM to allowed products" guarantee was bypassed (wasted tokens, extra repair churn). Fix: resolve restrictions once (Phase 0) and thread the same set into the catalog filter and generation.

### 3.2 Empty-plan guard (`0df4b67`)
A truncated/garbage LLM response (zero days, or days with no ingredients) was turned into a `DietaryPlan` and marked **COMPLETED** — a paying user receiving an empty plan. `_assert_plan_has_content()` now runs in **both** task paths after recipe grounding; it raises on an empty plan, routing into each task's failure handler (FAILED, or REFUND_ELIGIBLE when payment is pending; retried up to `max_retries` for a transient hiccup) — never COMPLETED.

### 3.3 Estimated-price transparency (`651a8ad`)
`PriceResolver` already labels each item with `estimated` (bool) + localized `source_detail`, and the serializer exposes them, but the frontend rendered estimated and verified prices identically. `PlanView` now shows a small amber **"odhad"** (estimate) tag next to the price when `item.estimated`, with `source_detail` as the tooltip. Verified prices are unchanged.

---

## 4. Verification

- **Full `diet_planner` suite: 161 passed** in Docker (pytest-django) before merge.
- Frontend `tsc --noEmit`: clean.
- Post-deploy live checks: `https://eatalnicek.eu/` → HTTP 200; `https://eatalnicek.eu/api/billing/plans/` → HTTP 200 with real tier data (Standard 99 CZK / Premium 199 CZK).

---

## 5. Deployment record

1. PR #18 (`feature/restriction-enforcement` → `develop`) — MERGEABLE/CLEAN, no CI gate — merged (`36e95fb`).
2. `develop` → `prod` merge `9bacaa4` (two parents: prod `2f0e6fc` #17 + develop `36e95fb`). Clean, no conflicts.
3. Push to `prod` → `deploy_on_push` triggered deploy `00e2c720`: BUILDING → DEPLOYING → **ACTIVE 6/6** (rolling, 2 instances).
4. Separate prior deploy `6dc3c23d` ("app spec updated") delivered the `CATALOG_CONSTRAINED_GENERATION=true` env pin — ACTIVE.

**This was a code-only deploy — no new migrations** (`makemigrations --check` → "No changes detected"; `requirements.txt` unchanged). Billing was already live in prod prior to this release; an earlier pre-flight that suggested "first-time billing + 5 migrations" was computed against a stale local `prod` ref and was incorrect.

---

## 6. Residual risks & follow-ups

- **Legacy estimated-price path** still reachable (thin-catalog fallback, Shopify webhook, `retry_goals`). Now labeled "odhad" where prices render. Consider routing the fallback through `PriceResolver` too, or surfacing the estimate label on `ShoppingListPage` (currently only `PlanView`).
- **`.do/app.yaml` drift** — repo file no longer represents the live app. Either delete it or reconcile it with the live `squid-app` spec to avoid future confusion.
- **Local doctl token is read-only** — can read specs/deployments but cannot `apps update` (403). Live env changes must go through the DO dashboard or a write-scoped token.
- Pre-existing seed-vs-`setUp` test collisions were fixed in the affected files; if other tests create seeded `GroceryStore` codes, apply the same `get_or_create` pattern.
