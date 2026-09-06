# Dish Roles, Příloha and Dish-Family Dedupe — Design

**Date:** 2026-09-06
**Status:** approved, not built
**Related:** `diet_planner/services/recipe_retrieval.py` (slot gates, selection,
overlay), `diet_planner/management/commands/retag_dish_roles.py` (the tag pass
this extends), `diet_planner/services/recipe_curation.py` (intake),
`docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md` (the swap
paths that must stay consistent), memory `mains-without-priloha-gap`.

## The problem

The first automated showcase post (goal 143, ISO week 2026-W37) described a
day the planner really produced for "Chci zhubnout, hodně bílkovin, snídaně a
večeře lehké, oběd sytý":

| slot | dish | kcal |
|---|---|---|
| lunch | Lečo | 644 |
| dinner | Lečo s klobásou a vejci | 460 |

Nobody in the Czech market eats lečo on its own, and nobody eats it as an oběd.
Three defects in the corpus and the planner combine to produce this:

1. **The role vocabulary cannot say "quick supper".** `dish_role` has
   main/light/soup/side/dessert. `light` lumps breakfast dishes and quick
   supper dishes together and the tag prompt gives only international examples
   (omelettes, toasts, shakshuka), so Gemini saw klobása and eggs and tagged
   all three lečo recipes `main`. `main` carries an oběd. The breakfast slot
   also admits `main`, so a guláš breakfast is possible in principle.
2. **The corpus has no concept of a příloha.** Source sites write "podáváme s
   chlebem" in prose; curation keeps the ingredient list, so bread, potatoes,
   rice and knedlík vanish from every omáčka, guláš, řízek and lečo. The plan
   card, the calories and the shopping list are all incomplete for the
   majority of the 94 Czech mains.
3. **Nothing stops the same dish family twice in a day.** The novelty penalty
   is per exact slug; the two lečo rows are different slugs, and the
   ingredient-reuse bonus actively favours the second lečo once the first is
   chosen.

A fourth, smaller defect: `domaci-leco` (18 servings of lard, onion, pepper,
tomato, salt) is a preserving base published as a main.

## Goals

1. A dish can only carry the slots it carries in Czech eating culture: lečo at
   večeře, never at oběd or snídaně; svíčková at oběd or večeře; kaše at
   snídaně.
2. A main that is eaten with a příloha arrives with one, and the příloha is
   visible on the card, counted in the calories, and present in the shopping
   list and deals headline.
3. No two dishes of the same family (lečo, guláš, rizoto, řízek…) in one day;
   the same family is discouraged within one plan.
4. The owner reviews every role change before it is written, and can pin any
   dish's classification so a later LLM pass cannot undo it.
5. Untagged recipes behave exactly as today, so the code can deploy before the
   tag pass runs.

## Non-goals

- LLM-generated (non-curated) meals: they are written with full prompt
  context and may already include bread; they are not touched.
- Backfilling plans that already exist. Only new plans and new swaps get the
  příloha and the dedupe.
- Soups tagged `main` (kulajda, česnečka) carrying an oběd alone. The tag pass
  recalibration will move many to `soup`, but "polévka + hlavní chod" as a
  composed oběd is a separate feature.
- The "snídaně lehká" request being answered with a 546 kcal omelette. That is
  a facet-extraction defect, tracked separately.
- Attaching corpus side *recipes* (Kynutý houskový knedlík, Rýže s
  koriandrem). The owner chose the fixed příloha line; recipe sides can be
  layered on later without changing the meal shape defined here.
- Absolute prices for the příloha. The price engine stays dormant
  (`PRICE_DISPLAY_ENABLED=false`); the side gets a canonical so pricing works
  when it returns.

## Design

### 1. Corpus vocabulary

`CuratedRecipe.DishRole` gains two values and marks one as legacy:

