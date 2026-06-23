# Per-Recipe Portion Scaling — Design

**Date:** 2026-06-23
**Status:** Approved (approach), pending spec review
**Author:** Robert Soroka (with Claude)

## Summary

Add an interactive portion stepper to the per-recipe view (like
toprecepty.cz's `+`/`−` control). Changing the portion count rescales the
displayed ingredient amounts live. The deals headline is unchanged because it
is portion-invariant. Scaling is **client-side** (Approach A); the backend's
only job is to make the serving denominator truthful and keep ingredient
quantities at full stored precision.

Inspiration: toprecepty.cz stores an **exact base value per ingredient** for a
known base portion count (`data-value="0.300…"`), renders a *rounded view*
(`0,4 kg`), leaves "to taste" items (salt, bacon) quantity-less, and multiplies
live in the browser against a portion stepper. We adopt the same model.

## Problem / Motivation

Scaling is currently broken at the root:

- `scale_recipe_to_meal` (`diet_planner/services/recipe_retrieval.py:287`) emits
  a meal dict with **no `servings` key** and ingredient quantities at base
  (`factor=1.0`).
- `Recipe.objects.create(...)` (`diet_planner/views.py:467`) never passes
  `servings`, so every grounded recipe gets the model default `servings = 1`
  (`diet_planner/models/core.py:726`) — even though its quantities describe
  `base_servings` portions (e.g. a recipe written for 4).

Consequences:

1. The servings badge (`RecipePage.tsx:142`) reads "1 porce" when the food is
   really for 4.
2. `price_recipe(ingredients, servings=1)` (`serializers.py:261`) computes a
   wrong per-portion cost (divides by 1 instead of the true base). This is
   dormant today (absolute price display is disabled) but latent-wrong.
3. There is no way for a user to say "I want this for N people" and have the
   amounts follow.

## Goal

A user viewing a recipe can change the portion count with a `−`/`+` stepper;
the ingredient amounts rescale instantly and correctly. The serving count the
amounts are based on is truthful end to end.

**Non-goals (explicitly out of scope):**

- Adding a toprecepty.cz HTML parser or any new recipe source. The chosen focus
  is *scaling fidelity*, not *extraction*. Scaling fidelity is bounded by the
  precision of the base quantities already stored; improving extraction is a
  separate effort.
- Re-enabling absolute price display. The price engine stays dormant. When it
  returns, scaling is linear and can mirror the same factor.
- Persisting the chosen portion count. Selection is ephemeral and resets to the
  recipe's base on reload.

## Approach

**Approach A — client-side scaling (chosen).** The server guarantees `servings`
is the true base denominator and that ingredient `quantity` is the exact stored
float. The React stepper holds the chosen portion count and computes
`scaled = qty × (chosen / servings)` per ingredient, formatting for display.
Deals headline untouched (portion-invariant); price display stays dormant.

Rejected — **Approach B (server round-trip)**: sends `?servings=N`, returns
rescaled ingredients. Single source of truth and "free" future price scaling,
but adds network latency on every tap and a new endpoint/param for zero
server-side values that currently depend on portions. The foundation work below
future-proofs B if we ever want it.

## Design

### Backend — make the denominator truthful (foundation)

1. **`scale_recipe_to_meal`** (`recipe_retrieval.py:287`): add
   `'servings': recipe.base_servings` to the returned meal dict. Ingredient
   quantities stay at base (`factor=1.0`) — they describe `base_servings`
   portions, which is exactly what `servings` now records. This value flows into
   the plan's `days` JSON via `overlay_curated_recipes`.

2. **`Recipe.objects.create`** (`views.py:467`): pass
   `servings=meal.get('servings') or 1`. Grounded meals carry the real base;
   non-grounded (LLM-generated) meals have no reliable base and default to `1`
   (acceptable — generated meals are effectively single-serving and were already
   treated as `servings=1`).

3. **Ingredient `quantity` precision**: keep the exact stored float. No rounding
   at curation (already true — `recipe_curation.py:170` stores as-is). Display
   rounding is the client's job, mirroring toprecepty's `data-value` vs.
   rendered text.

4. **Quantity-less ingredients** (`null` / "to taste"): pass through unchanged
   and are never scaled (already the case in `scale_recipe_to_meal`).

5. **No new endpoint.** `RecipeSerializer` already serializes `servings` and
   `ingredients` (`serializers.py:218-241`). Deals are unchanged and remain
   portion-invariant.

### Frontend — the stepper

Shared helpers in a new `frontend/src/lib/portions.ts`, consumed by both
`RecipePage.tsx` and `PublicRecipePage.tsx` (identical ingredient/deals blocks).

1. **`PortionStepper`** component: `−` / `[n]` / `+` control, initialized to
   `recipe.servings`, clamped to `[1, 20]`. Aria-labels in Czech.

2. **`scaleAmount(qty, baseServings, chosen)`**: returns
   `qty * (chosen / baseServings)`; guards `baseServings <= 0` → treat as 1.

3. **`formatAmount(value, unit)`**: unit-aware rounding with Czech decimal comma:
   - `g`, `ml` → whole numbers
   - `kg`, `l` → 1 decimal
   - `ks` / count → whole (or `.5` allowed)
   - unknown/other → up to 2 significant decimals, trailing zeros trimmed

4. **`czechPlural(n, [one, few, many])`**: 1 → `one`, 2–4 → `few`, 0 or 5+ →
   `many`. Portion word forms: `["porce", "porce", "porcí"]`. A small map covers
   counted ingredient units that inflect (e.g. `lžíce` →
   `["lžíce","lžíce","lžic"]`, `vejce` → `["vejce","vejce","vajec"]`,
   `stroužek` → `["stroužek","stroužky","stroužků"]`). Metric units
   (`g`/`kg`/`ml`/`l`/`ks`) are invariant and pass through unchanged.

5. **Quantity-less ingredients**: render name only (no amount), unaffected by
   the stepper — keep the existing `ing.quantity &&` guard.

6. **State**: `portions` held in component state, ephemeral. The deals block is
   rendered exactly as today (no portion input).

### Czech strings (authored here; EN gloss for review)

| String | Czech | EN gloss |
|---|---|---|
| Stepper decrement aria-label | `Méně porcí` | "Fewer portions" |
| Stepper increment aria-label | `Více porcí` | "More portions" |
| Portion plural | `porce / porce / porcí` | "portion / portions / portions" |

## Data Flow

```
CuratedRecipe.base_servings ──► scale_recipe_to_meal() meal['servings']
   meal stored in DietaryPlan.days JSON (overlay_curated_recipes)
      ──► Recipe.objects.create(servings=meal['servings'])   [views.py:467]
         ──► RecipeSerializer → API: {servings, ingredients:[{name,quantity,unit,optional}]}
            ──► RecipePage: portions state (default = servings)
               ──► per ingredient: formatAmount(scaleAmount(qty, servings, portions), unit)
```

Deals: `RecipeSerializer.deals` → `getRecipeDeals` → headline, **unchanged**.

## Error Handling / Edge Cases

- `baseServings` missing or `<= 0` → treat as `1` (no divide-by-zero).
- `quantity` null / non-numeric → name-only render, never scaled.
- Stepper clamped to `[1, 20]`; `+`/`−` disabled at bounds.
- Unknown unit → `formatAmount` falls back to trimmed 2-decimal display; unit
  string passed through verbatim (no pluralization).
- Non-grounded recipes (`servings = 1`): stepper still works; "per 1 porce"
  baseline. No regression.

## Testing

**Backend (pytest):**
- `scale_recipe_to_meal` emits `servings == recipe.base_servings`.
- Recipe creation from a grounded meal dict sets `Recipe.servings` to the base;
  from a generated meal (no `servings`) defaults to `1`.
- `price_recipe` per-portion now divides by the true base (regression guard for
  the dormant price path).

**Frontend (vitest):**
- `scaleAmount`: linear scaling; `baseServings=0` guard.
- `formatAmount`: rounding per unit; Czech comma; trailing-zero trim.
- `czechPlural`: 1 / 2–4 / 5+ boundaries for `porce` and counted units.
- Quantity-less ingredient renders name-only and is unaffected by stepper.
- `PortionStepper`: clamp at bounds; default = `servings`.

## Rollout

Pure additive UI + a backend correctness fix. No migration. Ships on `develop`;
prod deploys from `prod` branch per existing process.
