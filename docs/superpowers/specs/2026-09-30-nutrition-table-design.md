# Nutrition from real data: per-100 g table on canonical ingredients

**Date:** 2026-09-30
**Status:** approved design, awaiting implementation plan
**Owner decisions:** approach B (extend `CanonicalIngredient`); nutrients =
calories, protein, carbs, fat only; strict — a recipe that cannot be fully
computed is not published; no display caveats.

## 1. Problem

Every nutrition number the product shows is a Gemini guess made at curation
(`CuratedRecipe.base_nutrition`) or at gap fill (LLM meal
`nutritional_info`). The guesses have had the wrong basis (per portion vs per
recipe) twice in production and were repaired by heuristics
(`nutrition_basis_repair`, `nutrition_density`) that the code itself says are
"NOT a nutrition facts source". The repo has no food-composition data at all.

The corpus is already keyed for the fix: 98 % of ingredient lines carry a
`canonical` slug and every published recipe passes the catalog-mapping gate,
so every non-optional ingredient resolves to one of the 291 canonicals.

## 2. Goal

Nutrition becomes arithmetic: for each ingredient line, grams × nutrients per
100 g of its canonical ingredient, summed over the recipe. The only inputs are
the recipe's own ingredient lines and three per-canonical tables built once
from public data (USDA FoodData Central SR Legacy, Frida for gaps): nutrients
per 100 g, density for volume units, piece weight for count units.

A published recipe always computes completely, so the UI never needs a
caveat. Gemini stops being asked for `base_nutrition`.

## 3. Non-goals

- Fibre, sugar, salt, micronutrients.
- Cooked/raw yield factors: values are for the as-bought form (raw meat, dry
  pasta), matching how recipe quantities are written.
- Per-user calorie targets, `_SLOT_DEFAULT_KCAL`, ranking weights.
- Live lookups against any external API at runtime.
- Re-curating recipe quantities (bad quantities surface as implausible
  results and are fixed in the corpus by the existing tools).

## 4. Data model

`CanonicalIngredient` (`diet_planner/models/catalog.py`) gains, all nullable:

| field | type | meaning |
|---|---|---|
| `kcal_per_100g` | Decimal(7,2) | energy, as-bought |
| `protein_per_100g` | Decimal(6,2) | g |
| `carbs_per_100g` | Decimal(6,2) | g |
| `fat_per_100g` | Decimal(6,2) | g |
| `density_g_per_ml` | Decimal(5,3) | needed only for ingredients that appear in volume units; NULL means "volume not allowed" |
| `unit_weights` | JSON | ingredient-specific count units, e.g. `{"stroužek": 5, "plátek": 20, "svazek": 30}` |
| `nutrition_source` | Char(64) | `usda:<fdc_id>`, `frida:<id>`, `manual:<note>` |

`avg_piece_weight_g` (exists) is the weight of "1 ks". `has_nutrition`
property: all four nutrient fields non-null.

`CuratedRecipe` gains `nutrition_blockers` (JSON list, default `[]`) —
`[{name, canonical, unit, reason}]` for lines that could not convert, the
sibling of the existing `shopping_blockers`. Empty on a fully computed
recipe.

Source of truth stays `diet_planner/data/canonical_ingredients.yaml`; each
entry gains a `nutrition:` block (`kcal, protein, carbs, fat, density,
piece_weight_g, unit_weights, source`). `seed_canonical_ingredients` writes
the new fields (and `avg_piece_weight_g`) on every run. `typical_unit_weights.yaml`
is folded into the entries and deleted; `piece_weights.load_piece_weights`
reads the DB table instead. Migration 0041: additive, nullable, no data
rewrite.

Lookups: `nutrition_lookups.nutrition_table()` returns
`{slug: NutrientRow(kcal, protein, carbs, fat, density, piece_weight_g,
unit_weights)}` from the DB in one query, cached per request/process the same
way `category_table()` is.

## 5. Building the tables

Management command `import_usda_nutrition --sr-legacy <path> [--write-yaml]
[--report <path>]`:

1. Reads the USDA SR Legacy bulk JSON (downloaded by the operator into the
   scratchpad; never committed; public domain).