| role | carries | examples |
|---|---|---|
| `main` | oběd, večeře | svíčková, guláš, řízek, pečeně, rizoto, plněné papriky |
| `supper` (new) | večeře | lečo, topinky, bramboráky, smažený sýr, chlebíčky, míchaná vejce k večeři |
| `breakfast` (new) | snídaně | kaše, vejce, toasty, palačinky, jogurt s granolou |
| `soup` | večeře (accompanies) | česnečka, kulajda, čočková polévka |
| `side` | small slots only | knedlík, rýže, dipy, saláty, **preserving bases** |
| `dessert` | snídaně, small slots | buchty, koláče |
| `light` (legacy) | as today | kept so untagged rows deploy safely; the tag pass rewrites every `light` row; a follow-up removes the value once prod reports zero |

Slot table (`_SLOT_ALLOWED_ROLES`):

| slot | allowed roles |
|---|---|
| breakfast | breakfast, dessert, light |
| lunch | main |
| dinner | main, supper, soup, light |
| small_meal, snack | any |

`main` is removed from the breakfast slot. `meal_types` remains the first gate
(when a dish may appear); `dish_role` remains the second (whether it can carry
the slot). Both gates must agree for a dish to be served, which is why the tag
pass re-emits both.

Two new fields on `CuratedRecipe`:

- `side_options` — JSON list, ordered by preference, drawn from the příloha
  vocabulary below. Empty list = complete dish. Meaningful for `main` and
  `supper`; ignored for other roles.
- `dish_family` — short lowercase ASCII key, max 60 chars, indexed. Examples:
  `leco`, `gulas`, `svickova`, `rizek`, `rizoto`, `omacka-rajska`,
  `omacka-koprova`, `polevka-cockova`, `kure-pecene`. Used only for dedupe.
  Empty = untagged, never deduped.

`nutrition_plausibility.ROLE_MIN_PORTION_KCAL` gets `breakfast` and `supper`
entries equal to today's `light` (150 kcal).

### 2. The tag pass

The classifier moves out of the management command into
`diet_planner/services/dish_classification.py`:

- `classify_recipes(recipes) -> dict[slug, Classification]` — one Gemini call
  per batch of 25, JSON out, temperature 0. Returns `dish_role`, `meal_types`,
  `side_options`, `dish_family` for every slug. The prompt is recalibrated with
  Czech examples for every role (table above), states the příloha vocabulary
  and its meaning, says that preserving bases and batch components are `side`,
  and that a `main`/`supper` that is eaten with bread, potatoes, rice, knedlík
  or pasta must list them in `side_options` in the order a Czech household
  would choose.
- `apply_overrides(slug, dish_family, classification) -> Classification` —
  applies `diet_planner/data/dish_role_overrides.yaml`. The file has two
  sections: `by_slug` (wins over everything) and `by_family` (applied when the
  LLM's or the slug override's `dish_family` matches). Each entry may set any
  subset of the four fields and carries a `note`. The file ships with the
  lečo family pinned (`supper`, `[dinner]`, `[chleb]`) and `domaci-leco` pinned
  `side`, and grows from the owner's review.
- Validation drops any value outside the vocabularies (role, meal type,
  příloha key) and logs it; a recipe with an unusable role is skipped, never
  half-written.

`retag_dish_roles` keeps its name and gains:

- `--force` now means "re-tag everything, including `light` and already-tagged
  rows"; the default still tags only untagged rows.
- The dry run prints a **review report**: for every recipe whose role or
  meal_types would change, one line `slug | name | cuisine | old → new |
  side_options | family`, grouped by cuisine, Czech first; then a role
  histogram before and after; then the lunch pool size for the tag
  combinations the product enforces (none, vegetarian, vegan, gluten_free,
  dairy_free) before and after, with a warning line when any of them falls
  below 15 recipes. The owner reads this report once, edits the overrides file,
  and re-runs the dry run until satisfied; only then runs the write.

`recipe_curation` calls `classify_recipes` on every newly curated recipe and
`apply_overrides` after it, so new recipes enter tagged and the command is
only ever a backfill.

### 3. The příloha table

`diet_planner/services/priloha.py` holds one static table, `SIDES`, keyed by
the vocabulary:

