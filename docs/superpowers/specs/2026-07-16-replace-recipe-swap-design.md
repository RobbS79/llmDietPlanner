# Replace-recipe ("Vyměnit recept") — Design

**Date:** 2026-07-16
**Backlog:** Phase I (Pilot) — "Replace-recipe from recipe view"
**Status:** Approved, ready for implementation plan.

## Goal

From the recipe view, a signed-in user swaps the current meal for a **different curated
recipe** for that same slot, optionally steering the choice with a free-text hint
("něco s kuřecím", "něco lehčího"). Curated-corpus only — the 100% catalog-mapping /
deals integrity bar is preserved. No LLM-generated fallback meals.

## Decisions (locked)

- **Source:** curated corpus only (`CuratedRecipe`), via `eligible_recipes_for_slot(...,
  exclude_ids={current})`. If no other eligible recipe exists for the slot, the swap
  reports "no alternatives" rather than fabricating one.
- **UX:** one free-text box ("Na co máte chuť? (nepovinné)"). Blank = plain next-best.
- **Cost:** retrieval is $0 (DB query + scoring over the published corpus). The only paid
  step is parsing a non-blank hint into facets — a single Gemini-flash call
  (`extract_prompt_facets`), ≈ $0.0002–0.0005. Skipped entirely when the box is blank.
  No swap limit (retries are cheap; no per-turn spiral).
- **Placement:** recipe view only (`RecipePage.tsx`). PlanView meal-card button deferred.

## Background: how a meal is stored (why this is the shape it is)

Meal content is **not** a per-row model. It lives as JSON at
`DietaryPlan.days[day_index][slot]` (slot ∈ breakfast/lunch/dinner/small_meals/snacks),
addressed by `meal_identifier` = `"{goal_id}:{day_number}:{meal_type}:{index}"`. A curated
meal dict carries `source='curated'`, `curated_recipe_id`, `curated_recipe_slug`, and
`source_*` provenance (set by `scale_recipe_to_meal`, `recipe_retrieval.py:287-338`).

Two side tables key off the **same reused** `meal_identifier` and are cache traps for a swap:
- `Recipe` (`core.py:701`) — a lazily-created cache row, unique on `meal_identifier`.
  `RecipeDetailView.get` returns it early if present, ignoring `plan.days`. A swap MUST
  delete it or the pre-swap recipe is served forever.
- `MealInstance` (`core.py:779`) — cooking log (`is_cooked`, `meal_name`), keyed by the
  same identifier. A swap MUST clear its cooked state, or the new recipe shows "Uvařeno".

Pricing/deals need **no** recompute: `price_range`/`shopping_list`/`deals` are read-time
`SerializerMethodField`s off `obj.ingredients` — correct automatically once the new
ingredients land in the JSON.

## Endpoint

`POST /api/recipes/<meal_identifier>/replace/` — new view alongside `RecipeDetailView`
(`urls.py:24`). Request body: `{ "hint": "" }` (optional string).

**Flow:**
1. Parse `meal_identifier` → `goal_id:day_number:meal_type:index`. Load `DietaryGoal`
   **scoped to `request.user`** (404 if not owner / not found), its `DietaryPlan`, and the
   target slot in `days`. 404 if the slot is missing.
2. Derive slot constraints:
   - `meal_type` from the identifier,
   - `required_tags = parse_dietary_tags(goal.dietary_restrictions)`
     (`recipe_retrieval.py:66`),
   - `exclude_ids = {current meal dict's curated_recipe_id}` (empty set if the current
     meal was LLM-generated / has no id).
3. If `hint` is non-blank:
   `vocab = published_cuisine_vocab()` (`recipe_retrieval.py:82`);
   `facets = extract_prompt_facets(hint, language=goal.language_code, cuisine_vocab=vocab)`
   (`prompt_facets.py:101` — the single flash call). Blank hint → `facets = None`, no LLM.
4. `candidates = eligible_recipes_for_slot(meal_type, required_tags, exclude_ids=…,
   facets=facets)` (`recipe_retrieval.py:138`). Pick
   `max(candidates, key=lambda r: score_recipe(r, used_recipe_ids=<other curated ids in
   this plan>, ...))` so a swap does not duplicate a recipe already elsewhere in the plan.
5. **Hint fallback:** if `hint` was non-blank and step 4 yielded zero candidates, retry
   once with `facets=None` (plain next-best) and set `hint_matched=false`. Otherwise
   `hint_matched=true` (or `null` when no hint was given).
6. **No alternatives:** if candidates are still empty, return
   `200 {"replaced": false, "reason": "no_alternatives"}`. No DB writes.
