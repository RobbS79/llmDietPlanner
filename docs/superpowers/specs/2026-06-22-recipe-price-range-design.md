# Recipe Price Range — Design Spec

**Date:** 2026-06-22
**Status:** Approved (direction delegated to engineering)
**Author:** Robert Soroka + Claude

## Problem & motivation

Today the web surfaces plan cost as a **single whole-plan number** (`~350 Kč/den · na osobu`) plus a hedge. It is honest but thin: one figure, no context, no sense of how rough it is. An internal evaluation (see below) showed the *quality* users actually value is a **credible, contextualized, honestly-rough** cost signal — not more decimal places.

We are pivoting the **unit of pricing (and shopping) from the whole plan to the individual recipe**, and replacing the single number with an honest **from–to range**.

### Why a range, and why these numbers

An evaluation against the real 214-entry price book (`canonical_prices.yaml`) found:

- The gap between **consumed cost** (pro-rated, "the food in the dish") and **whole-pack outlay** (what hits the till) is **bounded and stable at ~1.23–1.32×** across very different baskets — a *known ~20–25% bias*, not chaos.
- Per-portion totals land within a believable band of the Czech Statistical Office figure (~3000 CZK/person/month food ≈ ~700 CZK/person/week), i.e. the model is in the right universe.

A range honestly communicates that bounded uncertainty instead of feigning precision. We use **model B**: center on consumed cost, open the upper bound by the measured overhead factor.

## Target end-state

The **recipe** is the atom of pricing and shopping:

- Each recipe carries a **from–to price range** (recipe total + per-portion).
- Each recipe can produce its **own shopping list** from its ingredients.
- A **meal plan** becomes a roll-up: cost = combined range of its recipes; shopping list = deduped union of recipe lists.
- The current single whole-plan estimate is replaced by a plan-level range — **last**, only after recipe-level pieces are proven, so the live prod headline is never broken mid-rework.

## Decomposition (ordered, each independently shippable)

1. **Recipe price-range engine** *(this spec)* — pure service computing from–to total + per-portion from the book. Foundation; everything depends on it.
2. **Surface range on recipe display + API** — recipe serializer + recipe card / detail / public `/recepty/` pages. First visible "quality output on web"; ships without touching plan generation.
3. **Per-recipe shopping list** — generate/expose a per-recipe shopping list from its ingredients.
4. **Plan roll-up + UI rework** — plan cost = combined recipe ranges; plan list = deduped union; rework PlanView/ShoppingListPage; retire the old whole-plan `EstimatePricer` headline. Done last to protect the live estimate.

Sub-projects 2–4 each get their own spec → plan → implementation cycle.

---

## Sub-project 1: Recipe price-range engine (detailed)

### Responsibility

One pure function: given a recipe's ingredient lines + servings, return an honest from–to cost range in the requested currency, plus coverage metadata. No UI, no DB writes, no LLM. Deterministic and fully unit-testable.

### Interface

```python
# diet_planner/services/recipe_pricing.py

@dataclass(frozen=True)
class RecipeRange:
    low: float            # Σ consumed ingredient costs (whole recipe), in `currency`
    high: float           # low * PACK_OVERHEAD
    per_portion_low: float | None   # low / servings  (None if servings missing)
    per_portion_high: float | None
    currency: str         # 'CZK' | 'EUR'
    priced_count: int     # ingredients that resolved to a book entry & priced
    total_count: int      # non-optional ingredients considered
    confident: bool       # priced_count / total_count >= COVERAGE_MIN

def price_recipe(
    ingredients: list[dict],   # [{name, quantity, unit, canonical?, optional?}]
    servings: int | None,
    *,
    currency: str = 'CZK',
) -> RecipeRange | None        # None if nothing prices at all
```

### Calculation (model B)

For each **non-optional** ingredient line:
1. Resolve slug: `line['canonical']` first, else `resolve_canonical(line['name']).slug` (mirrors [[pricing-catalog-id-resolution]] — canonical travels with the item, name is fallback).
2. Look up the book entry by slug. Unresolved/unknown → counts toward `total_count` but not `priced_count`; contributes 0 cost.
3. Compute the line's **consumed cost** via the shared helper (below), including the piece↔weight bridge already in the pricer.

Then:
- `low = Σ consumed costs * fx`
- `high = low * PACK_OVERHEAD`
- `per_portion_* = low|high / servings` when `servings` is a positive int, else `None`
- `confident = total_count > 0 and priced_count / total_count >= COVERAGE_MIN`
- Return `None` only when `priced_count == 0` (nothing to show).

Constants (module-level, documented):
- `PACK_OVERHEAD = 1.25` — measured consumed→till overhead; tune from real-spend feedback later.
- `COVERAGE_MIN = 0.6` — below this the UI should soften/hide the range.

### Decisions & rationale

- **Pantry-agnostic:** the recipe range counts staples (oil/salt/spices). A public recipe viewer wants "what this dish costs," not "assuming you own oil." This is intentionally different from the plan estimate, which honors user pantry toggles.
- **Optional ingredients excluded** in v1 (rough is the goal; avoids double-counting "nice to have" extras).
- **Rounding lives in the formatter**, not the engine. The engine returns raw floats; display rounding (e.g. nearest 5 Kč on totals, 1 Kč per-portion) is a frontend/serializer concern.
- **FX reused** from the existing pricer's CZK→currency map; the book is CZK.

### Shared line-cost helper (DRY refactor, included here)

Extract the per-line consumed-cost logic currently inside `EstimatePricer._consumed_cost`
(`estimate_pricer.py:150`) into a pure function, e.g.:

```python
# diet_planner/services/pricing_core.py
def consumed_line_cost(entry: dict, qty: float, unit: str,
                       grams: float | None = None) -> float | None:
    """Pro-rated cost of `qty unit` against a book `entry`, with the
    piece<->weight bridge. Returns None when not priceable."""
```

`EstimatePricer._consumed_cost` becomes a thin wrapper (preserving its MAX_PACKAGES
cap and pack-fallback behavior); `price_recipe` calls the same helper. This keeps unit
conversion in one place — the principle that prevented the 238k Kč regression — instead
of forking the math into a second path.

### Error handling & edge cases

- `quantity` non-numeric / ≤ 0 → line not priced (0 cost, counts toward total).
- `servings` missing/≤0 → per-portion fields `None`; recipe total still returned.
- Empty/`None` ingredients → return `None`.
- Unknown unit / dimension mismatch with no piece-weight bridge → line not priced.
- Unknown currency → FX falls back to 1.0 (same as existing pricer).

### Testing (TDD — tests first)

`diet_planner/tests/test_recipe_pricing.py`:
- Known book entries → exact expected `low`, and `high == low * PACK_OVERHEAD`.
- Per-portion = total / servings; `None` when servings missing.
- Coverage: mix of priced + unknown ingredients → correct `priced_count`/`total_count`/`confident`.
- Optional ingredient excluded from totals and counts.
- Piece↔weight bridge line (e.g. "220 g" vs per-`ks` book entry) prices via the shared helper.
- FX: EUR currency scales the CZK book.
- Edge: empty list → `None`; zero/negative quantity → unpriced; zero servings → per-portion `None`.
- Refactor guard: existing `test_estimate_pricer.py` still green after extracting `consumed_line_cost` (no behavior change to the live estimator).

### Out of scope (this sub-project)

API/serializer exposure, any React rendering, per-recipe shopping lists, plan roll-up, and retiring the whole-plan estimate — all are later sub-projects.