| key | name_cs | canonical | quantity per portion | display | kcal / portion | breaks tags |
|---|---|---|---|---|---|---|
| `chleb` | chléb | `bread-loaf` | 80 g | 2 krajíce | 200 | gluten_free |
| `brambory` | vařené brambory | `potatoes` | 250 g (raw) | 250 g | 190 | — |
| `ryze` | rýže | `rice-basmati` | 60 g (dry) | 60 g suché | 210 | — |
| `knedlik` | houskový knedlík | `bread-dumpling` (new canonical) | 120 g | 3 plátky | 240 | gluten_free, vegan |
| `testoviny` | těstoviny | `pasta` | 70 g (dry) | 70 g suché | 250 | gluten_free |

Each row also carries protein, carbs and fat per portion so the nutrition
block stays internally consistent, and a `with_cs` string ("s chlebem",
"s houskovým knedlíkem") for the plan card. The numbers are standard food-table values
for the purchased form (raw potatoes, dry rice and pasta, bought bread and
knedlík), rounded to 10 kcal, and are labeled in code as estimates. They live
in one place so the honest-copy rule stays checkable.

`bread-dumpling` (houskový knedlík, chilled, store-bought) is added to the
canonical dictionary, the price book and the availability list as a `common`
item. The other four canonicals already exist. A test asserts that every
`SIDES` canonical resolves in the dictionary, so a dictionary rename cannot
silently detach a side.

`pick_side(recipe, required_tags) -> Optional[Side]` returns the first
`side_options` entry whose `breaks tags` does not intersect the plan's
required dietary tags, or `None` when the recipe has no options or none fits.
A recipe with options and no fit is served bare and recorded as a gap with
reason `side_unavailable`, so the report can show how often a diet starves the
příloha.

### 4. Meal shape

`scale_recipe_to_meal(recipe, *, factor, portions, side=None)`:

- When `side` is given, the meal's `ingredients` list gets one more entry at
  the end: `{name, quantity, unit: 'g', canonical, catalog_id, optional:
  False, role: 'side'}` with quantity scaled by the served portions. Ordinary
  ingredients carry no `role`; downstream code that ignores unknown keys keeps
  working.
- `nutritional_info` totals include the side, scaled the same way.
- The meal gets `side: {key, name_cs, display}` for the card. `display` is the
  per-portion display string from the table; the card does not multiply it.

Because the side lives inside `ingredients` and `nutritional_info`, the
shopping list, the deals headline, the coherence judge, the cached public
`Recipe` row, the SSR recipe page and the social facts all pick it up with no
change. `_recipe_cache_fields` copies `ingredients` and `nutritional_info` as
today.

`portions_for_target(recipe, target, side=None)` sizes the slot on main plus
side per-portion kcal, so attaching bread cannot push a 700 kcal slot to 900
through the old per-main arithmetic. The side is served in the same number of
portions as the main, always.

### 5. Selection and dedupe

In `select_recipes_for_plan`:

- `used_families_today: set[str]` is reset per day; `used_families_plan:
  Counter[str]` accumulates across the plan. The selection loop drops any
  candidate whose family is already in `used_families_today` before scoring
  (`eligible_recipes_for_slot` gains an `exclude_families` argument for this).
  `score_recipe` gains `used_families: Counter` and subtracts
  `_RECENT_SERVE_PENALTY` (8.0) per earlier occurrence of the family in the
  plan, capped at 16, which stays below the 20-point wanted-ingredient weight
  so a requested dish still wins over a fresh one.
- An empty `dish_family` never matches anything.
- The same-day exclusion can starve a slot on tiny pools; when it does, the
  existing role-relaxed fallback path runs with the exclusion lifted and the
  gap is recorded as `family_relaxed`.

The swap paths (`_plan_swap_state` in views, the refine agent's candidate
pass) compute `used_families_today` from the other slots of the target day and
pass the same exclusion, so a swap or a refine cannot bring lečo back onto a
day that already has it. They also carry the plan-level penalty.

### 6. Write paths

