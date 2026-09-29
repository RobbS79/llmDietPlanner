# Meal pool: replace the day grid with "how many of each meal"

**Date:** 2026-09-29
**Status:** approved design, awaiting implementation plan
**Owner decision:** replace the day-based plan entirely (no second mode).

## 1. Problem

A plan today is a fixed grid: day 1 … day N, each with breakfast / lunch /
dinner plus per-day small meals and snacks. The user must accept both the
schedule and the shape. Real demand (see `docs/customer-journey-prompting.md`,
prompt mining 2026-09-16) is "co uvařit z kuřecích prsou", "rychlá večeře",
"krabičky na týden" — people want a set of dishes, not a timetable.

The grid is also where most generation incidents came from: Gemini composing
whole days (hollow days, goal 133), the overlay refusing to attach, the form
overriding the prompt's "3 dny, oběd a večeře" (plan 150), snacks generated
when `snacks_per_day` was 0. Gemini is never even told the meal booleans or
the snack counts; only the overlay honours them.

## 2. Goal

The user says how many breakfasts, lunches, dinners, small meals and snacks
they want. They receive exactly that many recipes, grouped by meal type, each
with its own shopping list, and cook them in whatever order they like.

Everything below the meal identifier — the `Recipe` row, per-recipe shopping
list, deals, pricing, nutrition card, refine chat, cooked tracking — is
already per-recipe and is kept.

## 3. Non-goals

- Macros / calorie targets from public nutrition data (USDA, Frida). Later.
- The prompt overriding the counts ("tři večeře na víkend" sets dinners=3).
  The prompt shapes *which* recipes are picked; the counts set the size.
- Drag ordering, "cook tonight" scheduling, calendar assignment.
- Ads, billing, corpus curation.

## 4. Input

### 4.1 `DietaryGoal`

New integer fields, each `0..14`, validators enforce at least one non-zero:

| field         | Czech label     |
|---------------|-----------------|
| `breakfasts`  | Snídaně         |
| `lunches`     | Obědy           |
| `dinners`     | Večeře          |
| `small_meals` | Svačiny         |
| `snacks`      | Drobné snacky   |

Legacy columns `num_days`, `breakfast`, `lunch`, `dinner`,
`small_meals_per_day`, `snacks_per_day` become nullable and are no longer
written. They stay so old goals load, render and export.

`DietaryGoal.is_pool` (property): true when at least one of the five count
fields is non-null. `DietaryPlan.is_pool`: `meals is not None`. These are the
switches serializers and UI read.

### 4.2 API

`DietaryGoalCreateRequest` (Pydantic) and the DRF goal serializers accept the
five counts and reject the legacy fields (400 with a clear message). The
detail serializer returns both sets so old goals still describe themselves.

Quota is unchanged: one final POST = one generation, regardless of counts.

### 4.3 Frontend `CreatePlan`

Step 2 "Nastavení jídel" becomes five steppers (0–14) plus two presets:

- **Pracovní týden**: 5 / 5 / 5 / 5 / 0
- **Víkend**: 2 / 2 / 2 / 0 / 2

`prefillFrom` copies the counts from the user's most recent goal (already the
mechanism for the old fields). The goal picker shows the total meal count
instead of `{n}d`. Validation: at least one count > 0.

`components/settings/PreferencesSection` drops "Počet dní jídelníčku"
(`num_days` in `dietary_preferences`); nothing read it.

## 5. Generation: corpus first, Gemini for gaps

Replaces both `process_dietary_goal_task` and
`process_dietary_goal_catalog_task` with one task `generate_meal_pool_task`.

1. **Facets.** `extract_prompt_facets(goal.prompt, …)` — the only Gemini call
   on the happy path. `store_derived_dietary_tags` as today.
2. **Select.** `select_recipes_for_pool(goal, facets, recently_served_ids)`
   in `services/recipe_retrieval.py` replaces `select_recipes_for_plan`.
   For each slot type in `(breakfast, lunch, dinner, small_meal, snack)` with
   `count > 0`, pick `count` recipes in one pass:
   - candidates via `eligible_recipes_for_slot` (unchanged gates: meal_type,
     dish_role, dietary tags, facets, catalog mapping);
   - fallbacks in the same order as today: family-relaxed → role-relaxed →
     `no_eligible_recipes` gap;
   - score with `score_recipe` (variety, demand ranking, recent-serve
     penalty, ingredient reuse); `target_calories` comes from
     `_SLOT_DEFAULT_KCAL[slot]` since there is no Gemini meal to read it from;
   - sampling window + seeded RNG keyed `f'{goal_seed}:{slot}:{i}'` (stable
     re-runs, rotation across goals);
   - `wanted_fit_below_threshold` gap for main slots when the best candidate
     matches none of the wanted ingredients;
   - dedupe: no recipe twice; no dish family twice **anywhere in the pool**
     (was: per day). Family relaxation only when the slot would otherwise
     starve, recorded as a gap.
   Returns `{'meals': [(slot, index, CuratedRecipe)], 'coverage', 'gaps'}`
   where gaps carry `slot` and `index` instead of `day_number`.
