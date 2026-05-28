# Pantry Staples + Pro-Rated Pricing — Implementation Plan

## Problem

Plan total includes the **full pack price** of pantry items (salt, olive oil, soy sauce, etc.) even when the recipes only use a marginal amount. A 1-day plan shows "≈1000 CZK" largely because a 150 CZK bottle of olive oil is added to the basket for 10 ml of use.

## Goal

1. **Pro-rate** pantry-staple costs by the fraction actually consumed (10 ml of a 500 ml bottle = 3 CZK, not 150).
2. **Group** staples separately in the shopping list UI so users see "pantry restock" prices vs. real per-plan cost.
3. Plan total reflects the realistic cost of *executing this plan*, assuming a typical kitchen has the staples (with full-pack prices still visible for users who need to restock).

## Current state (verified)

- Single cost flow: `diet_planner/tasks.py:1494–1579` loops shopping-list items, calls `calculate_package_aware_price()` (`tasks.py:1189+`), sums into `total_sum`, writes `DietaryPlan.total_price` at line 1598.
- `CanonicalIngredient.is_pantry_staple` exists (`diet_planner/models/catalog.py:97`, indexed) with `estimated_price_czk`/`estimated_price_eur` fallback fields — **but the table is empty**. Migration 0016 created the schema; nothing seeds rows.
- No bridge today between LLM-generated shopping-list line names (free text) and `CanonicalIngredient`.
- Shopping-list rows are JSON dicts with `ingredient`, `quantity`, `unit`, `price`, `price_total`, `price_source`, `estimated`, `package_size`, `currency`, `matched_product_name`. No `canonical_ingredient_id`, no `is_pantry_staple`.
- All unit conversion to base units (g/ml/ks) already lives inside `calculate_package_aware_price` (`tasks.py:1296–1318`) — pro-rating piggybacks on that.

## Decision points (resolve before coding)

### D1. Staple identification — DB lookup vs. keyword set

Two viable approaches:

- **A. Canonical lookup**: seed `CanonicalIngredient` with ~60 staples + CZ/SK names + aliases, match shopping-list `ingredient` name → canonical row → read `is_pantry_staple`. Aligns with the multi-store catalog architecture. Requires seed data + alias coverage.
- **B. Keyword set**: hardcoded Python set of staple keywords (EN/CZ/SK), no DB lookup. Ships in an hour. Doesn't reuse the catalog schema; duplicates work the catalog migration is heading toward.

**Recommendation: A.** The catalog is the long-term home for this; doing it in code now creates a parallel source of truth we'd rip out in a month. Cost is ~60 rows in a data migration with a name + cs/sk translation + 2–3 aliases each.

### D2. Pro-rated math for sub-package amounts

For staples, replace the existing `ceil(required / package_size) × price` with raw `(required / package_size) × price`. Existing base-unit conversion at `tasks.py:1296–1318` still applies.

Edge: if the canonical ingredient has `estimated_price_czk` set but no matched store product, use that as the per-pack price for the fraction calculation.

### D3. Plan total — include or exclude pantry?

- **Option 1**: Plan total = groceries + pro-rated pantry. Real per-plan cost, all-in.
- **Option 2**: Plan total = groceries only. Pantry shown as separate "restock" line.

**Recommendation: Option 1.** Pro-rated pantry is small (typically <5% of total) but real — it's what running this plan actually costs. Headline cost stays honest. The shopping list still groups the lines separately for shopability.

## Seed data — the staple set

≈60 canonical ingredients to seed with `is_pantry_staple=True`.

**Oils & fats (6)**: olive, sunflower, vegetable/rapeseed, coconut, sesame, butter-ghee
**Vinegars (5)**: white, apple cider, balsamic, rice, wine
**Salt & pepper (4)**: table salt, sea salt, black pepper, white pepper
**Dried spices/herbs (~18)**: paprika (sweet/hot/smoked), cumin, oregano, basil, thyme, rosemary, bay leaves, cinnamon, nutmeg, turmeric, ginger powder, chili/cayenne, curry powder, garlic powder, onion powder, coriander, caraway (kmín)
**Condiments/bottled sauces (~12)**: soy sauce, dijon mustard, yellow mustard, honey, ketchup, Worcestershire, hot sauce (Tabasco/sriracha), fish sauce, oyster sauce, BBQ sauce, tomato paste/purée, maple syrup
**Baking/dry goods (~9)**: plain flour, sugar (white/brown/powdered), baking powder, baking soda, dry yeast, cornstarch/potato starch, cocoa powder, vanilla extract
**CZ-specific (~4)**: Vegeta, bujón/stock cubes, horseradish (křen), bramborový škrob

**Intentionally NOT staples** (used in meaningful per-meal portions, or perishable):
butter (as block), milk, cream, cheese, yogurt, rice, pasta, oats, lentils, garlic (fresh), onion, ginger root, lemon/lime, bread, eggs, nuts/seeds.

## Implementation

### Phase 1 — Seed canonical staples (data migration)

**File**: `diet_planner/migrations/0021_seed_canonical_staples.py` (new)

