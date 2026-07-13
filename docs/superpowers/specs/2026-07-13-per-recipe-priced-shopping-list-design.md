# Per-Recipe Priced Shopping List + Honest Price Range — Design Spec

**Date:** 2026-07-13
**Status:** Approved design (lean delegated execution; no formal implementation plan)
**Origin:** Phase I (Pilot) pre-flight audit item P0 #2 — the landing sells "nákupní seznam s reálnými cenami" but the app has no shopping list and no prices. Close the landing↔product credibility gap before the FB/IG campaign.

## Goal

Deliver a **per-recipe priced shopping list** with an **honest from–to price range**, backed by a **trustworthy price book**, and rewrite the landing so its price promise matches what ships. Catalog-constrained / official-data prices only — never LLM price estimates, never name-matched live pricing.

## Key finding (why this is smaller than it looks)

The "model B" engine (`diet_planner/services/recipe_pricing.py::price_recipe`) is **already wired** and ships `{low, high, per_portion_low/high, currency, confident}` on every recipe API response (`serializers.py::RecipeSerializer.get_price_range`). Only the **frontend** is switched off: `frontend/src/lib/pricing.ts::getRecipeRange()` is hard-stubbed to `return null`. So the range is mostly a frontend un-stub. The real work is **trusting the underlying prices**.

## The price-trust problem (Component 1 — the gate)

`diet_planner/data/canonical_prices.yaml` (231 entries) was auto-seeded from **catalog medians** and **never audited**. Medians are polluted by premium/marinated SKUs. Evidence: `chicken-breast` = 350 Kč/kg is **3.2× `chicken-thigh`** (110 Kč/kg) when breast is normally ~1.5× thigh; real Rohlík basic breast is ~150–180 Kč/kg. Most entries rest on ~6 samples; some ≤2. There is **no validation**. Cross-checking the book against the catalog is circular (same polluted source).

**Hard rule:** no price is surfaced until it is `verified`. A wrong number on a receipt-styled page is worse than none.

### Tiered price sourcing (replaces "scrape and average")

| Tier | Source | Covers | Role |
|---|---|---|---|
| 1 | **ČSÚ dataset 012052** — official monthly avg consumer prices (open data, VDB), ~33 CPI-basket staples, Kč/unit, 2010+ | the staples that drive ~90% of recipe cost | **primary anchor**, `verified` |
| 2 | **Rohlík / Košík** basic-SKU median (existing Rohlík scraper) | mid-tail ČSÚ skips (mozzarella, specific produce, packaged) | fill gaps |
| 3 | **Wholesale × category gross margin × food VAT (12% CZ)** | everything / bands | audit plausibility **bands** + long-tail estimate |

Notes: ČSÚ = national average, monthly — for an honestly-labeled *estimate*, a national average is more defensible than one store's SKU. Eurostat HICP is indices only (inflation), usable to age prices forward, not to set them. All sources open-licensed.
Sources: ČSÚ 012052 (csu.gov.cz open data), Eurostat HICP.

### Component 1 deliverables
- `audit_price_book` management command: flags suspects via **category bands** (per-category Kč/kg — spices legitimately hit thousands), **ratio sanity** (intra-family, e.g. breast vs thigh 1.3–1.8×), **thin-sample** (≤2). Ranked report, staples first. Re-runnable gate (same spirit as the existing portion-plausibility gate).
- Corrected `canonical_prices.yaml`: staples set from ČSÚ (Tier 1), mid-tail from scrape (Tier 2), long tail estimated/kept (Tier 3). Each entry gains **`verified: true|false`** and a `source` tag.
- **A before/after price diff report** for human approval. **The agent does NOT commit prices** — the human approves the diff first.

## Component 2 — Per-recipe priced shopping list (B)

**Backend (small):** extend the pricing path to return **per-line** consumed cost + a `priced`/`verified` flag per ingredient, and re-expose `priced_count`/`total_count` (serializer currently drops them). Reuses `consumed_line_cost` — no new price math.

**Frontend:** un-stub `getRecipeRange()`; evolve `RecipeIngredients.tsx` into the priced list — verified lines show `~X Kč`, unverified/unpriced show **"bez ceny"**, deal lines keep the **SLEVA** tag, footer shows **from–to total + coverage** ("6 z 8 surovin oceněno"). Portion stepper stays and rescales prices live. Appears on **both** the public `/recepty/:id` and the in-app recipe page.

**Honesty gating:** if verified coverage < `COVERAGE_MIN` (0.6), show per-line prices but **suppress the headline total** rather than print a misleading range. Guard test: an unverified canonical must never render a price.

## Component 3 — Landing re-alignment

Rewrite hero + supporting copy (`frontend/src/pages/Landing.tsx`) to match B. Walk-backs:
- **Weekly total (1 247 Kč receipt mock)** → per-recipe honest range; receipt visual shows one recipe's priced list with a from–to, not a fabricated weekly total.
- **Store choice ("vyberte oblíbený obchod")** → removed (store selection is gone; Rohlík baseline).
- **Savings ("ušetřil 400 Kč")** → soften to the real deals layer ("N surovin ve slevě"); no fabricated savings math.
- **Print/export** → drop (not built).
- Headline "Víte, co budete jíst i kolik to stojí" can stay — B makes it true at recipe level.
- Czech copy authored by Claude with EN gloss for review (per project CZ-copy workflow); before/after mocked in the visual companion for sign-off.

## Out of scope (YAGNI)
Plan-level weekly aggregate (option C), store selection, print/export, savings math, LLM price estimation. Dead whole-plan modules (`shopping_list.py`, `price_resolver.py`, `cross_store_optimizer.py`) left in place — out of critical path.

## Execution model (lean harness)
- No formal implementation plan. Delegated agents per component; parent coordinates + verifies on prod.
- **Model per task:** reasoning-strong model (Opus/Sonnet) for Component 1 (numeric correctness); Fable 5 for Component 3 (Czech copy).
- **Non-negotiable gate:** human approval of the Component-1 price diff before any price reaches prod.
- Prod deploys from the `prod` branch; local catalog is empty (Component 1 works from the repo YAML + ČSÚ, not the DB).

## Testing
Unit tests for audit rules + ratio checks; per-line pricing serializer test; coverage-gating render test; guard test that unverified canonicals never render a price.