3. **Render.** Each chosen recipe → `render_curated_meal` / `scale_recipe_to_meal`
   with `target_kcal = _SLOT_DEFAULT_KCAL[slot]` and příloha attached as
   today. `source: "curated"`.
4. **Fill gaps.** For each gap, one `GeminiService.regenerate_meal`-style
   call for that slot type with the user prompt and resolved restrictions
   (`RestrictionResolver`), then the existing per-meal violation check +
   repair loop. `source: "generated"`. If the LLM fails for a gap, that
   position is dropped and counted in `shortfall[slot]`.
   *Suspect facets* (`facets.suspect`): the extraction failed on a concrete
   prompt, so corpus selection can't be trusted to honour it. All **main**
   slots go through the gap path with the raw prompt; small meals/snacks
   still come from the corpus.
5. **Guard.** `_assert_plan_has_content` becomes "at least one meal".
6. **Store.** `DietaryPlan.objects.create(meals=…, grounding_debug={facets,
   coverage, gaps, shortfall}, llm_* accounting)`.

Deleted: the whole-plan Gemini prompt paths (`generate_meal_plan_only`,
`generate_catalog_constrained_plan`, the `days` schema in
`_build_meal_system_prompt`, `_enforce_restrictions` day walk),
`transform_days_to_new_format`, `overlay_curated_recipes` and rescue-only mode,
`_calorie_targets_from_days`, `build_llm_prompt_json` + `DietaryGoalPromptDebugView`,
`services/meal_plan.py`, `services/shopping_list.py`, the day checks in
`services/validation.py`, the catalog-prompt build in the catalog task
(`CatalogService.build_compact_prompt_text` stays only if something else
uses it; otherwise delete).

`social/facts.py` and `shopifyin/webhooks.py` call the new task.

## 6. Storage and identifiers

### 6.1 `DietaryPlan.meals`

New JSON field, list of meal dicts. Each entry is today's meal dict (name,
description, servings, preparation_time, ingredients with
`canonical`/`catalog_id`, instructions, nutritional_info, source,
curated_recipe_id/slug, attribution, side) plus:

```json
{"slot": "dinner", "index": 3, "meal_identifier": "151:dinner:3", ...}
```

Order in the list = slot order (breakfast, lunch, dinner, small_meal, snack),
then index. `days` stays for legacy plans and is `[]` (the field default) for
pool plans; `meals` is `null` on legacy plans.

### 6.2 Identifier

New: `<goal_id>:<slot>:<index>` (3 parts). Legacy: `<goal_id>:<day>:<type>:<index>`
(4 parts, and 3-part `goal:day:type` for old dict slots).

`diet_planner/services/meal_locator.py`:

- `parse_meal_identifier(s) -> MealRef(goal_id, slot, index, day_number|None, is_legacy)`.
  Disambiguation: part 2 numeric → legacy day; part 2 in the slot vocabulary
  → pool. `ValueError` otherwise.
- `locate_meal(plan, ref) -> (container, key)` such that `container[key]` is
  the meal dict, for both shapes.
- `set_meal(plan, ref, meal)`.

This module replaces `views._parse_meal_identifier`, `_LIST_SLOT_KEYS`,
`_get_slot_meal`, `_set_slot_meal`, `_locate_plan_slot`'s day lookup, the
lookup in `RecipeDetailView`, `refresh_stale_recipe_cache._write_plan_slot`,
`recipe_research`'s `parts[2]` slot parse and `MealInstanceView.patch`'s
split. `Recipe.meal_identifier` help text and `lib/planMeals.ts` contract
comment are updated.

`MealInstance.day_number` becomes nullable; `meal_type` = slot.

## 7. Output

### 7.1 API

`DietaryPlanSerializer` returns `meals` (pool) or `days` (legacy), plus
`shortfall` and `counts` (`{slot: requested}`) from the goal.

### 7.2 Frontend

- `lib/planMeals.ts`: add `PlanMeal.slot/index`, `groupPoolMeals(meals)` →
  ordered sections `{slot, label, meals}`; `poolTotals` (cooked n/total,
  average kcal per main). `MEAL_SLOT_LABELS`, `parseNutrition` reused. Legacy
  `dayMealEntries`/`dayTotals` stay.
- `components/plan/MealRow.tsx`: `renderMain` / `renderSmall` lifted out of
  `DayCard` (one row: image, name, kcal, time, cooked toggle, "Nesedí?"
  link). `DayCard` imports it; behaviour for legacy plans unchanged.
- `components/plan/SlotSection.tsx`: heading (e.g. "Večeře · 5", or
  "Večeře · 4 z 5" when short), list of `MealRow`.
- `components/plan/SlotStrip.tsx`: sticky pills, one per non-empty slot,
  anchor `#slot-dinner`. Replaces `WeekStrip` for pool plans; `WeekStrip`
  stays for legacy.
- `pages/PlanView.tsx`: branch on `plan.meals`. Pool header: counts summary
  ("5 večeří · 3 snídaně"), "Uvařeno 3 z 13", "Prům. kcal na hlavní jídlo".
  Shortfall notice when any slot is short: "Našli jsme 4 z 5 večeří — zkuste
  jiné zadání nebo si nechte doplnit v chatu." Text export prints sections.