All three curated write paths attach the side the same way, through one
helper `render_curated_meal(recipe, *, target_kcal, required_tags)` in
`recipe_retrieval` that calls `pick_side`, `portions_for_target` and
`scale_recipe_to_meal`:

- overlay (`overlay_curated_recipes`) for breakfast/lunch/dinner and the small
  slots;
- replace (`_commit_slot_swap`);
- refine accept (same helper) and refine **preview** (`_candidate_payload`),
  so the card shows the calories that accept will write, including the side.

`required_tags` come from `required_tags_for_goal(goal)` on every path.

### 7. Frontend

- Plan card (`PlanView.tsx`): when `meal.side` is present, a muted line under
  the dish name reads `s {name_cs}` (e.g. "s chlebem", "s houskovým
  knedlíkem"). The Czech dative form is stored in the table as `with_cs`, so
  the frontend never inflects.
- Recipe page and public recipe page (`RecipeIngredients.tsx`): ingredients
  with `role === 'side'` render under a small "Příloha" heading after the main
  list, with the same portion stepper scaling. Nothing else on the page
  changes; the nutrition block already shows the summed totals.
- Copy is written by Claude with an English gloss for review, per the Czech
  copy rule.

### 8. Rollout

1. Migration (two fields, two choices) and all code ship in one PR. Untagged
   and `light` rows behave exactly as today, so no flag is needed.
2. On prod, `retag_dish_roles --force --dry-run` produces the review report.
   The owner reviews it, the overrides file is updated in a follow-up PR if
   needed, and the dry run is repeated until the report is accepted.
3. `retag_dish_roles --force` writes. A read-only probe confirms zero `light`
   rows, `domaci-leco` is `side`, and the lečo family is `supper` with
   `[dinner]` and `[chleb]`.
4. Verification: a fresh QA plan whose prompt asks for Czech classics; assert
   lečo appears only at dinner with bread and never twice in a day, svíčková
   arrives with knedlík, the shopping list contains the side, and the deals
   headline counts it. Then `/qa-prod`.
5. Memory `mains-without-priloha-gap` is updated with the outcome.

The tag pass is a mutating management command and may run through
`prod_run.py`; the review gate is what makes it safe, not the harness.

## Testing

Backend (Django test runner, sqlite):

- `priloha`: every canonical resolves; every row has all nutrients; `pick_side`
  honours ordering and dietary breaks; no fit → `None`.
- `scale_recipe_to_meal` with a side: ingredient appended with `role`,
  quantity and totals scale with portions, `side` object present, no side →
  identical output to today (regression).
- `portions_for_target` with a side counts the side kcal.
- Slot table: `main` rejected at breakfast, `supper` rejected at lunch and
  breakfast, `light` still passes where it did.
- Dedupe: two lečo-family recipes, one slot each on the same day → second
  excluded; across days → penalised; empty family → untouched; tiny pool →
  `family_relaxed` gap.
- Swap and refine: a candidate whose family is already on the day is not
  offered.
- `dish_classification`: parsing, vocabulary validation, `by_slug` beats
  `by_family` beats LLM; the shipped overrides file parses and every slug and
  family key it mentions is well-formed.
- `retag_dish_roles`: dry run writes nothing and prints the report sections;
  `--force` rewrites `light` rows; the pool-size warning fires below 15.
- Curation: a new recipe leaves intake with all four fields set.

Frontend (vitest): card renders the side line only when present; ingredient
component groups `role: 'side'` under "Příloha" and scales it with the
stepper.

## Risks

- **Pool shrinkage.** Moving quick suppers out of `main` shrinks the lunch
  pool, and gluten-free lunches are already thin (18 of 372 in July). The
  dry-run pool report exists to make this visible before writing; if a
  combination falls below 15 the owner decides between accepting the gap and
  acquiring recipes.
- **LLM drift.** A later re-tag could flip a dish back. The overrides file is
  the answer; every owner correction goes there, not into a one-off SQL fix.
- **Calorie honesty.** The side kcal are table estimates, the main's are from
  the source recipe. Both are already labeled estimates in the product; the
  spec does not change that claim.
