# Nutrition Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recipe nutrition (kcal, protein, carbs, fat) becomes arithmetic over a per-100 g table on `CanonicalIngredient`, built once from USDA SR Legacy; Gemini stops guessing it; a recipe that cannot be fully computed cannot be published.

**Architecture:** `CanonicalIngredient` carries nutrients per 100 g, density and piece/unit weights, seeded from `canonical_ingredients.yaml`. One `line_mass.line_grams` converts any ingredient line to grams; `recipe_nutrition.compute_recipe_nutrition` sums grams × nutrients. Curation writes computed `base_nutrition` or `nutrition_blockers`; promotion refuses blocked drafts; a backfill command recomputes the corpus with a dry-run worklist. Gap-fill meals compute when their ingredients resolve, else stay labelled estimates. Display gains an explicit basis.

**Tech Stack:** Django 5.x / DRF, PyYAML, React 18 + TypeScript + vitest. Spec: `docs/superpowers/specs/2026-09-30-nutrition-table-design.md`. Branch `feat/nutrition-table` (from develop d241f19).

**Conventions**
- Backend tests: `GEMINI_API_KEY=dummy python3 -m pytest <files> -q` (CI runner) — also works for Django `TestCase` modules. Full gate: `GEMINI_API_KEY=dummy python3 -m pytest diet_planner billing analytics social -q -x`.
- Frontend: `cd frontend && npx vitest run <paths>`; `npx tsc --noEmit`; `npx eslint <files>` (repo-wide `npm run lint` has pre-existing errors).
- Migration 0022 seeds a handful of canonicals into the TEST database (mouka, cukr, olej, …); tests that need nutrition rows create their own via `diet_planner/tests/factories.py::make_canonical`.
- Commit after every task with the trailer:
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_011rNrSwRcHVjx4Bk14ouSFC`.
- Czech UI strings are final and carry an `// EN:` gloss.

---

## File map

**Create**
- `diet_planner/migrations/0041_nutrition_table.py` (makemigrations)
- `diet_planner/services/unit_vocab.py` — one unit alias/volume/count vocabulary
- `diet_planner/services/line_mass.py` — `line_grams`
- `diet_planner/services/recipe_nutrition.py` — `compute_recipe_nutrition`
- `diet_planner/management/commands/import_usda_nutrition.py`
- `diet_planner/management/commands/recompute_nutrition.py`
- `diet_planner/tests/fixtures/usda_sr_legacy_slice.json` — 12-food slice
- Tests: `test_nutrition_model.py`, `test_line_mass.py`, `test_recipe_nutrition.py`, `test_import_usda_nutrition.py`, `test_curation_nutrition_gate.py`, `test_recompute_nutrition.py`, `test_gap_meal_nutrition.py`; frontend `lib/nutrition.test.ts` additions.

**Modify**
- `diet_planner/models/catalog.py`, `diet_planner/models/curated.py`
- `diet_planner/data/canonical_ingredients.yaml` (nutrition blocks), delete `typical_unit_weights.yaml`
- `diet_planner/management/commands/seed_canonical_ingredients.py`, `promote_curated_recipes.py`, `remap_curated_recipes.py`, `refresh_stale_recipe_cache.py`
- `diet_planner/services/piece_weights.py`, `nutrition_lookups.py`, `ingredient_mass.py`, `units.py`, `nutrition_plausibility.py`, `recipe_curation.py`, `recipe_retrieval.py` (nutritional_info shape), `priloha.py`, `meal_pool.py`
- `diet_planner/llm_service.py` (curation prompt)
- `llm_diet_planner_project/views.py` (SSR per-portion), `social/facts.py`
- `frontend/src/lib/nutrition.ts`, `frontend/src/pages/RecipePage.tsx`, `frontend/src/pages/PublicRecipePage.tsx`

**Delete**
- `diet_planner/services/nutrition_density.py`, `nutrition_basis_repair.py`, `management/commands/repair_nutrition_basis.py` and their tests (`test_nutrition_density.py`, `test_nutrition_basis_repair.py`, `test_repair_nutrition_basis.py`); `test_curation_nutrition_basis.py` is replaced by `test_curation_nutrition_gate.py`.

---

## Part A — data model and conversion

### Task 1: Nutrition fields on `CanonicalIngredient`, `nutrition_blockers` on `CuratedRecipe`, seed + migration

**Files:**
- Modify: `diet_planner/models/catalog.py` (after `avg_piece_weight_g`), `diet_planner/models/curated.py` (after `shopping_blockers`), `diet_planner/management/commands/seed_canonical_ingredients.py`, `diet_planner/services/piece_weights.py`, `diet_planner/services/nutrition_lookups.py`, `diet_planner/data/canonical_ingredients.yaml` (schema comment + fold in piece weights)
- Delete: `diet_planner/data/typical_unit_weights.yaml`
- Create: migration `0041_nutrition_table.py`, `diet_planner/tests/test_nutrition_model.py`

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_nutrition_model.py
"""Per-100 g nutrition lives on the canonical ingredient; the YAML seeds it."""
from decimal import Decimal
from io import StringIO
from pathlib import Path
import tempfile

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CanonicalIngredient, CuratedRecipe
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.piece_weights import load_piece_weights, clear_cache


class NutritionFieldsTest(TestCase):
    def test_has_nutrition_requires_all_four_nutrients(self):
        c = CanonicalIngredient.objects.create(name='Chicken breast', slug='t-chicken',
                                               kcal_per_100g=165, protein_per_100g=31,
                                               carbs_per_100g=0, fat_per_100g=3.6)
        self.assertTrue(c.has_nutrition)
        c.fat_per_100g = None
        self.assertFalse(c.has_nutrition)

    def test_curated_recipe_defaults_to_no_blockers(self):
        r = CuratedRecipe.objects.create(name_cs='x', base_servings=1)
        self.assertEqual(r.nutrition_blockers, [])


class SeedNutritionTest(TestCase):
    def _seed(self, yaml_text):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8') as fh:
            fh.write(yaml_text)
        out = StringIO()
        call_command('seed_canonical_ingredients', file=fh.name, stdout=out)
        Path(fh.name).unlink()
        return out.getvalue()

    def test_seed_writes_nutrition_density_and_unit_weights(self):
        self._seed("""
- name: olive oil
  name_cs: olivový olej
  category: oils
  nutrition:
    kcal: 884
    protein: 0
    carbs: 0
    fat: 100
    density: 0.92
    source: usda:171413
- name: garlic
  name_cs: česnek
  category: vegetables
  nutrition:
    kcal: 149
    protein: 6.4
    carbs: 33.1
    fat: 0.5
    piece_weight_g: 40
    unit_weights: {stroužek: 5}
    source: usda:169230
""")
        oil = CanonicalIngredient.objects.get(slug='olive-oil')
        self.assertEqual(oil.kcal_per_100g, Decimal('884'))
        self.assertEqual(oil.density_g_per_ml, Decimal('0.920'))
        self.assertEqual(oil.nutrition_source, 'usda:171413')
        garlic = CanonicalIngredient.objects.get(slug='garlic')
        self.assertEqual(garlic.avg_piece_weight_g, Decimal('40'))
        self.assertEqual(garlic.unit_weights, {'stroužek': 5})
        self.assertTrue(garlic.has_nutrition)

    def test_seed_without_nutrition_block_leaves_fields_null(self):
        self._seed("- name: mystery\n  category: other\n")
        c = CanonicalIngredient.objects.get(slug='mystery')
        self.assertIsNone(c.kcal_per_100g)
        self.assertFalse(c.has_nutrition)

    def test_nutrition_table_and_piece_weights_read_the_db(self):
        self._seed("""
- name: onion
  category: vegetables
  nutrition: {kcal: 40, protein: 1.1, carbs: 9.3, fat: 0.1, piece_weight_g: 110, source: usda:170000}
""")
        clear_cache()
        row = nutrition_table()['onion']
        self.assertEqual((row.kcal, row.protein, row.carbs, row.fat), (40.0, 1.1, 9.3, 0.1))
        self.assertEqual(row.piece_weight_g, 110.0)
        self.assertIsNone(row.density)
        self.assertEqual(load_piece_weights()['onion'], 110.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_nutrition_model.py -q`
Expected: errors — unknown field `kcal_per_100g`, no `nutrition_table`.

- [ ] **Step 3: Model fields**

In `diet_planner/models/catalog.py`, after `avg_piece_weight_g`:

```python
    # --- Nutrition per 100 g of the AS-BOUGHT form (raw meat, dry pasta). Built
    # from USDA SR Legacy / Frida by `import_usda_nutrition`, seeded from
    # data/canonical_ingredients.yaml. NULL = not yet tabled; a recipe using
    # such an ingredient cannot be published (nutrition_blockers).
    kcal_per_100g = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    protein_per_100g = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    carbs_per_100g = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    fat_per_100g = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    density_g_per_ml = models.DecimalField(
        max_digits=5, decimal_places=3, null=True, blank=True,
        help_text="Grams per millilitre; required only for ingredients used in volume units",
    )
    unit_weights = models.JSONField(
        default=dict, blank=True,
        help_text='Grams for ingredient-specific count units, e.g. {"stroužek": 5, "plátek": 20}',
    )
    nutrition_source = models.CharField(
        max_length=64, blank=True,
        help_text="usda:<fdc_id> | frida:<id> | manual:<note>",
    )

    @property
    def has_nutrition(self) -> bool:
        return all(v is not None for v in (
            self.kcal_per_100g, self.protein_per_100g, self.carbs_per_100g, self.fat_per_100g))
```

In `diet_planner/models/curated.py`, after `shopping_blockers`:

```python
    nutrition_blockers = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Ingredient lines whose grams or nutrients could not be computed "
            "[{name, canonical, unit, reason}]. Non-empty = cannot be promoted."
        ),
    )
```

- [ ] **Step 4: Seed command + YAML schema + piece weights from DB**

In `seed_canonical_ingredients.py`, extend `defaults` inside the row loop:

```python
            nutrition = row.get('nutrition') or {}
            defaults.update({
                'kcal_per_100g': nutrition.get('kcal'),
                'protein_per_100g': nutrition.get('protein'),
                'carbs_per_100g': nutrition.get('carbs'),
                'fat_per_100g': nutrition.get('fat'),
                'density_g_per_ml': nutrition.get('density'),
                'unit_weights': nutrition.get('unit_weights') or {},
                'nutrition_source': nutrition.get('source') or '',
            })
            if nutrition.get('piece_weight_g') is not None:
                defaults['avg_piece_weight_g'] = nutrition['piece_weight_g']
```

Update the YAML header comment with the `nutrition:` schema (`kcal, protein, carbs, fat` per 100 g as bought; `density` g/ml; `piece_weight_g`; `unit_weights`; `source`; optional `usda_query` search hint). Fold `typical_unit_weights.yaml` into the entries: for each slug in `grams_per_piece`, add `nutrition: {piece_weight_g: <g>}` to the matching entry (a small one-off Python snippet; the entries for garlic keep the clove note as `unit_weights: {stroužek: 5}` and `piece_weight_g: 5` as today). Delete `typical_unit_weights.yaml`.

Rewrite `piece_weights.py`:

```python
"""Grams per "1 ks" for count-unit canonicals, read from CanonicalIngredient.
avg_piece_weight_g (seeded from data/canonical_ingredients.yaml `nutrition.piece_weight_g`).
Bridges recipe counts ("2 ks cibule") and weight-priced catalog rows."""
from functools import lru_cache
from typing import Dict