- `pages/Dashboard.tsx`: badge "13 jídel" for pool goals, "7 dní" for legacy.
  Delete the dead per-day price code (`pricing.estimate` is no longer
  served).

`RecipePage`, refine chat, research parking, cooked toggle: no change (they
treat `mealId` as opaque).

## 8. Refine, replace, cooked

- `_plan_swap_state(plan, current_id)`: `used_recipe_ids` over all meals in
  `plan.meals` (or `days` for legacy); `used_families` = families of every
  *other* curated meal in the pool (was: same day). The swap candidate must
  not repeat a family already in the pool; relax only if that empties the
  candidate list.
- `_commit_slot_swap` writes via `set_meal`; portions to the old meal's kcal
  as today; `Recipe` row updated in place; `MealInstance` reset.
- `run_refine_turn` and research jobs receive `slot` from `MealRef`.
- `plan_time_budget` unchanged (reads `grounding_debug.facets`).

## 9. Copy

"Jídelníček" stays as the product word. Everything that says "N dní",
"týden jídla", "na den" changes to the pool framing: *vyberte si, kolik
snídaní, obědů a večeří chcete, a dostanete hotové recepty s nákupním
seznamem*. Files:

- `pages/Landing.tsx`: hero line, `SAMPLE_PLAN` becomes a small pool (2
  dinners, 1 lunch, 1 breakfast), CTA.
- `pages/HowToPrompt.tsx` (`/jak-to-funguje`) + `docs/customer-journey-prompting.md`:
  step 2 describes counts; example prompts lose "na 3 dny / na týden".
- `pages/Pricing.tsx`, `lib/billing.ts`: keep "7 / 30 jídelníčků"; drop
  "celý týden jídelníčku na míru".
- `frontend/index.html`, `frontend/prerender.mjs` meta descriptions.
- `pages/PublicRecipePage.tsx` + SSR `llm_diet_planner_project/views.py`
  CTA "Chcete celý týden takových jídel?" → "Chcete víc takových receptů
  s nákupním seznamem?".
- `CreatePlan.tsx`, `PlanView`, `Dashboard`: labels above.
- Social: `social/facts.py` showcase builds a pool goal (1 breakfast,
  2 dinners) and reads `plan.meals`; `social/cards.py` drops "Celkem X kcal
  za den"; `social/captions.py` brief says "jaká jídla mu Vařto vybralo".
- `components/ui/Receipt.tsx` comment.

Czech strings are drafted by Claude with an English gloss for the owner to
review before merge (owner cannot author Czech).

## 10. Legacy and rollout

- No data migration. Old goals keep `days` and 4-part identifiers; old
  plans render through `DayCard`/`WeekStrip`; old `Recipe`, `MealInstance`,
  `RecipeResearchJob` rows keep resolving through `meal_locator`.
- New schema migration: add five count fields + `DietaryPlan.meals`; make
  the six legacy goal fields and `MealInstance.day_number` nullable.
- One PR to `develop`, then `prod`. No feature flag: the old generation path
  is deleted, not dormant. `RECIPE_GROUNDING_ENABLED` becomes meaningless
  and is removed from settings and DO env.
- After deploy: `/qa-prod` on (a) a fresh pool plan from a real-demand
  prompt ("mám kuřecí prsa a cukety", 5 dinners) and (b) one pre-existing
  day plan (plan 150) to confirm legacy rendering, recipe page, refine and
  cooked toggle still work.

## 11. Testing

TDD per unit; the full `diet_planner` suite must stay green.

- `test_recipe_pool_selection.py`: counts honoured exactly; zero-count slots
  produce nothing; family dedupe across slots; relaxation recorded as gap;
  seed stability; recently-served penalty; `wanted_fit` gap on mains;
  suspect facets route mains to the gap path.
- `test_meal_locator.py`: parse both identifier shapes, reject malformed;
  locate/set on pool and legacy plans.
- `test_generate_meal_pool_task.py`: fake Gemini; gap fill; shortfall
  recorded on LLM failure; restriction repair on generated meals; quota and
  status transitions; `RepairBudgetExhausted` handling.
- `test_recipe_replace.py` / `test_recipe_refine.py`: swaps on pool plans;
  family rule across pool; legacy plan swap still works.
- Serializer tests: `meals` vs `days`, `counts`, `shortfall`; create request
  rejects legacy fields and all-zero counts.
- Frontend vitest: `planMeals` pool helpers, `SlotSection`, `SlotStrip`,
  `MealRow`, `PlanView` pool vs legacy branch, `CreatePlan` steppers +
  presets; `e2e/helpers/mocks.ts` gains a pool fixture.
- Social: `test_facts.py` showcase on a pool plan.
- Removed with the code: tests for the overlay, transform, whole-plan prompt,
  `MealPlanService`, `shopping_list.py`, validation day checks.

## 12. Open questions

None blocking. Decisions taken: prompt does not override counts; form
remembers last counts via `prefillFrom`; family dedupe is pool-wide;
calorie target per slot = existing `_SLOT_DEFAULT_KCAL` until the nutrition
project lands.