2. For each canonical: search query = `usda_query` from the YAML entry if
   present, else the English `name`; pick the best-scoring `description`
   (token overlap, prefer "raw" / unprepared forms, penalise "cooked",
   "canned" unless the canonical's category is `canned`). Record a
   confidence 0–1.
3. Extract nutrients 1008 (kcal), 1003 (protein), 1005 (carbohydrate by
   difference), 1004 (total fat). Extract portions: `cup` / `tbsp` / `tsp`
   gram weights → density = grams / ml (cup 240, tbsp 15, tsp 5 — USDA's own
   volumes); `medium`, `each`, `clove`, `slice`, `bunch` → `piece_weight_g`
   / `unit_weights`.
4. `--report` writes a CSV with one row per canonical: slug, name_cs, USDA
   description, fdc_id, kcal, protein, carbs, fat, density, piece weight,
   confidence, notes. The operator publishes it as a private artifact for the
   owner's review.
5. `--write-yaml` writes the `nutrition:` blocks into
   `canonical_ingredients.yaml` for rows with confidence ≥ 0.6 and leaves
   the rest empty with `source: needs_review`.

Low-confidence and unmatched rows are filled by hand (Frida or a kitchen
reference) with `source: frida:<id>` / `manual:<note>`. The command is
idempotent and re-runnable; existing `manual:` / `frida:` rows are never
overwritten.

Acceptance for the data: every canonical that appears in a published recipe
has nutrients; every canonical that appears in a volume unit has density;
every canonical that appears in a count unit has a piece weight or the
specific `unit_weights` key. The backfill dry run (§8) is the checker.

## 6. Grams per line

New `diet_planner/services/line_mass.py`, the single line → grams rule used
by nutrition, `ingredient_mass` and pricing:

```
line_grams(line, row) -> LineMass(grams: float | None, method: str, reason: str | None)
```

- `quantity` null/0 → `grams=0, method='to_taste'` (never blocks).
- Mass units (`g, gram, kg, dkg, mg`) → direct. A non-empty quantity that
  does not parse ("1/2", "cca 200") is `bad_quantity` and blocks.
- Volume units (`ml, l, dl, cl, lžíce/pl/tbsp 15 ml, lžička/čl/tsp 5 ml,
  hrnek/šálek/cup 250 ml, sklenice 300 ml, konzerva/plechovka 400 ml`)
  → ml × `density_g_per_ml`; no density → `None, reason='no_density'`.
- Count units (`ks, kus, kusy, kusů, stroužek, plátek, svazek, hrst, snítka,
  lístek, špetka, balení`) → `unit_weights[unit]` if present, else for
  `ks/kus*` `avg_piece_weight_g`, else `None, reason='no_piece_weight'`; other count
  units without a `unit_weights` entry → `None, reason='no_unit_weight'`;
  garnish units carry a fixed default (`špetka 1 g, snítka 2 g, lístek 1 g`).
- Unit vocabulary and aliases live in one place (`services/unit_vocab.py`),
  imported by `line_mass`, `units.py` (pricing) and `ingredient_mass`.
  `ingredient_mass.estimate_mass_g` keeps its lower-bound API and delegates.

## 7. Compute

New `diet_planner/services/recipe_nutrition.py`:

```
compute_recipe_nutrition(ingredients, table) -> RecipeNutrition(
    calories, protein, carbs, fat,          # whole-recipe totals, floats
    lines_total, lines_converted,
    unconverted: [ {name, canonical, unit, reason} ],
    complete: bool)                          # every non-optional line converted
```

Optional lines that convert are included; optional lines that do not are
listed but never make the result incomplete. Rounding: calories to int,
macros to one decimal, done by the caller when writing `base_nutrition`.

`base_nutrition` written by curation / backfill:
`{"calories": 1840, "protein": 96.5, "carbs": 210.0, "fat": 61.2,
"source": "computed", "computed_at": "<iso>"}` — the same whole-recipe-for-
`base_servings` basis `scale_recipe_to_meal`, `per_portion_calories`,
`portions_for_target` and `score_recipe` already consume. The serving path
does not change.

## 8. Curation gate

In `recipe_curation` after `map_ingredients`:

1. `compute_recipe_nutrition`. Incomplete → the recipe stays a DRAFT with
   `nutrition_blockers` set to the unconverted lines (the same pattern as
   `shopping_blockers`: drafts are never "rejected", they simply cannot be
   promoted while blockers exist). `base_nutrition` is left empty.
2. Complete → `base_nutrition` = computed. The Gemini curation prompt no
   longer requests `base_nutrition`; `build_recipe_fields` ignores any it
   returns. `correct_nutrition_basis` and `nutrition_density` are deleted;
   `nutrition_basis_repair` and its command are deleted (their job is gone).
3. `check_nutrition_plausibility` runs on the computed value. Outside the
   role band → `nutrition_blockers = [{reason: 'implausible', per_portion_kcal}]`
   (this now means a wrong quantity, density or piece weight to fix in the
   corpus). The Atwater check is dropped (computed values satisfy it by
   construction).

`promote_curated_recipes` (by id, as always) adds a third skip condition next
to `skipped_unmapped` / `skipped_judge`: `skipped_nutrition` when
`nutrition_blockers` is non-empty or `base_nutrition.source != 'computed'`.
`remap_curated_recipes` recomputes nutrition after remapping so a dictionary
fix clears blockers without a re-curation.

## 9. Backfill

New command `recompute_nutrition [--status published|draft|all] [--apply]
[--report <csv>]`:

- Dry run (default): per recipe old kcal → new kcal, delta %, `complete`;
  aggregates unconverted lines by `(canonical, unit, reason)` with counts —
  the worklist for §5. Summary: recipes total / complete / incomplete;
  largest deltas.
- `--apply`: refuses if any PUBLISHED recipe is incomplete (exit 1 with the
  worklist) unless `--skip-incomplete`, which leaves those rows untouched and
  lists them. Writes `base_nutrition` for complete rows and prints a
  REVERSAL map (`id: old_base_nutrition`) like `repair_nutrition_basis` did.
- Afterwards `refresh_stale_recipe_cache --apply` re-derives cached `Recipe`
  rows; its `rebuild_meal` switches to `render_curated_meal` so sides are
  included (fixes the known drift).

Run on prod via the console harness; the dry-run report is reviewed by the
owner before apply.

## 10. Gemini gap-fill meals and sides

- `meal_pool`: after `_normalise_generated`, resolve each ingredient's
  canonical with `resolve_canonical`; if `compute_recipe_nutrition` is
  complete, replace `nutritional_info` with the computed per-meal totals
  (servings 1) and `nutrition_source='computed'`; otherwise keep Gemini's
  numbers with `nutrition_source='estimated'`. The recipe page shows a small
  "odhad" badge (EN: estimate) only when `estimated`.
- `priloha.SIDES` drop their hand-typed kcal/macros; `side_nutrition` computes
  from the side ingredient's canonical and grams through §7. The side rows keep
  only key, name, ingredient canonical, grams per portion.

## 11. Display

`nutritional_info` on every stored meal (curated and generated) carries
explicit `basis: "total"` and `servings`, plus `nutrition_source`. Frontend
`nutritionBasisFor` reads `basis` when present and falls back to the slug
heuristic for old rows. Two bugs fixed: `RecipePage` JSON-LD and the Django
SSR `public_recipe_view` divide by servings before emitting per-portion
`NutritionInformation`. `social/facts._per_portion_kcal` reads `basis`.

## 12. Testing

- `test_line_mass.py`: every unit family; density present/absent; ks with
  piece weight, with `unit_weights`, without either; null quantity;
  Czech/Slovak/English aliases; `ingredient_mass` parity.
- `test_recipe_nutrition.py`: a hand-checked recipe (e.g. 400 g chicken
  breast 165 kcal/100 g + 200 g rice + 1 lžíce oil at density 0.92) →
  exact totals; optional line handling; `complete` semantics.
- `test_import_usda_nutrition.py`: a 20-food fixture slice of SR Legacy →
  matching, nutrient ids, portion-derived density and piece weight,
  confidence, `--write-yaml` idempotency, `manual:` rows preserved.
- Curation: incomplete → held with reason; complete → computed source;
  implausible → held; prompt no longer contains `base_nutrition`.
- Backfill: dry-run report content; `--apply` refusal; `--skip-incomplete`;
  reversal map; cache refresh includes sides.
- Gap meals: computed vs estimated stamping.
- Frontend vitest: `nutritionBasisFor` with `basis`; JSON-LD per portion;
  "odhad" badge. Backend: SSR per-portion values.
- Existing suites that seed `base_nutrition={'calories': N}` fixtures keep
  working (the shape is unchanged).

## 13. Rollout

1. PR: models + migration, unit vocab, line_mass, recipe_nutrition, curation
   gate, backfill command, gap-meal stamping, sides, display fixes, the
   import command, and the seeded YAML with the reviewed table.
2. Owner reviews the 291-row table artifact before the YAML is committed.
3. Deploy; on prod: `seed_canonical_ingredients` runs at boot (existing);
   `recompute_nutrition` dry run → owner reads the delta list → `--apply` →
   `refresh_stale_recipe_cache --apply`.
4. `/qa-prod` addendum: three recipes' numbers checked by hand against the
   table; a generated gap meal shows "odhad" only when estimated.

## 14. Open questions

None blocking. Decisions taken: as-bought basis; optional lines never block;
sides computed from the table; Gemini gap meals may stay estimated (labelled);
the plausibility check is kept as a data-quality hold.