7. **Apply (one `transaction.atomic()`):**
   - `new_meal = scale_recipe_to_meal(chosen)`; set
     `new_meal['meal_identifier'] = <existing identifier>`.
   - Write `plan.days[day_index][slot] = new_meal`; `plan.save()`.
   - `CuratedRecipe.objects.filter(pk=chosen.id).update(usage_count=F('usage_count')+1)`.
   - Delete the cached `Recipe` row for this `meal_identifier` (scoped to the user's goal),
     if any.
   - Clear the `MealInstance` cooked state for this `meal_identifier` (reset
     `is_cooked=False`, refresh `meal_name`), if a row exists.
8. Return `200 {"replaced": true, "hint_matched": <bool|null>, "recipe": <serialized>}`
   where `recipe` is the same shape `RecipeDetailView` returns, built from `new_meal`
   (curated meals already carry instructions, so no LLM call to synthesize them). The
   frontend re-renders from this payload without a second round-trip.

**Note on rebuilding the `Recipe` cache:** the endpoint deletes the stale row. It MAY also
create the fresh cache row from `new_meal` in the same transaction (curated → has
instructions, $0). Whether to pre-create vs. lazy-regenerate on next `GET` is an
implementation detail, provided the next `GET /recipes/<id>/` cannot trigger an LLM
instruction-synthesis call for a curated meal.

## Frontend (`frontend/src/pages/RecipePage.tsx`)

- Add a **"Vyměnit recept"** button near the attribution / "Zpět na plán" link.
- Clicking opens a small inline panel (not a full modal):
  - Label **"Na co máte chuť? (nepovinné)"**, placeholder
    *"např. něco s kuřecím, něco lehčího"*.
  - Submit button **"Vyměnit"**; Cancel closes the panel. Submit is allowed with an empty
    box (= plain next-best).
- On submit: `POST /recipes/${mealId}/replace/` with `{ hint }`. Disable submit while
  pending.
- Responses:
  - `replaced:true` → replace local recipe with returned `recipe`; invalidate
    `['recipe', mealId]` and `['plan', goalId]`; close panel;
    toast **"Recept byl vyměněn."** If `hint_matched === false`:
    toast **"Nenašli jsme recept přesně podle přání, vybrali jsme jinou variantu."**
  - `replaced:false` → keep panel open; message
    **"Pro tento typ jídla teď nemáme jinou alternativu."**
  - Network / 4xx-5xx error → **"Výměna se nezdařila, zkuste to prosím znovu."**

The API call lives in a small frontend lib module (mirroring `lib/settings.ts`) so it is
unit-testable without the component.

## Czech copy (final)

| Key | String |
|---|---|
| Button | Vyměnit recept |
| Panel label | Na co máte chuť? (nepovinné) |
| Placeholder | např. něco s kuřecím, něco lehčího |
| Submit | Vyměnit |
| Cancel | Zrušit |
| Success | Recept byl vyměněn. |
| Hint no-match (still swapped) | Nenašli jsme recept přesně podle přání, vybrali jsme jinou variantu. |
| No alternatives | Pro tento typ jídla teď nemáme jinou alternativu. |
| Error | Výměna se nezdařila, zkuste to prosím znovu. |

## Out of scope (YAGNI)

- Swap limits / quotas (retrieval is $0).
- "Vyměnit" on the PlanView meal card (trivial later follow-up).
- Multi-turn chat.
- LLM-generated fallback recipes (would break the catalog-mapping / deals bar).

## Testing

**Backend (`python3 manage.py test`, sqlite):**
- Excludes the current recipe (never returns the same `curated_recipe_id`).
- Hint filters candidates (facets respected via `recipe_matches_facets`).
- Hint-no-match: non-blank hint with zero facet matches falls back to next-best and
  returns `hint_matched=false`.
- No-alternatives: slot with no other eligible recipe → `{replaced:false}`, no DB writes.
- Ownership: another user's `meal_identifier` → 404, no writes.
- Side effects: stale `Recipe` row deleted; `MealInstance.is_cooked` reset;
  `plan.days[day][slot]` rewritten with the new curated meal + preserved `meal_identifier`;
  `usage_count` bumped.

**Frontend (`npx vitest run`, `npx tsc --noEmit`, lint):**
- Lib module: posts `{hint}` to the right URL; surfaces `replaced`/`hint_matched`.
- Component: panel open → submit (blank + with hint) → each toast/message branch;
  submit disabled while pending. Lint stays at the current baseline (52/1).

## Key code anchors

- `diet_planner/services/recipe_retrieval.py`: `parse_dietary_tags:66`,
  `published_cuisine_vocab:82`, `recipe_matches_facets:121`,
  `eligible_recipes_for_slot:138`, `score_recipe:174`, `scale_recipe_to_meal:287`,
  `overlay_curated_recipes:341` (materialization + usage_count pattern).
- `diet_planner/services/prompt_facets.py`: `extract_prompt_facets:101`.
- `diet_planner/urls.py:24` (`recipes/<str:meal_identifier>/`), `:26` (meals).
- `diet_planner/views.py`: `RecipeDetailView` (serialization shape to mirror),
  `MealInstanceView` (cooked-state model), price/deals builders.
- `diet_planner/models/core.py`: `DietaryPlan:477`, `Recipe:701`, `MealInstance:779`,
  `DietaryGoal:190`.
- `frontend/src/pages/RecipePage.tsx` (button + panel), `frontend/src/pages/PlanView.tsx`
  (query keys `['plan', id]`, `['recipe', mealId]` to invalidate).