@lru_cache(maxsize=1)
def load_piece_weights() -> Dict[str, float]:
    from diet_planner.models.catalog import CanonicalIngredient
    out: Dict[str, float] = {}
    rows = CanonicalIngredient.objects.exclude(avg_piece_weight_g=None).values_list(
        'slug', 'avg_piece_weight_g')
    for slug, grams in rows:
        try:
            g = float(grams)
        except (TypeError, ValueError):
            continue
        if g > 0:
            out[slug] = g
    return out


def clear_cache() -> None:
    load_piece_weights.cache_clear()
```

Callers (`recipe_pricing.py`, `build_price_book.py`, `audit_price_book.py`, `nutrition_lookups.piece_weight_table`) keep working unchanged. Because the cache is process-wide, tests that seed rows call `clear_cache()` (as the test above does); add `clear_cache()` at the end of `seed_canonical_ingredients.handle`.

In `nutrition_lookups.py` add:

```python
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NutrientRow:
    kcal: float
    protein: float
    carbs: float
    fat: float
    density: Optional[float]          # g per ml, None = volume units not convertible
    piece_weight_g: Optional[float]   # grams per "1 ks"
    unit_weights: Dict[str, float]    # ingredient-specific count units


def nutrition_table() -> Dict[str, NutrientRow]:
    """Canonical slug -> NutrientRow for every canonical with complete nutrients."""
    out: Dict[str, NutrientRow] = {}
    fields = ('slug', 'kcal_per_100g', 'protein_per_100g', 'carbs_per_100g',
              'fat_per_100g', 'density_g_per_ml', 'avg_piece_weight_g', 'unit_weights')
    for slug, kcal, protein, carbs, fat, density, piece, uw in (
            CanonicalIngredient.objects.values_list(*fields)):
        if None in (kcal, protein, carbs, fat):
            continue
        out[slug] = NutrientRow(
            kcal=float(kcal), protein=float(protein), carbs=float(carbs), fat=float(fat),
            density=float(density) if density is not None else None,
            piece_weight_g=float(piece) if piece is not None else None,
            unit_weights={str(k): float(v) for k, v in (uw or {}).items()},
        )
    return out
```

- [ ] **Step 5: Migration, tests, existing suites**

Run: `GEMINI_API_KEY=dummy python3 manage.py makemigrations diet_planner -n nutrition_table` → 0041 with 7 AddField on CanonicalIngredient + 1 on CuratedRecipe.
Run: `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_nutrition_model.py diet_planner/tests/test_build_price_book.py diet_planner/tests/test_priloha.py diet_planner/tests/test_recipe_pricing.py -q` → pass (any test reading `typical_unit_weights.yaml` directly is updated to read the DB via `load_piece_weights` after seeding, or to read the YAML entries' `nutrition.piece_weight_g`).

- [ ] **Step 6: Commit**

```bash
git add diet_planner/models diet_planner/migrations/0041_nutrition_table.py diet_planner/management/commands/seed_canonical_ingredients.py diet_planner/services/piece_weights.py diet_planner/services/nutrition_lookups.py diet_planner/data diet_planner/tests
git commit -m "feat(nutrition): per-100g nutrients, density and unit weights on CanonicalIngredient; nutrition_blockers on CuratedRecipe"
```

### Task 2: `unit_vocab` + `line_grams`

**Files:**
- Create: `diet_planner/services/unit_vocab.py`, `diet_planner/services/line_mass.py`, `diet_planner/tests/test_line_mass.py`
- Modify: `diet_planner/services/units.py` (import aliases from vocab), `diet_planner/services/ingredient_mass.py` (delegate)

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_line_mass.py
from django.test import SimpleTestCase

from diet_planner.services.ingredient_mass import estimate_mass_g
from diet_planner.services.line_mass import line_grams
from diet_planner.services.nutrition_lookups import NutrientRow
from diet_planner.services.unit_vocab import normalize_unit, unit_kind


def row(density=None, piece=None, unit_weights=None):
    return NutrientRow(kcal=100, protein=1, carbs=1, fat=1, density=density,
                       piece_weight_g=piece, unit_weights=unit_weights or {})


class UnitVocabTest(SimpleTestCase):
    def test_aliases_normalise_across_languages(self):
        for raw, code in [('G', 'g'), ('gramů', 'g'), ('dkg', 'dkg'), ('dag', 'dkg'), ('Kg.', 'kg'),
                          ('ML', 'ml'), ('dl', 'dl'), ('lžíce', 'tbsp'), ('lžic', 'tbsp'), ('pl', 'tbsp'),
                          ('lžička', 'tsp'), ('čl', 'tsp'), ('hrnek', 'cup'), ('šálek', 'cup'),
                          ('ks', 'ks'), ('kusů', 'ks'), ('stroužek', 'stroužek'), ('stroužky', 'stroužek'),
                          ('plátek', 'plátek'), ('svazek', 'svazek'), ('hrst', 'hrst'), ('špetka', 'špetka'),
                          ('konzerva', 'konzerva'), ('plechovka', 'konzerva'), ('balení', 'balení')]:
            self.assertEqual(normalize_unit(raw), code, raw)

    def test_unit_kind(self):
        self.assertEqual(unit_kind('kg'), 'mass')
        self.assertEqual(unit_kind('tbsp'), 'volume')
        self.assertEqual(unit_kind('ks'), 'count')
        self.assertEqual(unit_kind('stroužek'), 'count')
        self.assertIsNone(unit_kind('furlong'))


class LineGramsTest(SimpleTestCase):
    def test_mass_units(self):
        self.assertEqual(line_grams({'quantity': 300, 'unit': 'g'}, row()).grams, 300)
        self.assertEqual(line_grams({'quantity': 1.5, 'unit': 'kg'}, row()).grams, 1500)
        self.assertEqual(line_grams({'quantity': 25, 'unit': 'dkg'}, row()).grams, 250)

    def test_volume_units_need_density(self):
        oil = row(density=0.92)
        self.assertAlmostEqual(line_grams({'quantity': 200, 'unit': 'ml'}, oil).grams, 184)
        self.assertAlmostEqual(line_grams({'quantity': 2, 'unit': 'lžíce'}, oil).grams, 27.6)
        self.assertAlmostEqual(line_grams({'quantity': 1, 'unit': 'hrnek'}, oil).grams, 230)
        r = line_grams({'quantity': 200, 'unit': 'ml'}, row())
        self.assertIsNone(r.grams)
        self.assertEqual(r.reason, 'no_density')

    def test_count_units(self):
        onion = row(piece=110)
        self.assertEqual(line_grams({'quantity': 2, 'unit': 'ks'}, onion).grams, 220)
        garlic = row(piece=40, unit_weights={'stroužek': 5})
        self.assertEqual(line_grams({'quantity': 3, 'unit': 'stroužky'}, garlic).grams, 15)
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'ks'}, garlic).grams, 40)
        r = line_grams({'quantity': 2, 'unit': 'ks'}, row())
        self.assertIsNone(r.grams)
        self.assertEqual(r.reason, 'no_piece_weight')
        r = line_grams({'quantity': 1, 'unit': 'plátek'}, row(piece=100))
        self.assertEqual(r.reason, 'no_unit_weight')

    def test_garnish_units_have_defaults(self):
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'špetka'}, row()).grams, 1)
        self.assertEqual(line_grams({'quantity': 2, 'unit': 'snítka'}, row()).grams, 4)

    def test_to_taste_is_zero_not_a_gap(self):
        r = line_grams({'quantity': None, 'unit': None}, row())
        self.assertEqual((r.grams, r.method), (0.0, 'to_taste'))
        self.assertEqual(line_grams({'quantity': 0, 'unit': 'g'}, row()).method, 'to_taste')

    def test_unknown_unit_and_missing_row(self):
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'furlong'}, row()).reason, 'unknown_unit')
        self.assertEqual(line_grams({'quantity': 100, 'unit': 'g'}, None).grams, 100)   # mass never needs a row
        self.assertEqual(line_grams({'quantity': 1, 'unit': 'ks'}, None).reason, 'no_piece_weight')

    def test_czech_decimal_comma(self):
        self.assertEqual(line_grams({'quantity': '1,5', 'unit': 'kg'}, row()).grams, 1500)


class IngredientMassParityTest(SimpleTestCase):
    def test_estimate_mass_still_lower_bound_via_line_grams(self):
        est = estimate_mass_g([
            {'quantity': 200, 'unit': 'g'},
            {'quantity': 2, 'unit': 'ks', 'canonical': 'onion'},
            {'quantity': 1, 'unit': 'ks', 'canonical': 'unknown'},
        ], {'onion': 110})
        self.assertEqual(est.grams, 420)
        self.assertEqual((est.known_lines, est.unknown_lines), (2, 1))
```

- [ ] **Step 2: Run to verify failure** — ImportError for `unit_vocab` / `line_mass`.

- [ ] **Step 3: `unit_vocab.py`**

```python
# diet_planner/services/unit_vocab.py
"""The one unit vocabulary for recipes, pricing and nutrition.

Codes: mass g/dkg/kg; volume ml/cl/dl/l/tsp/tbsp/cup/konzerva/sklenice;
count ks + ingredient-specific pieces (stroužek, plátek, svazek, hrst, balení);
garnish units with a fixed gram default (špetka, snítka, lístek).
"""
from typing import Dict, Optional, Tuple

ALIASES: Dict[str, str] = {
    # mass
    'g': 'g', 'gram': 'g', 'gramy': 'g', 'gramu': 'g', 'gramů': 'g', 'gramow': 'g', 'g.': 'g',
    'dkg': 'dkg', 'dag': 'dkg', 'deka': 'dkg',
    'kg': 'kg', 'kilogram': 'kg', 'kilogramy': 'kg', 'kilogramů': 'kg', 'kilogramow': 'kg', 'kg.': 'kg',
    # volume
    'ml': 'ml', 'mililitr': 'ml', 'mililitry': 'ml', 'mililitrů': 'ml', 'milliliter': 'ml', 'millilitre': 'ml', 'ml.': 'ml',
    'cl': 'cl', 'dl': 'dl', 'deci': 'dl', 'decilitr': 'dl', 'decilitry': 'dl',
    'l': 'l', 'litr': 'l', 'litry': 'l', 'litrů': 'l', 'litrow': 'l', 'liter': 'l', 'litre': 'l', 'l.': 'l',
    'lžička': 'tsp', 'lžičky': 'tsp', 'lžiček': 'tsp', 'lžičku': 'tsp', 'čl': 'tsp', 'čajová lžička': 'tsp',
    'lyzicka': 'tsp', 'lzicka': 'tsp', 'tsp': 'tsp', 'teaspoon': 'tsp',
    'lžíce': 'tbsp', 'lžíci': 'tbsp', 'lžic': 'tbsp', 'pl': 'tbsp', 'polévková lžíce': 'tbsp',
    'polevkova lzice': 'tbsp', 'lzice': 'tbsp', 'tbsp': 'tbsp', 'tablespoon': 'tbsp',
    'hrnek': 'cup', 'hrnky': 'cup', 'hrnků': 'cup', 'hrnku': 'cup', 'šálek': 'cup', 'šálky': 'cup',
    'salek': 'cup', 'cup': 'cup', 'cups': 'cup',
    'konzerva': 'konzerva', 'plechovka': 'konzerva', 'sklenice': 'sklenice',
    # count
    'ks': 'ks', 'ks.': 'ks', 'kus': 'ks', 'kusy': 'ks', 'kusů': 'ks', 'kusu': 'ks', 'kusow': 'ks',
    'piece': 'ks', 'pieces': 'ks', 'pcs': 'ks', 'pc': 'ks', 'szt': 'ks', 'sztuk': 'ks', 'sztuki': 'ks',
    'stroužek': 'stroužek', 'stroužky': 'stroužek', 'stroužků': 'stroužek', 'strouzek': 'stroužek',
    'plátek': 'plátek', 'plátky': 'plátek', 'plátků': 'plátek', 'platek': 'plátek',
    'svazek': 'svazek', 'svazky': 'svazek', 'svazků': 'svazek',
    'hrst': 'hrst', 'hrstka': 'hrst', 'malá hrst': 'hrst',
    'balení': 'balení', 'sáček': 'balení', 'balíček': 'balení',
    # garnish
    'špetka': 'špetka', 'špetky': 'špetka', 'spetka': 'špetka', 'pinch': 'špetka',
    'snítka': 'snítka', 'snítky': 'snítka',
    'lístek': 'lístek', 'lístky': 'lístek', 'lístků': 'lístek',
}

MASS_G: Dict[str, float] = {'g': 1.0, 'dkg': 10.0, 'kg': 1000.0}
VOLUME_ML: Dict[str, float] = {'ml': 1.0, 'cl': 10.0, 'dl': 100.0, 'l': 1000.0,
                               'tsp': 5.0, 'tbsp': 15.0, 'cup': 250.0,
                               'konzerva': 400.0, 'sklenice': 300.0}
COUNT_UNITS = ('ks', 'stroužek', 'plátek', 'svazek', 'hrst', 'balení')
GARNISH_G: Dict[str, float] = {'špetka': 1.0, 'snítka': 2.0, 'lístek': 1.0}


def normalize_unit(unit) -> str:
    if not unit:
        return ''
    key = str(unit).strip().lower()
    return ALIASES.get(key, key)


def unit_kind(code: str) -> Optional[str]:
    if code in MASS_G:
        return 'mass'
    if code in VOLUME_ML:
        return 'volume'
    if code in COUNT_UNITS:
        return 'count'
    if code in GARNISH_G:
        return 'garnish'
    return None


def to_base(value: float, unit) -> Tuple[float, Optional[str]]:
    """(base_value, dimension) for pricing: mass→g, volume→ml, count→ks.
    Garnish units are volume-ish for pricing (a pinch ≈ 0.3 ml)."""
    code = normalize_unit(unit)
    if code in MASS_G:
        return value * MASS_G[code], 'mass'
    if code in VOLUME_ML:
        return value * VOLUME_ML[code], 'volume'
    if code in COUNT_UNITS:
        return value, 'count'
    if code in GARNISH_G:
        return value * 0.3, 'volume'
    return value, None
```

