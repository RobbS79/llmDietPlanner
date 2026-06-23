# Recipe Deals Headline — Design Spec

**Date:** 2026-06-23
**Status:** Draft for review
**Author:** Robert Soroka (with Claude)

## Problem

The per-recipe absolute price-range feature (shipped 2026-06-23) fabricates
numbers we can't stand behind. Root cause: `consumed_line_cost` charges a whole
pack for any unit it can't convert, so e.g. "1 lžička salt" → 184.90 CZK, and a
simple peanut soup reads **784 CZK**. One absurd number destroys trust — a
genuine reason a user abandons the service.

We are pivoting away from showing absolute prices. Instead, surface **currently
active discounts** from leaflets/web for the ingredients in a recipe's shopping
list. Headline = how many of a recipe's ingredients are on sale this week.

## Goals

- Stop displaying fabricated absolute prices immediately.
- Show, per recipe, **only genuinely active** deals on its ingredients:
  *"N z M surovin ve slevě tento týden"* + the list of deals (shop + product +
  leaflet link).
- Absolute integrity on the ACTIVE flag — see below.

## Non-Goals (this phase)

- No CZK savings figure. `discount_percentage`/`original_price` are 0 in the
  data, and leaflets carry no comparable unit, so a savings number would be
  fabricated. Deferred to a later phase.
- No removal of the pricing engine — it stays dormant in the codebase for the
  later savings phase.
- No change to the discount scraper (`scan_discounts`) — it is healthy
  (validated: last run 2026-06-23 02:05, 312 active discounts).

## The ACTIVE rule (hard requirement)

A deal is ACTIVE **iff** all hold:

1. It is a persisted `PriceRecord` with `source_type = LEAFLET_DISCOUNT`
   (real scraper/API output — nothing fabricated, mocked, or planned).
2. `valid_from <= now` — already started (excludes future-dated/planned leaflets).
3. `valid_until > now` and `valid_until IS NOT NULL` — not expired, real end date.
4. It resolves to a canonical ingredient (via `store_product.canonical_ingredient`).

Implementation: `PriceRecord.objects.current().filter(
source_type=LEAFLET_DISCOUNT, valid_until__isnull=False)`. `current()` already
enforces (2)+(3-not-expired); we add the non-null end date.

**Why it matters (validated on prod 2026-06-23):** of 374 leaflet discounts,
**62 are future-dated (planned)** — a loose `valid_until > now` filter would
wrongly show them as live. The strict window drops them with zero coverage loss.

## Validated data facts (prod, 2026-06-23)

- `LEAFLET_DISCOUNT` PriceRecords: 374 total, **312 strictly active**, 0 null-end.
- Active discount canonicals: **41** (chicken-breast, eggs, butter, cheese,
  carrots, banana, mango, lemons, …).
- Coverage over the 18 public recipes: **88.9%** have ≥1 active deal,
  avg **3.06** deals/recipe, 61% have ≥3.
- `STORE_REGULAR` PriceRecords: 3,491 (baseline available for later savings phase).

## Design

### Phase 1(a) — Hide the absolute price

- Frontend: `getRecipeRange` (and the detail price card + grid inline) stop
  rendering the absolute range. Cleanest: gate the price-range UI behind a flag
  / remove the components, leaving `pricing.ts` types + the backend engine in
  place (dormant). No backend removal.
- Effect: the 784 CZK number disappears under every scenario.

### Phase 1(b) — Deals headline

**Backend service** `diet_planner/services/recipe_deals.py`:

```
recipe_deals(ingredients) -> {
  matched: int,           # distinct recipe ingredients with an active deal
  total: int,             # priceable (non-optional) ingredients considered
  deals: [ { ingredient, canonical, shop, display_name, source_url,
             valid_until } ]   # one per matched ingredient (deterministic pick:
                                # soonest-expiring active deal, tie-break by shop)
}
```

- Resolve each ingredient → canonical slug (reuse `resolve_canonical`, same as
  the pricing path).
- Build the active-deal set once via the ACTIVE query above, indexed by
  canonical slug.
- Match recipe canonicals against it; dedupe to one deal per ingredient.
- Returns `matched = 0` cleanly (headline simply not shown).

**Serializer:** add `deals` (`SerializerMethodField`) to `RecipeSerializer`,
calling `recipe_deals(obj.ingredients)`. Keep `price_range` in the serializer
for now (dormant) or drop it from the payload — decide in the plan.

**Frontend:** replace the price card/inline with a deals headline:
- Headline: *"{matched} z {total} surovin ve slevě tento týden"*
  (EN gloss: "{matched} of {total} ingredients on sale this week").
- Expandable list: each deal shows the shop, the leaflet product name, and a
  link to `source_url`. No price, no % — informational.
- When `matched === 0`: render nothing (no empty/zero headline).
- CZ strings authored by Claude with EN gloss for review (per house rule).

### Phase 2 (later, separate spec)

CZK "deals worth up to ~X" — only where an active `LEAFLET_DISCOUNT` and a
`STORE_REGULAR` baseline exist for the same canonical with comparable units.
Requires verifying unit comparability across the two PriceRecord sources.

## Testing (TDD)

- `recipe_deals`: active deal matched; **future-dated deal excluded**; expired
  excluded; null-end excluded; non-`LEAFLET_DISCOUNT` excluded; ingredient with
  no canonical link ignored; dedupe to one deal per ingredient; `matched=0` path.
- Serializer: `deals` payload shape; `matched=0` → empty deals.
- Frontend: headline renders with count; hidden when `matched=0`; deal list +
  links.

## Risks / notes

- **Only 18 recipes are `is_public=True`** (vs 372 curated `CuratedRecipe`). A
  separate publishing-pipeline gap; out of scope here but worth raising.
- Matching depends on the discount having a `store_product.canonical_ingredient`
  link; discounts without it are silently skipped (acceptable — integrity first).
- No discount_percentage means the headline is count-only by design this phase.
