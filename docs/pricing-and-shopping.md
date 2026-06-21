# Pricing, Shopping List & Ingredient Diversity

How a plan's grocery cost is estimated and how the shopping list is kept short.
This replaces the old per-shop price resolution (unreliable) with a maintainable
static estimate, and steers generation toward fewer distinct ingredients.

Last reworked: 2026-06-21.

---

## 1. Pricing model (what the user sees)

The headline is an **estimate**, never an exact price, and is framed as a small,
relatable **per-day, per-person** number — the plan total is secondary. Prices
are pro-rated (cost of the food actually consumed), not whole-pack.

### Where the numbers come from

| Concern | Answer |
| --- | --- |
| Source of prices | A **static price book**, `diet_planner/data/canonical_prices.yaml`. No live per-shop calls. |
| Unit of price | CZK per **base unit** (g / ml / ks) + a typical pack size, keyed by **canonical ingredient** slug. |
| Cost basis | **Pro-rated / consumed**: `cost = quantity_consumed × price_per_unit`. Not whole packages. |
| Shop names | **Never shown** in the shopping list or estimate. Stores appear **only** in the leaflet *deals* section. |
| Pantry staples | Excluded from the headline by default (the "Mám doma základy" / fridge toggles). |
| Currency | Book is CZK; non-CZK plans converted with a rough constant (estimates only). |

### Key code

- `diet_planner/services/estimate_pricer.py` — `EstimatePricer.price(items, basics_on, fridge_on)`
  returns `(resolved_items, estimate)`. `_consumed_cost` does the pro-rated math
  via the shared converter; falls back to one pack only when units can't be
  converted; caps absurd quantities.
- `diet_planner/services/units.py` — the single unit converter (mass/volume/count).
  Mixing g with kg without converting is what once produced a 238 000 Kč chicken
  line; keep all pricing math on this module.
- `diet_planner/services/shopping_list_pricing.py` — `compute_pricing()` returns
  `{estimate, deals, pantry_toggles, pantry_present}`. The old cross-store
  `price_range` (which leaked shop names) is gone. `deals` are factual leaflet
  discounts and the only place store names appear.
- `diet_planner/serializers.py` — `DietaryPlanSerializer.get_pricing` recomputes
  the estimate live per the plan's actual pantry toggles.

### API contract (`plan.pricing`)

```jsonc
{
  "estimate": { "total", "per_day", "per_portion"|null, "currency",
                "is_estimate": true, "priced_items", "total_items" },
  "deals": [ { "store", "store_name", "status", "valid_from", "valid_until",
               "currency", "items": [ { "ingredient", "matched_product_name",
                                        "sale", "original"|null, "savings"|null } ] } ],
  "pantry_toggles": { "basics_on", "fridge_on" },
  "pantry_present":  { "basics", "fridge" }
}
```

Shopping-list items carry `price_total`, `price_source`
(`estimate` | `pantry_estimate` | `not_available`), `estimated`, and pantry
metadata — and **no** shop/brand fields.

### Frontend

`frontend/src/lib/pricing.ts` holds the contract types + helpers. The estimate
renders per-day-per-person as the hero ("Odhad ceny jídla · na den", "/ den ·
na osobu") with the plan total secondary, on `ShoppingListPage`, `PlanView`, and
`Dashboard`. No fabricated "savings vs average" widgets.

---

## 2. Maintaining the price book

`canonical_prices.yaml` is **maintained by hand** (inflation, corrections). It
was seeded from catalog **medians** (which ignore premium SKUs that inflate
totals).

```bash
# Re-seed the whole book from current catalog medians (overwrites the file):
python manage.py build_price_book
python manage.py build_price_book --stdout        # preview without writing
```

Entry shape:

```yaml
prices:
  chicken-breast:
    name_cs: kuřecí prsa
    unit: g                 # base unit
    price_per_unit: 0.3499  # CZK per g
    pack: 650.0             # typical pack size in base unit
    samples: 4
```

Known seed caveat: a few pantry staples are over-priced from gourmet-only SKUs
(e.g. `salt` ≈ 740 Kč/kg). They don't reach the headline (pantry is excluded by
default) but are worth correcting on a manual pass.

### Re-pricing existing plans (no regeneration)

Per-item prices are frozen into the plan at creation. After a pricing change,
heal existing plans in place — no LLM, same meals:

```bash
python manage.py recompute_plan_prices --dry-run   # preview old -> new
python manage.py recompute_plan_prices             # apply
```

> Re-pricing uses the current book, so re-running can shift a plan's total as
> the book changes. It re-prices the existing shopping list; it does not
> regenerate meals.

---

## 3. Ingredient diversity (keeping the shopping list short)

A plan built from many one-off ingredients yields a long, expensive,
hard-to-shop list (some plans hit ~99 distinct ingredients for 3 days). Two
nudges steer generation toward a shared core set, without gutting variety:

1. **Prompt budget** — `LLMService._build_meal_system_prompt` adds an
   "INGREDIENT EFFICIENCY" block (full plans only): reuse proteins/veg/grains
   across meals, target ≈ `max(15, num_days × 6)` distinct main ingredients,
   prefer meals that reuse what's already in the plan.

2. **Ingredient-overlap-aware curated selection** —
   `diet_planner/services/recipe_retrieval.py`. `score_recipe` takes
   `used_canonicals` and rewards candidates sharing canonical ingredients with
   already-chosen recipes (`+0.6` each, capped `+6.0`); `select_recipes_for_plan`
   accumulates `used_canonicals` across the plan. This is a **nudge / tie-breaker**
   — deliberately weaker than the cuisine-variety penalty so a week doesn't
   collapse into one ingredient.

The shopping list itself is aggregated from meal ingredients by normalized name
in `tasks.py:aggregate_ingredients_from_meals` (quantities summed across meals).

### Tuning knobs

| Want | Change |
| --- | --- |
| Shorter lists (less variety) | Raise the overlap weight / cap in `score_recipe`; lower the prompt budget multiplier. |
| More variety (longer lists) | Lower the overlap weight; raise the budget multiplier. |
| Stronger reuse vs. cuisine variety | Increase overlap weight relative to the `-5` cuisine penalty in `score_recipe`. |

---

## 4. History / rationale

- Whole-pack pricing was tried first, then reversed: plans are priced per person
  (`servings` defaults to 1; household size isn't captured), so whole-pack badly
  overstated short plans (~730 Kč/day). Pro-rated is lower and more honest.
- Showing prices at all was questioned (fear of deterring customers); kept,
  because real grocery cost is the product's differentiator — but reframed to a
  believable per-day number.
- The unit-conversion bug that produced a 238 129 Kč chicken line is fixed in
  `units.py` + `price_resolver.py` (`_calc_packages_needed`).
