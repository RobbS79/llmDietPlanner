# Drop Store Selection → Rohlík Baseline + On-Demand Discount Price-Map

**Date:** 2026-06-21
**Status:** Approved design, pending implementation plan
**Branch:** `feature/drop-store-selection-discount-map`

## Problem & motivation

Today the user picks a grocery store up front (Onboarding step 5, CreatePlan step 3) and a
`store_mode` (single vs multi-store). That selection then constrains plan generation and
locks pricing to the chosen store. Two problems:

1. **The data can't back it.** Only Rohlík has a real, populated catalog. All other stores
   have ~0 active priced offers (verified 2026-06-20). A multi-store selector the catalog
   can't honor is a price-fabrication surface, not a feature.
2. **Wrong moment for discounts.** Forcing a store choice before the plan exists is backwards.
   Users want a plan first, then to discover where it's cheapest.

## Goal

Remove store selection entirely. Generate plans/recipes/shopping lists **catalog-constrained
to Rohlík** (real ingredients, real baseline prices — preserves the P0 no-fabrication gate).
Make discounts an **opt-in, read-only layer**: on a finished shopping list the user clicks
"check discounts" and sees, per item, where it's on sale and how much they'd save vs the
Rohlík baseline. **The list never changes.**

### Non-goals

- No ingredient-swap / plan-mutating optimization (explicitly rejected — see Decisions).
- No live scraping at click-time (read path is DB-only).
- No deletion of the dormant multi-store optimizer or the `shop`/`store_mode` columns in
  this pass (kept for a smaller, reversible diff).

## Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Discount layer behavior | **Price-map, no recipe change** | User wants price intelligence, not a plan mutator. |
| Click-time data source | **Query DB only** | Fast; freshness handled by a separate daily job. |
| Freshness | **Daily scan** of discount offers + leaflet currentness | Keeps the DB read honest without slow click-time scraping. |
| Generation constraint | **Pin catalog constraint to Rohlík** | Only store with real catalog data; preserves P0 integrity. |
| Baseline price | **Rohlík regular price** | Single, real reference for savings math. |
| Matching | **Strictly by `canonical_id`** | No fuzzy name matching (pricing-integrity rule). No cross-store canonical match → show no discount, never a fabricated one. |

## Design

### 1. Frontend — remove the picker

- **`frontend/src/pages/Onboarding.tsx`**: delete Step 5 "Obchod" (the store-grid step), the
  `/shops/` query, the `shop` field default, and the "Obchod" summary row. Quiz: 5 → 4 steps.
- **`frontend/src/pages/CreatePlan.tsx`**: delete Step 3 "Preferovaný obchod", the
  `store_mode` toggle (Jeden obchod / Více obchodů) and explainer, and the store/mode summary
  rows. Stop sending `shop` / `store_mode` in the create payload.

### 2. Backend — generation pinned to Rohlík

- **`diet_planner/schemas.py`**: make `shop` and `store_mode` optional in
  `DietaryGoalCreateRequest`.
- **`diet_planner/views.py`** (`DietaryGoalCreateView`): default `shop=ROHLIK`,
  `store_mode=single` server-side when absent. Keep persisting to the `DietaryGoal` columns
  (audit; no migration to drop them).
- **`diet_planner/tasks.py`**: generation always uses the Rohlík catalog constraint +
  `PriceResolver(shop=ROHLIK)`. The `mix_cost`/`mix_trips` branch (`CrossStoreOptimizer`)
  becomes **dormant** — unreferenced by the new flow, left in place, not deleted.

### 3. Discount price-map (the new feature)

- **Endpoint:** `GET /goals/<id>/discount-map/` — read-only, no plan mutation.
- **Service:** `discount_price_map(plan)`:
  - For each shopping-list item with a `canonical_id`:
    - baseline = the item's resolved Rohlík price (already on the list).
    - query current `PriceRecord` rows with `source_type=LEAFLET_DISCOUNT` for that canonical
      across all stores (`PriceRecord.objects.current()`), via
      `StoreProduct.canonical_ingredient`.
    - pick the best discounted price; `saving = baseline − discounted`, scaled to the needed
      quantity. Drop non-positive savings.
  - **Output:** per-item `{store, discounted_price, saving}` + a grouped summary
    (e.g. "6 items cheaper at Lidl → save 84 Kč") + total potential savings.
  - Result cached on the plan: new `discount_map` (JSONField) + `discount_map_computed_at`.