- Forward op: `RunPython` that creates `CanonicalIngredient` rows for the ~60 staples above.
- Each row: `name` (EN), `name_cs`, `name_sk`, `slug`, `category`, `default_unit`, `typical_unit`, `typical_package_sizes`, `is_pantry_staple=True`, `estimated_price_czk`, `estimated_price_eur`.
- Also seed 2–3 `IngredientAlias` rows per canonical ingredient (lowercase variants, common misspellings, CZ/SK forms the LLM might emit — "sůl", "salt", "kuchyňská sůl").
- Reverse op: delete by slug list (so rollback is clean).

### Phase 2 — Name → canonical lookup helper

**File**: `diet_planner/services/canonical_lookup.py` (new, ~40 lines)

```python
def resolve_canonical(name: str) -> CanonicalIngredient | None:
    """Resolve a free-text ingredient name to a CanonicalIngredient via
    direct name match (any of name/name_cs/name_sk, case-insensitive),
    then IngredientAlias. Returns None if no match.
    """
```

Cached for the duration of a request (lru_cache or simple dict on the service).

### Phase 3 — Bridge + pro-rated pricing in the sum loop

**File**: `diet_planner/tasks.py`

- Inside the loop at line 1494, after `validate_shopping_item`:
  ```python
  canonical = resolve_canonical(ingredient_name)
  validated_item['canonical_ingredient_id'] = canonical.id if canonical else None
  validated_item['is_pantry_staple'] = bool(canonical and canonical.is_pantry_staple)
  ```
- Modify `calculate_package_aware_price` (line 1189+) to accept an `is_staple` flag. When True: skip the `ceil` step, return raw `(required_base / package_size_base) × price_per_package`.
- At the sum site (line 1539 and sibling branches at 1547/1551/1561/1576):
  ```python
  if validated_item['is_pantry_staple']:
      validated_item['pantry_pack_price'] = base_price       # full bottle/bag
      validated_item['fraction_used'] = float(required_base / package_size_base)
      pantry_sum += calculated_price
  else:
      total_sum += calculated_price
  ```
- Final total stored at line 1598 stays inclusive: `total_price = total_sum + pantry_sum`.

### Phase 4 — Persist pantry breakdown on `DietaryPlan`

**File**: `diet_planner/models/core.py`

- Add `pantry_price = DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)` to `DietaryPlan`.
- Schema migration `0022_dietaryplan_pantry_price.py`.
- Populate at the `DietaryPlan.objects.create(...)` call (`tasks.py:1594`).

### Phase 5 — Frontend rendering

**Files**: shopping-list and plan-summary components (likely under `frontend/src/.../ShoppingListPage.jsx` and the plan summary card — confirm paths during implementation).

- Plan total: unchanged number, but expose `pantry_price` so the UI can show a small "(incl. ~X CZK pro-rated pantry)" note.
- Shopping list: render two sections:
  - **Groceries** — items where `is_pantry_staple=false`. Each row shows full price (current behavior).
  - **Pantry — fractional use** — items where `is_pantry_staple=true`. Each row shows:
    - amount used + pro-rated price ("Olive oil — 10 ml · 3 CZK your share")
    - full pack price as secondary info ("500 ml bottle 150 CZK if you need to restock")
- Optional toggle: "I already have all pantry items" hides the pantry section visually and subtracts `pantry_price` from the displayed total. Pure frontend, no backend change.

### Phase 6 — Tests

- Unit test: `calculate_package_aware_price(is_staple=True)` returns the raw fraction × price, no ceil.
- Unit test: `resolve_canonical` matches direct name, alias, and is case-insensitive; returns None for unknown.
- Integration test: a synthetic shopping list with mixed staples + groceries produces correct `total_price` and `pantry_price` on `DietaryPlan`.
- Snapshot test: a known meal plan that previously totaled X CZK now totals X − (full pack prices) + (pro-rated prices) within tolerance.

## Open questions

- **Alias coverage.** LLM ingredient names are unpredictable. Are 2–3 aliases per staple enough, or do we need a fallback heuristic (substring/normalized-token match) for un-aliased forms? Recommend: ship with strict alias matching, log unmatched staples for a week, add aliases based on real misses.
- **`estimated_price_czk` source.** For the seed migration, where do reference prices come from — manual entry from a single store snapshot, or an existing data source? Manual entry from current Rohlík prices is fine for v1.
- **Bouillon cubes.** Per-cube usage (1 cube of a 10-pack per recipe) is well-modeled as `package_size=10 ks` + fractional pricing. Confirms the staple treatment works for `ks`-unit items, not just `g`/`ml`.
- **Existing plans.** Old `DietaryPlan` rows have no `pantry_price`. Either leave null (UI tolerates) or run a one-off recompute. Recommend: leave null; users care about new plans.

## Rough effort

- Phase 1 (seed): half a day, mostly typing translations and aliases
- Phase 2–4 (backend code + migrations): half a day
- Phase 5 (frontend): half a day
- Phase 6 (tests): 2–3 hours

≈ 2 days total for one engineer. No external dependencies. No deploy coordination needed (App Platform handles migrations).