`units.py` becomes a thin re-export so pricing callers do not change:

```python
"""Unit normalisation for pricing — re-exported from unit_vocab so pricing,
nutrition and mass estimation share one vocabulary."""
from diet_planner.services.unit_vocab import normalize_unit, to_base  # noqa: F401
```
(Check `test_build_price_book` still passes: `pinch` now maps to `špetka` → 0.3 ml volume as before; `cup` stays 250 ml.)

- [ ] **Step 4: `line_mass.py`**

```python
# diet_planner/services/line_mass.py
"""One ingredient line -> grams. Pure; never raises.

Mass units convert directly; volume units need the ingredient's density;
count units need its piece weight (`ks`) or an ingredient-specific unit weight
(`stroužek`, `plátek`, ...); garnish units carry a fixed default; a missing or
zero quantity is "to taste" = 0 g and never a gap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from diet_planner.services.nutrition_lookups import NutrientRow
from diet_planner.services.unit_vocab import (
    COUNT_UNITS, GARNISH_G, MASS_G, VOLUME_ML, normalize_unit,
)


@dataclass(frozen=True)
class LineMass:
    grams: Optional[float]
    method: str          # mass | volume | count | unit_weight | garnish | to_taste | none
    reason: Optional[str] = None  # no_density | no_piece_weight | no_unit_weight | unknown_unit


def _quantity(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        q = float(value) if isinstance(value, (int, float)) else float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None
    return q if q > 0 else None


def line_grams(line: dict, row: Optional[NutrientRow]) -> LineMass:
    qty = _quantity((line or {}).get('quantity'))
    if qty is None:
        return LineMass(0.0, 'to_taste')
    code = normalize_unit((line or {}).get('unit'))
    if code in MASS_G:
        return LineMass(round(qty * MASS_G[code], 3), 'mass')
    if code in VOLUME_ML:
        density = row.density if row is not None else None
        if not density:
            return LineMass(None, 'none', 'no_density')
        return LineMass(round(qty * VOLUME_ML[code] * density, 3), 'volume')
    if code in GARNISH_G:
        return LineMass(round(qty * GARNISH_G[code], 3), 'garnish')
    if code in COUNT_UNITS:
        uw = (row.unit_weights if row is not None else {}) or {}
        if code in uw and uw[code] > 0:
            return LineMass(round(qty * uw[code], 3), 'unit_weight')
        if code == 'ks':
            piece = row.piece_weight_g if row is not None else None
            if piece:
                return LineMass(round(qty * piece, 3), 'count')
            return LineMass(None, 'none', 'no_piece_weight')
        return LineMass(None, 'none', 'no_unit_weight')
    if code == '':
        # bare number, e.g. "2 vejce" written as quantity 2, unit null → treat as ks
        piece = row.piece_weight_g if row is not None else None
        if piece:
            return LineMass(round(qty * piece, 3), 'count')
        return LineMass(None, 'none', 'no_piece_weight')
    return LineMass(None, 'none', 'unknown_unit')
```

`ingredient_mass.py`: replace the body of `estimate_mass_g` so it builds a `NutrientRow`-like stub from `piece_weights` and calls `line_grams`:

```python
def estimate_mass_g(ingredients, piece_weights=None) -> MassEstimate:
    weights = piece_weights or {}
    grams = 0.0
    known = unknown = 0
    for line in (ingredients or []):
        if not isinstance(line, dict):
            unknown += 1
            continue
        slug = line.get('canonical') or ''
        row = NutrientRow(0, 0, 0, 0, density=1.0, piece_weight_g=weights.get(slug),
                          unit_weights={}) if slug else NutrientRow(0, 0, 0, 0, 1.0, None, {})
        lm = line_grams(line, row)
        if lm.method == 'to_taste' or lm.grams is None:
            unknown += 1
            continue
        grams += lm.grams
        known += 1
    return MassEstimate(grams=round(grams, 2), known_lines=known, unknown_lines=unknown)
```
(density 1.0 keeps the old "ml ≈ g" lower-bound behaviour for the mass gate; delete `DIRECT_UNITS`, `SPOON_UNITS`, `COUNT_UNITS` from the module; update `test_ingredient_mass.py` only where it imported those constants.)

- [ ] **Step 5: Run** — `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_line_mass.py diet_planner/tests/test_ingredient_mass.py diet_planner/tests/test_build_price_book.py diet_planner/tests/test_recipe_pricing.py diet_planner/tests/test_recipe_plausibility.py -q` → pass.

- [ ] **Step 6: Commit** — `git add diet_planner/services/unit_vocab.py diet_planner/services/line_mass.py diet_planner/services/units.py diet_planner/services/ingredient_mass.py diet_planner/tests && git commit -m "feat(nutrition): one unit vocabulary; line_grams with density, piece and unit weights"`

### Task 3: `compute_recipe_nutrition`

**Files:**
- Create: `diet_planner/services/recipe_nutrition.py`, `diet_planner/tests/test_recipe_nutrition.py`

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_recipe_nutrition.py
"""Nutrition is arithmetic: grams × nutrients per 100 g, summed over the recipe."""
from django.test import SimpleTestCase

from diet_planner.services.nutrition_lookups import NutrientRow
from diet_planner.services.recipe_nutrition import (
    compute_recipe_nutrition, computed_base_nutrition,
)

TABLE = {
    'chicken-breast': NutrientRow(165, 31, 0, 3.6, None, None, {}),
    'rice-basmati': NutrientRow(360, 7, 79, 0.6, None, None, {}),
    'olive-oil': NutrientRow(884, 0, 0, 100, 0.92, None, {}),
    'onion': NutrientRow(40, 1.1, 9.3, 0.1, None, 110, {}),
    'salt': NutrientRow(0, 0, 0, 0, None, None, {}),
}
RECIPE = [
    {'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g', 'canonical': 'chicken-breast'},
    {'name': 'rýže', 'quantity': 200, 'unit': 'g', 'canonical': 'rice-basmati'},
    {'name': 'olivový olej', 'quantity': 1, 'unit': 'lžíce', 'canonical': 'olive-oil'},
    {'name': 'cibule', 'quantity': 1, 'unit': 'ks', 'canonical': 'onion'},
    {'name': 'sůl', 'quantity': None, 'unit': None, 'canonical': 'salt'},
]