- **Reuses** existing `canonical_id` linkage and `PriceRecord` — no new pricing model.
- **Retire** the legacy LLM-swap path: `optimize_plan_discounts_task`,
  `DiscountOptimizationView` (`/optimize-discounts/`), `ApplyDiscountOptimizationView`
  (`/apply-optimization/`), and the `discount_optimization*` fields — wrong shape for this
  feature. (Confirm no other callers before removing.)

### 4. Daily freshness job

- **Management command `scan_discounts`**: refreshes `LEAFLET_DISCOUNT` records (kupi.cz
  aggregator for Lidl/Albert/Kaufland/Penny/Tesco + Rohlík search-scraper sale flags) and
  **expires stale leaflets** so the click-time DB read is honest. Scoped to canonicals that
  appear in active plans (or the full dictionary — TBD in plan).
- **Scheduling (decided):** Celery **beat is disabled in prod** (curation runs via manual DO
  Console). Do **not** re-enable beat. A **DO App Platform scheduled Job** component runs
  `python manage.py scan_discounts` daily (e.g. `0 4 * * *`). Claude wires this via `doctl`
  using `DIGITAL_OCEAN_TOKEN` (both present in the environment) — **no manual dashboard step
  for the user.** Method: pull the **live** app spec (`doctl apps spec get <app-id>`), add the
  Job component to that spec, push it back (`doctl apps update`). **Never** apply the repo's
  `.do/app.yaml` (stale placeholder — would wreck prod). Sequenced **after** the
  `scan_discounts` command exists and is verified, as the final implementation step.

### 5. UX on the shopping list

- **`frontend/src/pages/ShoppingListPage.tsx`**: default view unchanged (list + Rohlík price
  range). Add a **"Zkontrolovat slevy"** button that calls `GET /goals/<id>/discount-map/`.
  Results render as per-item chips (e.g. *"akce u Lidl — ušetříš 12 Kč"*) plus a top
  savings-summary banner grouped by store. Reuse the existing deal-chip rendering.

## Data flow

```
Create plan (no store)  →  generate catalog-constrained to Rohlík  →  shopping list priced at Rohlík baseline
                                                                              │
                                                  user clicks "Zkontrolovat slevy"
                                                                              │
                              GET /goals/<id>/discount-map/  →  discount_price_map(plan)
                                                                              │
                        per canonical_id: current LEAFLET_DISCOUNT across stores vs Rohlík baseline
                                                                              │
                                   per-item chips + grouped savings summary (list unchanged)

[daily]  scan_discounts  →  refresh LEAFLET_DISCOUNT records + expire stale leaflets
```

## Risks / open items

- **Coverage:** non-Rohlík discount data is thin (kupi.cz only). Many items will show no
  discount. Acceptable for v1 — honest emptiness beats fabrication. Coverage improves as the
  daily scan runs.
- **Scheduler wiring** (section 4) is the one unresolved ops decision.
- **Retiring the swap task** must confirm no remaining frontend/API callers before deletion.
- **Quantity scaling** for savings must match the unit logic already used by the resolver to
  avoid mismatched per-unit vs per-package comparisons.

## Testing

- Unit: `discount_price_map` — baseline vs discounted math, quantity scaling, canonical-only
  matching, non-positive-saving exclusion, grouping/summary totals.
- Unit: create-goal defaults `shop=ROHLIK` / `store_mode=single` when omitted.
- Integration: generation still produces a Rohlík-catalog-constrained, fully-priced list with
  no `shop` in the request.
- Frontend: Onboarding is 4 steps; CreatePlan has no store step; "Zkontrolovat slevy" renders
  chips + summary from a mocked discount-map response.
- Command: `scan_discounts` upserts/expires `LEAFLET_DISCOUNT` records as expected.