class ComputeTest(SimpleTestCase):
    def test_hand_checked_totals(self):
        n = compute_recipe_nutrition(RECIPE, TABLE)
        # 400 g chicken 660 kcal + 200 g rice 720 + 13.8 g oil 122.0 + 110 g onion 44 + salt 0
        self.assertAlmostEqual(n.calories, 660 + 720 + 13.8 * 8.84 + 44, places=1)
        self.assertAlmostEqual(n.protein, 124 + 14 + 0 + 1.21, places=2)
        self.assertAlmostEqual(n.fat, 14.4 + 1.2 + 13.8 + 0.11, places=2)
        self.assertTrue(n.complete)
        self.assertEqual((n.lines_total, n.lines_converted), (5, 5))
        self.assertEqual(n.unconverted, [])

    def test_missing_nutrients_block(self):
        n = compute_recipe_nutrition(RECIPE + [{'name': 'mystery', 'quantity': 50, 'unit': 'g', 'canonical': 'mystery'}], TABLE)
        self.assertFalse(n.complete)
        self.assertEqual(n.unconverted, [{'name': 'mystery', 'canonical': 'mystery', 'unit': 'g', 'reason': 'no_nutrition'}])

    def test_unresolved_canonical_blocks(self):
        n = compute_recipe_nutrition([{'name': 'něco', 'quantity': 50, 'unit': 'g'}], TABLE)
        self.assertEqual(n.unconverted[0]['reason'], 'no_canonical')
        self.assertFalse(n.complete)

    def test_volume_without_density_blocks(self):
        n = compute_recipe_nutrition([{'name': 'rýže', 'quantity': 1, 'unit': 'hrnek', 'canonical': 'rice-basmati'}], TABLE)
        self.assertEqual(n.unconverted[0]['reason'], 'no_density')

    def test_optional_lines_never_block_but_count_when_they_convert(self):
        n = compute_recipe_nutrition([
            {'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
            {'name': 'petržel', 'quantity': 1, 'unit': 'svazek', 'canonical': 'parsley', 'optional': True},
            {'name': 'olej', 'quantity': 1, 'unit': 'lžička', 'canonical': 'olive-oil', 'optional': True},
        ], TABLE)
        self.assertTrue(n.complete)
        self.assertAlmostEqual(n.calories, 360 + 4.6 * 8.84, places=1)
        self.assertEqual(n.unconverted[0]['name'], 'petržel')

    def test_computed_base_nutrition_shape(self):
        b = computed_base_nutrition(compute_recipe_nutrition(RECIPE, TABLE))
        self.assertEqual(set(b), {'calories', 'protein', 'carbs', 'fat', 'source', 'computed_at'})
        self.assertIsInstance(b['calories'], int)
        self.assertEqual(b['source'], 'computed')
        self.assertEqual(b['protein'], round(139.21, 1))
```

- [ ] **Step 2: Run to verify failure** — ImportError.

- [ ] **Step 3: Implement**

```python
# diet_planner/services/recipe_nutrition.py
"""Recipe nutrition from ingredient lines and the per-100 g table. Pure."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from diet_planner.services.line_mass import line_grams
from diet_planner.services.nutrition_lookups import NutrientRow


@dataclass
class RecipeNutrition:
    calories: float = 0.0
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0
    lines_total: int = 0
    lines_converted: int = 0
    unconverted: List[Dict[str, Any]] = field(default_factory=list)
    complete: bool = True

    @property
    def coverage(self) -> float:
        return self.lines_converted / self.lines_total if self.lines_total else 0.0


def compute_recipe_nutrition(ingredients: Optional[List[Any]],
                             table: Mapping[str, NutrientRow]) -> RecipeNutrition:
    """Whole-recipe totals over every line with a quantity. `complete` is
    False when any NON-optional line could not convert; optional lines that
    fail are listed but never block."""
    out = RecipeNutrition()
    for line in (ingredients or []):
        if not isinstance(line, dict):
            continue
        out.lines_total += 1
        slug = line.get('canonical') or ''
        row = table.get(slug) if slug else None
        optional = bool(line.get('optional'))
        reason: Optional[str] = None
        if not slug:
            reason = 'no_canonical'
        elif row is None:
            reason = 'no_nutrition'
        else:
            lm = line_grams(line, row)
            if lm.grams is None:
                reason = lm.reason or 'unknown_unit'
            else:
                factor = lm.grams / 100.0
                out.calories += row.kcal * factor
                out.protein += row.protein * factor
                out.carbs += row.carbs * factor
                out.fat += row.fat * factor
                out.lines_converted += 1
        if reason:
            out.unconverted.append({'name': line.get('name'), 'canonical': slug or None,
                                    'unit': line.get('unit'), 'reason': reason})
            if not optional:
                out.complete = False
    return out


def computed_base_nutrition(n: RecipeNutrition) -> Dict[str, Any]:
    """The `base_nutrition` dict written to CuratedRecipe (whole recipe for base_servings)."""
    return {
        'calories': int(round(n.calories)),
        'protein': round(n.protein, 1),
        'carbs': round(n.carbs, 1),
        'fat': round(n.fat, 1),
        'source': 'computed',
        'computed_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
```

- [ ] **Step 4: Run** — `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_recipe_nutrition.py -q` → 6 pass. Also `diet_planner/tests/test_recipe_retrieval.py` (scaling reads `base_nutrition` numerically; extra keys `source`/`computed_at` must pass through `scale_recipe_to_meal` untouched — check the totals block only reads the four numbers).

- [ ] **Step 5: Commit** — `git add diet_planner/services/recipe_nutrition.py diet_planner/tests/test_recipe_nutrition.py && git commit -m "feat(nutrition): compute_recipe_nutrition over the per-100g table"`

### Task 4: `import_usda_nutrition` command

**Files:**
- Create: `diet_planner/management/commands/import_usda_nutrition.py`, `diet_planner/tests/fixtures/usda_sr_legacy_slice.json`, `diet_planner/tests/test_import_usda_nutrition.py`

SR Legacy JSON shape (FoodData Central "sr_legacy_food_json"): `{"SRLegacyFoods": [{"fdcId": 171413, "description": "Oil, olive, salad or cooking", "foodNutrients": [{"nutrient": {"id": 1008, "name": "Energy", "unitName": "kcal"}, "amount": 884.0}, ...], "foodPortions": [{"gramWeight": 13.5, "amount": 1.0, "measureUnit": {"name": "tbsp"}, "modifier": ""}, ...]}]}`. Nutrient ids: 1008 kcal, 1003 protein, 1005 carbohydrate by difference, 1004 total lipid.

- [ ] **Step 1: Fixture** — write `usda_sr_legacy_slice.json` with 12 foods in exactly that shape: olive oil (171413; tbsp 13.5 g, cup 216 g), chicken breast raw (171077; "breast, meat only, raw"), chicken breast cooked/roasted (a decoy with "cooked" in the description), rice white raw (169756; cup 185 g), onions raw (170000; "1 medium" 110 g via `modifier: "medium"`, `measureUnit.name: "undetermined"`), garlic raw (169230; clove 3 g via modifier "clove"), whole milk (171265; cup 244 g), all-purpose flour (169761; cup 125 g, tbsp 7.8 g), egg whole raw (171287; "1 large" 50 g), butter (173410; tbsp 14.2 g), honey (169640; tbsp 21 g), and a canned tomatoes decoy (170500; "canned").

- [ ] **Step 2: Write the failing tests**

```python
# diet_planner/tests/test_import_usda_nutrition.py
import csv, json, tempfile
from io import StringIO
from pathlib import Path

import yaml
from django.core.management import call_command
from django.test import SimpleTestCase

from diet_planner.management.commands.import_usda_nutrition import (
    best_match, derive_density, derive_piece_weights, nutrients_of,
)

FIX = Path(__file__).parent / 'fixtures' / 'usda_sr_legacy_slice.json'


def foods():
    return json.loads(FIX.read_text())['SRLegacyFoods']


class MatchingTest(SimpleTestCase):
    def test_prefers_raw_over_cooked_and_canned(self):
        m, conf = best_match('chicken breast', foods(), category='meat')
        self.assertEqual(m['fdcId'], 171077)
        self.assertGreaterEqual(conf, 0.6)

    def test_usda_query_hint_overrides_name(self):
        m, _ = best_match('flour', foods(), category='baking', query='wheat flour all-purpose')
        self.assertEqual(m['fdcId'], 169761)

    def test_canned_category_allows_canned(self):
        m, _ = best_match('tomatoes', foods(), category='canned')
        self.assertEqual(m['fdcId'], 170500)

    def test_no_match_returns_none_with_zero_confidence(self):
        m, conf = best_match('dragon fruit', foods(), category='fruits')
        self.assertIsNone(m)
        self.assertEqual(conf, 0.0)


class DerivationTest(SimpleTestCase):
    def test_nutrients_of(self):
        oil = next(f for f in foods() if f['fdcId'] == 171413)
        self.assertEqual(nutrients_of(oil), {'kcal': 884.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 100.0})

    def test_density_from_tbsp_or_cup(self):
        oil = next(f for f in foods() if f['fdcId'] == 171413)
        self.assertAlmostEqual(derive_density(oil), 13.5 / 15, places=3)
        milk = next(f for f in foods() if f['fdcId'] == 171265)
        self.assertAlmostEqual(derive_density(milk), 244 / 240, places=3)   # USDA cup = 240 ml
        chicken = next(f for f in foods() if f['fdcId'] == 171077)
        self.assertIsNone(derive_density(chicken))

    def test_piece_weights_from_portions(self):
        onion = next(f for f in foods() if f['fdcId'] == 170000)
        self.assertEqual(derive_piece_weights(onion), {'piece_weight_g': 110.0, 'unit_weights': {}})
        garlic = next(f for f in foods() if f['fdcId'] == 169230)
        self.assertEqual(derive_piece_weights(garlic), {'piece_weight_g': None, 'unit_weights': {'stroužek': 3.0}})
        egg = next(f for f in foods() if f['fdcId'] == 171287)
        self.assertEqual(derive_piece_weights(egg)['piece_weight_g'], 50.0)


class CommandTest(SimpleTestCase):
    def _yaml(self, text):
        f = tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False, encoding='utf-8')
        f.write(text); f.close()
        return Path(f.name)

    def test_report_and_write_yaml(self):
        y = self._yaml("""
- name: olive oil
  category: oils
- name: chicken breast
  category: meat
- name: onion
  category: vegetables
- name: bread dumpling
  category: baking
  nutrition: {kcal: 200, protein: 7, carbs: 40, fat: 1, source: "manual:czech table"}
""")
        rep = y.with_suffix('.csv')
        out = StringIO()
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), report=str(rep),
                     write_yaml=True, stdout=out)
        rows = {r['slug']: r for r in csv.DictReader(rep.open(encoding='utf-8'))}
        self.assertEqual(rows['olive-oil']['fdc_id'], '171413')
        self.assertEqual(rows['bread-dumpling']['status'], 'kept_manual')
        data = {e['name']: e for e in yaml.safe_load(y.read_text(encoding='utf-8'))}
        self.assertEqual(data['olive oil']['nutrition']['source'], 'usda:171413')
        self.assertAlmostEqual(data['olive oil']['nutrition']['density'], 0.9, places=2)
        self.assertEqual(data['onion']['nutrition']['piece_weight_g'], 110.0)
        self.assertEqual(data['bread dumpling']['nutrition']['source'], 'manual:czech table')
        self.assertIn('matched=3', out.getvalue())

    def test_low_confidence_rows_are_left_for_review(self):
        y = self._yaml("- name: dragon fruit\n  category: fruits\n")
        out = StringIO()
        call_command('import_usda_nutrition', sr_legacy=str(FIX), yaml=str(y), write_yaml=True, stdout=out)
        data = yaml.safe_load(y.read_text(encoding='utf-8'))
        self.assertEqual(data[0]['nutrition'], {'source': 'needs_review'})
```

- [ ] **Step 3: Implement the command**

```python
# diet_planner/management/commands/import_usda_nutrition.py
"""Build the per-canonical nutrition table from USDA SR Legacy (public domain).

    python manage.py import_usda_nutrition --sr-legacy /path/FoodData_Central_sr_legacy_food_json_2018-04.json \
        --report /path/nutrition_review.csv --write-yaml

Matches each canonical (English `name`, or the entry's `usda_query` hint) to
an SR Legacy food, extracts kcal/protein/carbs/fat per 100 g, density from a
tbsp/cup portion and piece/unit weights from medium/each/clove/slice portions,
and writes a `nutrition:` block into data/canonical_ingredients.yaml for rows
with confidence >= MIN_CONFIDENCE. Rows already tagged `manual:`/`frida:` are
never overwritten; unmatched rows get `{source: needs_review}`.
"""
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

NUTRIENT_IDS = {1008: 'kcal', 1003: 'protein', 1005: 'carbs', 1004: 'fat'}
MIN_CONFIDENCE = 0.6
USDA_ML = {'tbsp': 15.0, 'tsp': 5.0, 'cup': 240.0}
PIECE_MODIFIERS = ('medium', 'each', 'whole', 'large', 'piece')
UNIT_MODIFIERS = {'clove': 'stroužek', 'slice': 'plátek', 'bunch': 'svazek', 'sprig': 'snítka', 'leaf': 'lístek'}
BAD_WORDS = ('cooked', 'roasted', 'fried', 'boiled', 'braised', 'baked', 'canned', 'frozen', 'dried',
             'dehydrated', 'juice', 'babyfood', 'fast foods', 'restaurant')
DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'canonical_ingredients.yaml'


def _tokens(s: str) -> set:
    return {t for t in re.split(r'[^a-z]+', (s or '').lower()) if len(t) > 2}


def best_match(name: str, foods: List[dict], *, category: str = '', query: Optional[str] = None) -> Tuple[Optional[dict], float]:
    want = _tokens(query or name)
    if not want:
        return None, 0.0
    allow_canned = category == 'canned'
    allow_frozen = category == 'frozen'
    best, best_score = None, 0.0
    for f in foods:
        desc = (f.get('description') or '').lower()
        have = _tokens(desc)
        overlap = len(want & have) / len(want)
        if overlap == 0:
            continue
        score = overlap
        if 'raw' in have:
            score += 0.15
        for bad in BAD_WORDS:
            if bad in desc and not ((bad == 'canned' and allow_canned) or (bad == 'frozen' and allow_frozen)):
                score -= 0.5
        score -= 0.01 * max(0, len(have) - len(want))  # prefer short, generic descriptions
        if score > best_score:
            best, best_score = f, score
    return (best, round(min(best_score, 1.0), 2)) if best is not None and best_score > 0 else (None, 0.0)


def nutrients_of(food: dict) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for fn in food.get('foodNutrients') or []:
        nid = (fn.get('nutrient') or {}).get('id')
        if nid in NUTRIENT_IDS:
            out[NUTRIENT_IDS[nid]] = float(fn.get('amount') or 0.0)
    return out


def _portions(food: dict):
    for p in food.get('foodPortions') or []:
        g = p.get('gramWeight')
        amt = p.get('amount') or 1.0
        unit = ((p.get('measureUnit') or {}).get('name') or '').lower()
        mod = (p.get('modifier') or '').lower()
        if g:
            yield float(g) / float(amt), unit, mod


def derive_density(food: dict) -> Optional[float]:
    for g, unit, _ in _portions(food):
        if unit in USDA_ML:
            return round(g / USDA_ML[unit], 3)
    return None


def derive_piece_weights(food: dict) -> Dict[str, Any]:
    piece: Optional[float] = None
    unit_weights: Dict[str, float] = {}
    for g, unit, mod in _portions(food):
        words = set(re.split(r'[^a-z]+', f'{unit} {mod}'))
        for usda_word, cz in UNIT_MODIFIERS.items():
            if usda_word in words and cz not in unit_weights:
                unit_weights[cz] = round(g, 1)
        if piece is None and any(w in words for w in PIECE_MODIFIERS):
            piece = round(g, 1)
    return {'piece_weight_g': piece, 'unit_weights': unit_weights}


class Command(BaseCommand):
    help = 'Build per-canonical nutrition from USDA SR Legacy into canonical_ingredients.yaml'

    def add_arguments(self, parser):
        parser.add_argument('--sr-legacy', dest='sr_legacy', required=True)
        parser.add_argument('--yaml', dest='yaml', default=str(DEFAULT_FILE))
        parser.add_argument('--report', dest='report', default=None)
        parser.add_argument('--write-yaml', dest='write_yaml', action='store_true')

    def handle(self, *args, **opts):
        src = Path(opts['sr_legacy'])
        if not src.exists():
            raise CommandError(f'SR Legacy file not found: {src}')
        foods = json.loads(src.read_text(encoding='utf-8')).get('SRLegacyFoods') or []
        ypath = Path(opts['yaml'])
        entries = yaml.safe_load(ypath.read_text(encoding='utf-8')) or []
        rows, matched, kept, review = [], 0, 0, 0
        for e in entries:
            name = e.get('name') or ''
            slug = e.get('slug') or slugify(name)[:255]
            existing = e.get('nutrition') or {}
            src_tag = str(existing.get('source') or '')
            if src_tag.startswith(('manual:', 'frida:')):
                kept += 1
                rows.append({'slug': slug, 'name_cs': e.get('name_cs', ''), 'status': 'kept_manual',
                             'usda_description': '', 'fdc_id': '', 'confidence': '',
                             **{k: existing.get(k, '') for k in ('kcal', 'protein', 'carbs', 'fat', 'density', 'piece_weight_g')}})
                continue
            food, conf = best_match(name, foods, category=e.get('category', ''), query=e.get('usda_query'))
            if food is None or conf < MIN_CONFIDENCE:
                review += 1
                rows.append({'slug': slug, 'name_cs': e.get('name_cs', ''), 'status': 'needs_review',
                             'usda_description': (food or {}).get('description', ''), 'fdc_id': (food or {}).get('fdcId', ''),
                             'confidence': conf, 'kcal': '', 'protein': '', 'carbs': '', 'fat': '', 'density': '', 'piece_weight_g': ''})
                if opts['write_yaml']:
                    e['nutrition'] = {**{k: v for k, v in existing.items() if k in ('piece_weight_g', 'unit_weights')}, 'source': 'needs_review'}
                continue
            n = nutrients_of(food)
            if set(n) != {'kcal', 'protein', 'carbs', 'fat'}:
                review += 1
                if opts['write_yaml']:
                    e['nutrition'] = {'source': 'needs_review'}
                continue
            matched += 1
            pw = derive_piece_weights(food)
            block = {'kcal': n['kcal'], 'protein': n['protein'], 'carbs': n['carbs'], 'fat': n['fat']}
            density = derive_density(food)
            if density:
                block['density'] = density
            piece = existing.get('piece_weight_g') or pw['piece_weight_g']   # a hand-set piece weight wins
            if piece:
                block['piece_weight_g'] = piece
            uw = {**pw['unit_weights'], **(existing.get('unit_weights') or {})}
            if uw:
                block['unit_weights'] = uw
            block['source'] = f"usda:{food['fdcId']}"
            if opts['write_yaml']:
                e['nutrition'] = block
            rows.append({'slug': slug, 'name_cs': e.get('name_cs', ''), 'status': 'matched',
                         'usda_description': food.get('description', ''), 'fdc_id': food['fdcId'],
                         'confidence': conf, 'kcal': n['kcal'], 'protein': n['protein'], 'carbs': n['carbs'],
                         'fat': n['fat'], 'density': density or '', 'piece_weight_g': block.get('piece_weight_g', '')})
        if opts['report']:
            with open(opts['report'], 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ['slug'])
                w.writeheader(); w.writerows(rows)
        if opts['write_yaml']:
            ypath.write_text(yaml.safe_dump(entries, allow_unicode=True, sort_keys=False, width=100), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(
            f'matched={matched} kept_manual={kept} needs_review={review} total={len(entries)}'))
```

NOTE on `--write-yaml`: `yaml.safe_dump` drops the file's comments. Keep the header comment by reading the leading comment block (lines starting with `#`) before parsing and re-prepending it on write. Add that to `handle` (10 lines) and cover it with one assertion in `test_report_and_write_yaml` (header preserved).

- [ ] **Step 4: Run** — `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_import_usda_nutrition.py -q` → 9 pass.

- [ ] **Step 5: Commit** — `git add diet_planner/management/commands/import_usda_nutrition.py diet_planner/tests/fixtures/usda_sr_legacy_slice.json diet_planner/tests/test_import_usda_nutrition.py && git commit -m "feat(nutrition): import_usda_nutrition builds the canonical table from SR Legacy"`

### Task 5: Build the real table (data task)

**Files:**
- Modify: `diet_planner/data/canonical_ingredients.yaml` (nutrition blocks for all 291 entries, `usda_query` hints where needed)
- Scratchpad only (never committed): the SR Legacy download, the review CSV

- [ ] **Step 1: Download** — `cd $SCRATCHPAD && curl -L -o sr_legacy.zip https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_json_2018-04.zip && unzip -o sr_legacy.zip` (≈ 30 MB zip). If the URL has moved, find the current "SR Legacy" JSON link on https://fdc.nal.usda.gov/download-datasets.html and report it.

- [ ] **Step 2: First pass** — `GEMINI_API_KEY=dummy python3 manage.py import_usda_nutrition --sr-legacy $SCRATCHPAD/FoodData_Central_sr_legacy_food_json_2018-04.json --report $SCRATCHPAD/nutrition_review.csv` (no `--write-yaml`). Read the report: for every `needs_review` row and every `matched` row whose description is obviously wrong for the Czech name (e.g. "hladká mouka" matched to "flour, corn"), add a `usda_query:` hint to the YAML entry (English, specific: `wheat flour white all-purpose`, `pork loin raw`, `cabbage green raw`, `sour cream cultured`, `quark` → will not exist → manual). Re-run until the remaining `needs_review` rows are genuinely absent from USDA (Czech-specific: tvaroh, houskový knedlík, bramborák mix, pribináček, smetana ke šlehání 33 %, kysané zelí…).

- [ ] **Step 3: Hand entries** — for each remaining row add `nutrition: {kcal, protein, carbs, fat, [density], [piece_weight_g], source: "frida:<id>" | "manual:<reference>"}` from Frida (https://frida.fooddata.dk, open data) or the product label of a common Czech brand (state which in `source`). Density is needed only when the corpus uses that ingredient in a volume unit; piece weights only for count units — the backfill dry run in Task 8 is the checker, so do not over-fill.

- [ ] **Step 4: Write and seed** — run with `--write-yaml`, then `GEMINI_API_KEY=dummy python3 manage.py seed_canonical_ingredients` locally; `python3 -c` check: count of canonicals with `has_nutrition` == 291 minus the documented exceptions (list them in the commit message). Publish the review CSV as a private artifact for the owner (title "Nutrition table review") and pause for their review before committing the YAML.

- [ ] **Step 5: Commit** — `git add diet_planner/data/canonical_ingredients.yaml && git commit -m "data(nutrition): per-100g nutrients, density and piece weights for the canonical dictionary (USDA SR Legacy + Frida/manual)"`

---

## Part B — curation, promotion, backfill

### Task 6: Curation computes nutrition; blockers; prompt no longer asks for it

**Files:**
- Modify: `diet_planner/services/recipe_curation.py` (imports, `build_recipe_fields`, delete `correct_nutrition_basis`, `curate_from_source`), `diet_planner/llm_service.py` (curation prompt ~lines 813-819), `diet_planner/services/nutrition_plausibility.py` (drop Atwater), `diet_planner/management/commands/promote_curated_recipes.py`, `diet_planner/management/commands/remap_curated_recipes.py`
- Delete: `diet_planner/services/nutrition_density.py`, `diet_planner/services/nutrition_basis_repair.py`, `diet_planner/management/commands/repair_nutrition_basis.py`, tests `test_nutrition_density.py`, `test_nutrition_basis_repair.py`, `test_repair_nutrition_basis.py`, `test_curation_nutrition_basis.py`
- Create: `diet_planner/tests/test_curation_nutrition_gate.py`

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_curation_nutrition_gate.py
"""Curation computes base_nutrition from the table; anything it cannot compute
blocks promotion instead of shipping a guess."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services import recipe_curation
from diet_planner.services.recipe_curation import apply_nutrition
from diet_planner.tests.factories import make_canonical


def _canon(name, slug, **nut):
    return make_canonical(name, slug=slug, kcal_per_100g=nut.get('kcal'), protein_per_100g=nut.get('protein', 0),
                          carbs_per_100g=nut.get('carbs', 0), fat_per_100g=nut.get('fat', 0),
                          density_g_per_ml=nut.get('density'), avg_piece_weight_g=nut.get('piece'),
                          category=nut.get('category', 'other'))


def _curated(**overrides):
    payload = {
        "name_cs": "Kuře s rýží", "name_en": "Chicken with rice", "description": "Jednoduché.",
        "meal_types": ["lunch"], "cuisine": "czech", "difficulty": "easy", "dietary_tags": [],
        "ingredients": [
            {"name": "kuřecí prsa", "quantity": 400, "unit": "g"},
            {"name": "rýže", "quantity": 200, "unit": "g"},
        ],
        "instructions": [{"text": "Uvař rýži, opeč kuře."}],
        "base_servings": 2,
        "base_nutrition": {"calories": 1, "protein": 1, "carbs": 1, "fat": 1},   # Gemini's guess is ignored
        "prep_time": 10, "cook_time": 20,
    }
    payload.update(overrides)
    return payload


class ApplyNutritionTest(TestCase):
    def setUp(self):
        _canon('Chicken breast', 'chicken-breast', kcal=165, protein=31, fat=3.6, category='meat')
        _canon('Rice basmati', 'rice-basmati', kcal=360, protein=7, carbs=79, fat=0.6, category='grains')
        recipe_curation.clear_resolver_cache()

    def test_complete_recipe_gets_computed_base_nutrition(self):
        fields = recipe_curation.build_recipe_fields(_curated(), source_url='u', source_name='s')
        self.assertEqual(fields['base_nutrition'], {})
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual(blockers, [])
        self.assertEqual(fields['base_nutrition']['calories'], 660 + 720)
        self.assertEqual(fields['base_nutrition']['source'], 'computed')
        self.assertEqual(fields['nutrition_blockers'], [])

    def test_unresolved_or_untabled_line_blocks(self):
        fields = recipe_curation.build_recipe_fields(
            _curated(ingredients=[{"name": "kuřecí prsa", "quantity": 400, "unit": "g"},
                                  {"name": "dračí ovoce", "quantity": 100, "unit": "g"}]),
            source_url='u', source_name='s')
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual(blockers[0]['reason'], 'no_canonical')
        self.assertEqual(fields['base_nutrition'], {})
        self.assertEqual(fields['nutrition_blockers'], blockers)

    def test_implausible_portion_blocks_with_reason(self):
        fields = recipe_curation.build_recipe_fields(
            _curated(ingredients=[{"name": "kuřecí prsa", "quantity": 5000, "unit": "g"}], base_servings=1),
            source_url='u', source_name='s')
        blockers = apply_nutrition(fields, dish_role='main')
        self.assertEqual(blockers[0]['reason'], 'implausible')
        self.assertGreater(blockers[0]['per_portion_kcal'], 1500)
        self.assertEqual(fields['base_nutrition']['source'], 'computed')   # kept, but blocked


class CurateFromSourceTest(TestCase):
    def setUp(self):
        _canon('Chicken breast', 'chicken-breast', kcal=165, protein=31, fat=3.6, category='meat')
        _canon('Rice basmati', 'rice-basmati', kcal=360, protein=7, carbs=79, fat=0.6, category='grains')
        recipe_curation.clear_resolver_cache()

    def _curate(self, curated):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = curated
            gem.return_value.classify_dishes.side_effect = Exception('no classifier in tests')
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/kure", "source_name": "Example"}, run_judge=False)

    def test_saved_recipe_carries_computed_nutrition(self):
        r = self._curate(_curated())
        self.assertTrue(r.ok, r.error)
        rec = CuratedRecipe.objects.get(source_url="https://example.test/kure")
        self.assertEqual(rec.base_nutrition['source'], 'computed')
        self.assertEqual(rec.nutrition_blockers, [])

    def test_blocked_recipe_is_saved_as_draft_with_blockers(self):
        r = self._curate(_curated(ingredients=[{"name": "dračí ovoce", "quantity": 100, "unit": "g"}]))
        self.assertTrue(r.ok, r.error)
        rec = CuratedRecipe.objects.get(source_url="https://example.test/kure")
        self.assertEqual(rec.status, CuratedRecipe.Status.DRAFT)
        self.assertEqual(rec.nutrition_blockers[0]['reason'], 'no_canonical')
        self.assertEqual(rec.base_nutrition, {})


class PromoteTest(TestCase):
    def test_promote_skips_nutrition_blocked_and_uncomputed(self):
        base = dict(ingredients=[{'name': 'x', 'quantity': 1, 'unit': 'g', 'canonical': 'chicken-breast'}], base_servings=1)
        ok = CuratedRecipe.objects.create(name_cs='ok', base_nutrition={'calories': 1, 'protein': 0, 'carbs': 0, 'fat': 0, 'source': 'computed'}, **base)
        blocked = CuratedRecipe.objects.create(name_cs='blocked', nutrition_blockers=[{'reason': 'no_density'}], **base)
        legacy = CuratedRecipe.objects.create(name_cs='legacy', base_nutrition={'calories': 500}, **base)
        out = StringIO()
        call_command('promote_curated_recipes', stdout=out)
        self.assertEqual(CuratedRecipe.objects.get(pk=ok.pk).status, CuratedRecipe.Status.PUBLISHED)
        self.assertEqual(CuratedRecipe.objects.get(pk=blocked.pk).status, CuratedRecipe.Status.DRAFT)
        self.assertEqual(CuratedRecipe.objects.get(pk=legacy.pk).status, CuratedRecipe.Status.DRAFT)
        self.assertIn('skipped_nutrition=2', out.getvalue())


class PromptTest(TestCase):
    def test_curation_prompt_no_longer_asks_for_base_nutrition(self):
        from diet_planner.llm_service import GeminiService
        with patch('diet_planner.llm_service.genai.GenerativeModel') as gm:
            gm.return_value.generate_content.return_value.text = '{"name_cs": "x"}'
            GeminiService().curate_recipe_to_czech(source_title='t', source_material='m', source_url='u', source_lang_hint='')
            prompt = gm.return_value.generate_content.call_args.args[0]
        self.assertNotIn('base_nutrition', prompt)
        self.assertIn('base_servings', prompt)
```

Check `diet_planner/tests/factories.py::make_canonical` accepts arbitrary kwargs passed to `get_or_create(defaults=...)`; if it only accepts `name`, extend it to forward `**kwargs` into `defaults` (tiny change, keep existing callers working). Check whether `recipe_curation` exposes the resolver cache clear (`canonical_lookup.clear_cache`); import it as `clear_resolver_cache` in the module (one line) so tests that create canonicals after import can resolve them.

- [ ] **Step 2: Run to verify failure** — ImportError `apply_nutrition`.

- [ ] **Step 3: `recipe_curation.py`**

Imports: remove `plan_basis_repair`, `category_table`, `piece_weight_table`; add
```python
from diet_planner.services.canonical_lookup import clear_cache as clear_resolver_cache  # noqa: F401 (tests)
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.nutrition_plausibility import check_nutrition_plausibility
from diet_planner.services.recipe_nutrition import compute_recipe_nutrition, computed_base_nutrition
```
`build_recipe_fields`: delete the `nutrition = curated.get("base_nutrition")…` lines; set `"base_nutrition": {}` and add `"nutrition_blockers": []`.

Delete `correct_nutrition_basis`. Add:

```python
def apply_nutrition(fields: Dict[str, Any], *, dish_role: Optional[str] = None,
                    table: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Compute `base_nutrition` from the ingredient lines. Writes the computed
    dict when every non-optional line converts, else leaves it empty; always
    writes `nutrition_blockers` (empty = publishable). An implausible computed
    portion is a blocker too — it means a wrong quantity, density or piece
    weight, which the corpus tools fix. Returns the blockers."""
    result = compute_recipe_nutrition(fields.get("ingredients"), table if table is not None else nutrition_table())
    blockers: List[Dict[str, Any]] = [u for u in result.unconverted
                                      if not _is_optional(fields.get("ingredients"), u["name"])]
    if result.complete:
        fields["base_nutrition"] = computed_base_nutrition(result)
        check = check_nutrition_plausibility(fields["base_nutrition"], fields.get("base_servings"), dish_role)
        if not check.ok:
            blockers.append({"reason": "implausible", "per_portion_kcal": check.per_portion_kcal,
                             "detail": "; ".join(check.reasons)})
    else:
        fields["base_nutrition"] = {}
    fields["nutrition_blockers"] = blockers
    return blockers


def _is_optional(ingredients, name) -> bool:
    return any(isinstance(i, dict) and i.get("name") == name and i.get("optional") for i in (ingredients or []))
```

In `curate_from_source`: delete the `corrected = correct_nutrition_basis(fields)` block. Call `apply_nutrition(fields)` right after `build_recipe_fields` (before `recipe = CuratedRecipe(**fields)`; the role is unknown yet, so the default floor applies), and re-run only the plausibility part after dish classification when a role was assigned:

```python
    apply_nutrition(fields)                      # role unknown yet → default floor
    ...
    recipe = CuratedRecipe(**fields)
    ...  # classification block
    if recipe.dish_role and recipe.base_nutrition.get('source') == 'computed':
        check = check_nutrition_plausibility(recipe.base_nutrition, recipe.base_servings, recipe.dish_role)
        recipe.nutrition_blockers = [b for b in recipe.nutrition_blockers if b.get('reason') != 'implausible']
        if not check.ok:
            recipe.nutrition_blockers.append({"reason": "implausible", "per_portion_kcal": check.per_portion_kcal,
                                              "detail": "; ".join(check.reasons)})
```
The `enforce_plausibility` (mass gate) and availability gate stay as they are. Log at info when blockers are non-empty.

- [ ] **Step 4: Prompt, plausibility, promote, remap**

`llm_service.py` curation prompt: delete the whole `- "base_nutrition": …` bullet with its worked example and self-check (keep `base_servings`). Add one line after `base_servings`: `- (Do NOT include nutrition; it is computed from the ingredients.)`. The response parser must tolerate the missing key (it does — `build_recipe_fields` no longer reads it).

`nutrition_plausibility.py`: remove the Atwater drift block from `check_nutrition_plausibility` (and `ATWATER_TOLERANCE`; keep `atwater_kcal` only if `audit_nutrition_plausibility` still prints it — it does, so keep the function and its field, just stop failing on it). Update the docstring: floors/ceiling now catch wrong quantities, not wrong basis; keep `suspected_basis` for the audit's sake.

`promote_curated_recipes.py`: add
```python
            if (r.nutrition_blockers or []) or (r.base_nutrition or {}).get('source') != 'computed':
                skipped_nutrition += 1
                continue
```
after the mapping check; init and print `skipped_nutrition`.

`remap_curated_recipes.py`: after remapping (whether or not the mapping changed), recompute nutrition for every row: `blockers = apply_nutrition(fields := {'ingredients': remapped, 'base_servings': r.base_servings}, dish_role=r.dish_role or None, table=table)` with `table = nutrition_table()` loaded once; write `r.base_nutrition = fields['base_nutrition']`, `r.nutrition_blockers = blockers`, save with `update_fields=['ingredients', 'base_nutrition', 'nutrition_blockers', 'updated_at']` when anything changed; add `nutrition_blocked=N` to the summary line. In `--dry-run` only count.

- [ ] **Step 5: Delete the old machinery** — `git rm diet_planner/services/nutrition_density.py diet_planner/services/nutrition_basis_repair.py diet_planner/management/commands/repair_nutrition_basis.py diet_planner/tests/test_nutrition_density.py diet_planner/tests/test_nutrition_basis_repair.py diet_planner/tests/test_repair_nutrition_basis.py diet_planner/tests/test_curation_nutrition_basis.py`. `nutrition_lookups.category_table` and `piece_weight_table` lose their last callers → delete them too (grep first). `grep -rn "nutrition_density\|nutrition_basis_repair\|correct_nutrition_basis\|plan_basis_repair\|category_table\|piece_weight_table" --include=*.py diet_planner social` → empty.

- [ ] **Step 6: Run** — `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_curation_nutrition_gate.py diet_planner/tests/test_nutrition_plausibility.py diet_planner/tests/test_curation_plausibility_gate.py diet_planner/tests/test_dish_roles.py diet_planner/tests/test_audit_nutrition_plausibility.py -q` (adapt any Atwater-specific plausibility test to the new rule: those cases now pass instead of failing — delete them, they tested deleted behaviour). Then the full gate.

- [ ] **Step 7: Commit** — `git add -A diet_planner && git commit -m "feat(nutrition): curation computes base_nutrition, nutrition_blockers gate promotion; retire basis heuristics"`

### Task 7: `recompute_nutrition` backfill + cache refresh includes sides

**Files:**
- Create: `diet_planner/management/commands/recompute_nutrition.py`, `diet_planner/tests/test_recompute_nutrition.py`
- Modify: `diet_planner/management/commands/refresh_stale_recipe_cache.py` (`rebuild_meal` → `render_curated_meal`), its test

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_recompute_nutrition.py
import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.tests.factories import make_canonical


class RecomputeNutritionTest(TestCase):
    def setUp(self):
        make_canonical('Chicken breast', slug='chicken-breast', kcal_per_100g=165, protein_per_100g=31,
                       carbs_per_100g=0, fat_per_100g=3.6)
        make_canonical('Rice basmati', slug='rice-basmati', kcal_per_100g=360, protein_per_100g=7,
                       carbs_per_100g=79, fat_per_100g=0.6)
        make_canonical('Mystery', slug='mystery')   # no nutrition
        self.ok = CuratedRecipe.objects.create(
            name_cs='Kuře s rýží', status='published', base_servings=2, dish_role='main',
            base_nutrition={'calories': 900, 'protein': 50, 'carbs': 80, 'fat': 20},
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 400, 'unit': 'g', 'canonical': 'chicken-breast'},
                         {'name': 'rýže', 'quantity': 200, 'unit': 'g', 'canonical': 'rice-basmati'}])
        self.bad = CuratedRecipe.objects.create(
            name_cs='Záhada', status='published', base_servings=1, dish_role='main',
            base_nutrition={'calories': 500},
            ingredients=[{'name': 'záhada', 'quantity': 100, 'unit': 'g', 'canonical': 'mystery'},
                         {'name': 'olej', 'quantity': 2, 'unit': 'lžíce', 'canonical': 'chicken-breast'}])

    def test_dry_run_reports_deltas_and_worklist_without_writing(self):
        out = StringIO()
        call_command('recompute_nutrition', stdout=out)
        text = out.getvalue()
        self.assertIn('Kuře s rýží', text)
        self.assertIn('900 -> 1380', text)
        self.assertIn('mystery', text)          # worklist by (canonical, unit, reason)
        self.assertIn('no_nutrition', text)
        self.assertIn('no_density', text)
        self.assertIn('complete=1 incomplete=1', text)
        self.ok.refresh_from_db()
        self.assertEqual(self.ok.base_nutrition['calories'], 900)

    def test_apply_refuses_while_a_published_recipe_is_incomplete(self):
        with self.assertRaises(CommandError):
            call_command('recompute_nutrition', apply=True, stdout=StringIO())
        self.ok.refresh_from_db()
        self.assertEqual(self.ok.base_nutrition['calories'], 900)

    def test_apply_with_skip_incomplete_writes_complete_rows_and_reversal_map(self):
        out = StringIO()
        call_command('recompute_nutrition', apply=True, skip_incomplete=True, stdout=out)
        self.ok.refresh_from_db(); self.bad.refresh_from_db()
        self.assertEqual(self.ok.base_nutrition['calories'], 1380)
        self.assertEqual(self.ok.base_nutrition['source'], 'computed')
        self.assertEqual(self.ok.nutrition_blockers, [])
        self.assertEqual(self.bad.base_nutrition['calories'], 500)
        self.assertEqual({b['reason'] for b in self.bad.nutrition_blockers}, {'no_nutrition', 'no_density'})
        text = out.getvalue()
        self.assertIn('REVERSAL', text)
        rev = json.loads(text.split('REVERSAL')[1].strip().splitlines()[0])
        self.assertEqual(rev[str(self.ok.pk)]['calories'], 900)

    def test_report_csv(self):
        import csv, tempfile
        path = tempfile.mktemp(suffix='.csv')
        call_command('recompute_nutrition', report=path, stdout=StringIO())
        rows = list(csv.DictReader(open(path, encoding='utf-8')))
        self.assertEqual({r['slug'] for r in rows}, {self.ok.slug, self.bad.slug})
```

- [ ] **Step 2: Implement**

```python
# diet_planner/management/commands/recompute_nutrition.py
"""Recompute CuratedRecipe.base_nutrition from the per-100 g table.

Dry run (default) prints old -> new kcal per recipe, the worklist of lines
that cannot convert grouped by (canonical, unit, reason), and a summary.
`--apply` writes computed rows and prints a REVERSAL map; it refuses while
any PUBLISHED recipe is incomplete unless `--skip-incomplete`.
After applying run `refresh_stale_recipe_cache --apply`.
"""
import csv
import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.recipe_curation import apply_nutrition


class Command(BaseCommand):
    help = 'Recompute base_nutrition from ingredient lines and the canonical nutrition table.'

    def add_arguments(self, parser):
        parser.add_argument('--status', choices=['published', 'draft', 'all'], default='published')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--skip-incomplete', dest='skip_incomplete', action='store_true')
        parser.add_argument('--report', default=None)

    def handle(self, *args, **opts):
        qs = CuratedRecipe.objects.all().order_by('id')
        if opts['status'] != 'all':
            qs = qs.filter(status=opts['status'])
        table = nutrition_table()
        worklist = Counter()
        rows, incomplete_published, plans = [], [], {}
        for r in qs:
            fields = {'ingredients': r.ingredients or [], 'base_servings': r.base_servings}
            blockers = apply_nutrition(fields, dish_role=r.dish_role or None, table=table)
            old = (r.base_nutrition or {}).get('calories')
            new = (fields['base_nutrition'] or {}).get('calories')
            complete = bool(fields['base_nutrition'])
            for b in blockers:
                worklist[(b.get('canonical') or b.get('name'), b.get('unit'), b['reason'])] += 1
            if not complete and r.status == CuratedRecipe.Status.PUBLISHED:
                incomplete_published.append(r)
            delta = (f'{(new - old) / old:+.0%}' if old and new else '')
            self.stdout.write(f'[{r.pk}] {r.name_cs[:34]:34} {old} -> {new} {delta} '
                              f'{"" if complete else "INCOMPLETE " + ", ".join(b["reason"] for b in blockers)}')
            rows.append({'id': r.pk, 'slug': r.slug, 'status': r.status, 'old_kcal': old, 'new_kcal': new,
                         'delta': delta, 'complete': complete, 'blockers': json.dumps(blockers, ensure_ascii=False)})
            plans[r.pk] = (r, fields['base_nutrition'], blockers)
        self.stdout.write('')
        self.stdout.write('Worklist (canonical, unit, reason): count')
        for (c, u, reason), n in worklist.most_common():
            self.stdout.write(f'  {c} {u} {reason}: {n}')
        self.stdout.write(self.style.SUCCESS(
            f'recipes={len(rows)} complete={sum(1 for x in rows if x["complete"])} '
            f'incomplete={sum(1 for x in rows if not x["complete"])}'))
        if opts['report']:
            with open(opts['report'], 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ['id'])
                w.writeheader(); w.writerows(rows)
        if not opts['apply']:
            return
        if incomplete_published and not opts['skip_incomplete']:
            raise CommandError(f'{len(incomplete_published)} published recipe(s) are incomplete; '
                               f'fix the table (see worklist) or pass --skip-incomplete')
        reversal = {}
        with transaction.atomic():
            for r, base, blockers in plans.values():
                if not base:
                    if r.nutrition_blockers != blockers:
                        r.nutrition_blockers = blockers
                        r.save(update_fields=['nutrition_blockers', 'updated_at'])
                    continue
                reversal[str(r.pk)] = r.base_nutrition or {}
                r.base_nutrition = base
                r.nutrition_blockers = blockers
                r.save(update_fields=['base_nutrition', 'nutrition_blockers', 'updated_at'])
        self.stdout.write('REVERSAL')
        self.stdout.write(json.dumps(reversal, ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS(f'applied={len(reversal)}'))
```

`refresh_stale_recipe_cache.rebuild_meal`: replace the body with `meal, _ = render_curated_meal(curated, target_kcal=_SLOT_DEFAULT_KCAL.get(slot_key_for(meal_type)), required_tags=required_tags_for_goal(row.dietary_goal))` — it needs the goal for the side rule; change the signature to `rebuild_meal(curated, row, meal_type)` and pass `row` from `handle`. Import `render_curated_meal`, `required_tags_for_goal`. Update `test_refresh_stale_recipe_cache.py` where it calls `rebuild_meal` and add one assertion that a recipe with `side_options=['chleb']` rebuilds WITH a `side` and its calories include the side.

- [ ] **Step 3: Run** — `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_recompute_nutrition.py diet_planner/tests/test_refresh_stale_recipe_cache.py -q` → pass.

- [ ] **Step 4: Commit** — `git add diet_planner/management/commands/recompute_nutrition.py diet_planner/management/commands/refresh_stale_recipe_cache.py diet_planner/tests && git commit -m "feat(nutrition): recompute_nutrition backfill with worklist and reversal; cache refresh renders sides"`

---

## Part C — serving path, display, rollout

### Task 8: Explicit basis on every meal; computed sides; gap-meal stamping

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py` (`scale_recipe_to_meal` nutritional_info), `diet_planner/services/priloha.py` (`Side` loses kcal/macros; `side_nutrition` computes), `diet_planner/services/meal_pool.py` (stamp generated meals), `diet_planner/views.py` (`_recipe_cache_fields` passes the new keys through — it copies the dict verbatim, verify), `social/facts.py` (`_per_portion_kcal` reads basis)
- Tests: `diet_planner/tests/test_gap_meal_nutrition.py` (new), edit `test_priloha.py`, `test_recipe_retrieval.py` side tests, `social/tests/test_facts.py`

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_gap_meal_nutrition.py
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal
from diet_planner.services import recipe_curation
from diet_planner.services.meal_pool import build_meal_pool, stamp_generated_nutrition
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.tests.factories import make_canonical


class StampTest(TestCase):
    def setUp(self):
        make_canonical('Chicken breast', slug='chicken-breast', name_cs='kuřecí prsa', kcal_per_100g=165,
                       protein_per_100g=31, carbs_per_100g=0, fat_per_100g=3.6)
        recipe_curation.clear_resolver_cache()

    def test_resolvable_meal_is_computed(self):
        meal = {'name': 'Kuře', 'servings': 1,
                'ingredients': [{'name': 'kuřecí prsa', 'quantity': 200, 'unit': 'g'}],
                'nutritional_info': {'calories': 999, 'protein': '1g'}}
        stamp_generated_nutrition(meal, nutrition_table())
        self.assertEqual(meal['nutritional_info'], {'calories': 330, 'protein': '62g', 'carbs': '0g', 'fat': '7g',
                                                    'basis': 'total', 'servings': 1, 'nutrition_source': 'computed'})
        self.assertEqual(meal['ingredients'][0]['canonical'], 'chicken-breast')

    def test_unresolvable_meal_keeps_gemini_numbers_as_estimate(self):
        meal = {'name': 'X', 'servings': 1,
                'ingredients': [{'name': 'dračí ovoce', 'quantity': 100, 'unit': 'g'}],
                'nutritional_info': {'calories': 120, 'protein': '2g'}}
        stamp_generated_nutrition(meal, nutrition_table())
        self.assertEqual(meal['nutritional_info']['calories'], 120)
        self.assertEqual(meal['nutritional_info']['nutrition_source'], 'estimated')
        self.assertEqual(meal['nutritional_info']['basis'], 'total')


class PoolIntegrationTest(TestCase):
    def test_gap_meal_from_pool_is_stamped(self):
        user = User.objects.create_user('p', password='x')
        make_canonical('Chicken breast', slug='chicken-breast', name_cs='kuřecí prsa', kcal_per_100g=165,
                       protein_per_100g=31, carbs_per_100g=0, fat_per_100g=3.6)
        recipe_curation.clear_resolver_cache()
        goal = DietaryGoal.objects.create(user=user, prompt='x', country='CZ', dinners=1)
        llm = MagicMock()
        llm.generate_slot_meal.return_value = {
            'meal': {'name': 'Kuře', 'ingredients': [{'name': 'kuřecí prsa', 'quantity': 200, 'unit': 'g'}],
                     'nutritional_info': {'calories': 999}},
            'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2, 'cost_usd': 0, 'model': 'f'}
        with patch('diet_planner.services.meal_pool.extract_prompt_facets', return_value=PromptFacets()):
            result = build_meal_pool(goal, llm=llm)
        ni = result.meals[0]['nutritional_info']
        self.assertEqual((ni['calories'], ni['nutrition_source']), (330, 'computed'))
```

Edit `test_priloha.py`: `test_every_row_is_complete` no longer checks `side.calories…`; add `test_side_nutrition_computes_from_table` that seeds `bread-loaf` with kcal 250/protein 9/carbs 47/fat 3 and asserts `side_nutrition(SIDES['chleb'], portions=2, table=nutrition_table())` == `{'calories': 400, 'protein': 14.4, 'carbs': 75.2, 'fat': 4.8}` (80 g × 2). Edit `test_recipe_retrieval.py` side tests (`test_side_counted_in_nutrition`, `test_portions_for_target_counts_the_side`) to seed `bread-loaf` nutrition so the numbers (200 kcal per 80 g portion → kcal 250/100 g) hold. Edit `social/tests/test_facts.py:57-58` to pass a dict with `basis: 'total'` instead of the `curated` flag.

- [ ] **Step 2: Implement**

`recipe_retrieval.scale_recipe_to_meal`: the `nutritional_info` dict gains `'basis': 'total', 'servings': served, 'nutrition_source': (base.get('source') or 'estimated')`. `side_nutrition` is now called with `table=nutrition_table()` (load once per call via a module-level helper with the same lru pattern as `published_pool` — or pass it through `render_curated_meal`, which is the single entry point; add a `table` kwarg defaulting to `nutrition_table()`).

`priloha.py`: `Side` keeps `key, name_cs, with_cs, canonical, grams, display, breaks_tags`; delete the four nutrient fields from the dataclass and the table rows. `side_nutrition(side, *, portions, table)` → `row = table.get(side.canonical)`; if None return zeros and log a warning (the dictionary test guarantees the five canonicals exist and Task 5 gives them nutrition); else `factor = side.grams * portions / 100` → `{'calories': row.kcal*factor, 'protein': …}`. `portions_for_target(recipe, target, side, table)` reads `side_nutrition(side, portions=1, table)['calories']` instead of `side.calories`.

`meal_pool.py`: add

```python
def stamp_generated_nutrition(meal: Dict[str, Any], table) -> None:
    """Resolve canonicals for a Gemini meal and compute its nutrition when
    every line converts; otherwise keep Gemini's numbers, labelled estimated."""
    from diet_planner.services.recipe_curation import map_ingredients
    from diet_planner.services.recipe_nutrition import compute_recipe_nutrition
    meal['ingredients'] = map_ingredients(meal.get('ingredients') or [])
    servings = int(meal.get('servings') or 1)
    n = compute_recipe_nutrition(meal['ingredients'], table)
    if n.complete and n.lines_converted:
        meal['nutritional_info'] = {
            'calories': int(round(n.calories)), 'protein': f'{int(round(n.protein))}g',
            'carbs': f'{int(round(n.carbs))}g', 'fat': f'{int(round(n.fat))}g',
            'basis': 'total', 'servings': servings, 'nutrition_source': 'computed'}
    else:
        info = dict(meal.get('nutritional_info') or {})
        info.update({'basis': 'total', 'servings': servings, 'nutrition_source': 'estimated'})
        meal['nutritional_info'] = info
```
and call it right after the final `_normalise_generated(meal)` in the gap loop (load `table = nutrition_table()` once before the loop, next to `exclusions`).

`social/facts._per_portion_kcal(nutritional_info, servings)`: drop the `curated` parameter; return None unless `nutritional_info.get('basis') == 'total'` or (legacy rows) the caller passes `curated=True` — simplest: keep the signature `(nutritional_info, servings, curated)` and treat `basis == 'total'` as an additional "known basis" condition (`if not curated and info.get('basis') != 'total': return None`). Update both call sites to pass the dict.

- [ ] **Step 3: Run** — `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_gap_meal_nutrition.py diet_planner/tests/test_priloha.py diet_planner/tests/test_recipe_retrieval.py diet_planner/tests/test_meal_pool.py social/tests/test_facts.py diet_planner/tests/test_recipe_replace_pool.py diet_planner/tests/test_recipe_refine.py -q` → pass (fixtures in ranking/replace tests use `base_nutrition={'calories': N}` without `source` → `nutrition_source: 'estimated'` on those meals is fine).

- [ ] **Step 4: Commit** — `git add -A diet_planner social && git commit -m "feat(nutrition): explicit basis on meals; sides and gap-fill meals compute from the table"`

### Task 9: Display — basis-aware frontend, per-portion JSON-LD and SSR, "odhad" badge

**Files:**
- Modify: `frontend/src/lib/nutrition.ts` (`nutritionBasisFor`, `nutritionSourceFor`), `frontend/src/lib/nutrition.test.ts`, `frontend/src/pages/RecipePage.tsx` (JSON-LD + badge), `frontend/src/pages/PublicRecipePage.tsx` (badge), `llm_diet_planner_project/views.py` (SSR per-portion), `diet_planner/tests/test_public_recipe_ssr.py`

- [ ] **Step 1: Failing tests**

Append to `frontend/src/lib/nutrition.test.ts`:
```ts
describe('explicit basis and source', () => {
  it('reads basis from nutritional_info when present', () => {
    expect(nutritionBasisFor({ curated_recipe_slug: '', nutritional_info: { basis: 'total' } })).toBe('total');
    expect(nutritionBasisFor({ curated_recipe_slug: '', nutritional_info: { basis: 'portion' } })).toBe('portion');
    expect(nutritionBasisFor({ curated_recipe_slug: 'x', nutritional_info: {} })).toBe('total');
  });
  it('nutritionSourceFor distinguishes computed from estimated', () => {
    expect(nutritionSourceFor({ nutritional_info: { nutrition_source: 'computed' } })).toBe('computed');
    expect(nutritionSourceFor({ nutritional_info: { nutrition_source: 'estimated' } })).toBe('estimated');
    expect(nutritionSourceFor({ nutritional_info: {} })).toBeUndefined();
  });
  it('normalizeNutrition ignores the meta keys', () => {
    const rows = normalizeNutrition({ calories: 600, protein: '30g', carbs: '40g', fat: '20g', basis: 'total', servings: 2, nutrition_source: 'computed' }, 2, 'total');
    expect(rows?.[0]).toMatchObject({ key: 'calories', value: 300 });
    expect(rows).toHaveLength(4);
  });
});
```
Backend `test_public_recipe_ssr.py`: add a test that a public `Recipe` with `servings=2`, `nutritional_info={'calories': 600, 'protein': '30g', 'carbs': '40g', 'fat': '20g', 'basis': 'total'}` renders `300 kcal` in the nutrition `<dl>` and `"calories": "300 kcal"` in the JSON-LD, and that `basis`/`servings`/`nutrition_source` never appear as `<dt>` labels.

- [ ] **Step 2: Implement**

`nutrition.ts`: `classifyKey` returns null for `basis`, `servings`, `nutrition_source` (add an early `if (['basis','servings','nutrition_source'].includes(k)) return null;`). `nutritionBasisFor(recipe)` → `const b = recipe?.nutritional_info?.basis; if (b === 'total' || b === 'portion') return b; return recipe?.curated_recipe_slug ? 'total' : undefined;`. Add `export function nutritionSourceFor(recipe): 'computed' | 'estimated' | undefined`.

`RecipePage.tsx`: replace the JSON-LD nutrition block (lines ~132-145) with the same `normalizeNutrition(...)` + per-row mapping `PublicRecipePage` already uses (copy that block). In the nutrition card heading, when `nutritionSourceFor(recipe) === 'estimated'` append `<span className="…muted…">· odhad</span>` (EN: estimate). Same badge on `PublicRecipePage`.

`llm_diet_planner_project/views.py`: replace `nutrition_html` and the JSON-LD nutrition loop with a small helper `_per_portion_nutrition(recipe)` returning `[(label_cs, value_str)]` — divides by `recipe.servings` when `nutritional_info.get('basis') == 'total'` or `recipe.curated_recipe_slug`, skips meta keys, labels `Energie/Bílkoviny/Sacharidy/Tuky`, formats `300 kcal` / `15 g`; both the `<dl>` and the JSON-LD use it.

- [ ] **Step 3: Run** — `cd frontend && npx vitest run src/lib/nutrition.test.ts src/pages && npx tsc --noEmit`; `GEMINI_API_KEY=dummy python3 -m pytest diet_planner/tests/test_public_recipe_ssr.py diet_planner/tests/test_public_recipe_views.py -q`.

- [ ] **Step 4: Commit** — `git add frontend/src/lib/nutrition.ts frontend/src/lib/nutrition.test.ts frontend/src/pages/RecipePage.tsx frontend/src/pages/PublicRecipePage.tsx llm_diet_planner_project/views.py diet_planner/tests/test_public_recipe_ssr.py && git commit -m "fix(nutrition): explicit basis in the frontend; per-portion JSON-LD and SSR; estimate badge"`

### Task 10: Verification, PR, deploy, prod backfill, QA

- [ ] **Step 1: Gates** — `GEMINI_API_KEY=dummy python3 -m pytest diet_planner billing analytics social -q -x`; `GEMINI_API_KEY=dummy python3 manage.py makemigrations --check --dry-run`; `cd frontend && npx tsc --noEmit && npx vitest run`; `grep -rn "typical_unit_weights\|nutrition_density\|nutrition_basis_repair\|plan_basis_repair\|correct_nutrition_basis" --include=*.py --include=*.yaml --include=*.md diet_planner social docs/superpowers/plans/2026-09-30* | grep -v "\.claude/"` → only historical docs.

- [ ] **Step 2: Local end-to-end** — `GEMINI_API_KEY=dummy python3 manage.py seed_canonical_ingredients` then, if the local DB has a corpus (`load_curated_corpus` from a prod dump if not), `recompute_nutrition` dry run: the worklist must be EMPTY for published recipes before the PR is opened; otherwise go back to Task 5 and fill the missing densities/piece weights (the worklist names them).

- [ ] **Step 3: PR** — push `feat/nutrition-table`; `gh pr create --base develop` with: what (nutrition = arithmetic over a per-100 g table; Gemini no longer guesses), how (model fields + seed, unit_vocab/line_mass/recipe_nutrition, curation gate + blockers, promote/remap, recompute_nutrition, gap-meal stamping, sides from table, explicit basis + per-portion JSON-LD/SSR), ops (migration 0041 additive; after deploy run `recompute_nutrition` dry run → review → `--apply` → `refresh_stale_recipe_cache --apply`; `seed_canonical_ingredients` runs at boot), data (source of every row is tagged; owner reviewed the table), QA plan. Watch `gh pr checks`, squash-merge, ff `prod`, poll the DO deployment.

- [ ] **Step 4: Prod backfill** — via the console harness (`prod_run.py` pattern; mutating management commands are allowed, long ones need the heartbeat driver): `recompute_nutrition --report /tmp/nutrition.csv` (dry run) → copy the summary + top-20 deltas into a message for the owner → on GO: `recompute_nutrition --apply` (expect 0 incomplete published; if not, fix the YAML, apply the dictionary on prod without a deploy via `seed_canonical_ingredients --file`, re-run) → `refresh_stale_recipe_cache --apply`. Record the REVERSAL map in the session scratchpad and in `docs/qa/2026-09-30-nutrition-backfill.md`.

- [ ] **Step 5: QA** — `/qa-prod` addendum: open three curated recipes on prod, recompute their per-portion kcal by hand from the ingredient list and the table (spot-check within rounding); generate one pool plan and confirm a curated meal shows no "odhad" badge; force one gap meal (a prompt the corpus cannot serve, e.g. "5 večeří z chobotnice") and confirm it shows "odhad" only if an ingredient did not resolve. Write the report; update `resume-here` memory and add a `nutrition-table` memory (identifier: source tags, how to add a new canonical's nutrition, the "worklist must be empty" rule).
