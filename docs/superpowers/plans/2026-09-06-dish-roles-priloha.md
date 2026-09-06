# Dish Roles, Příloha and Dish-Family Dedupe — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lečo (and every quick supper) can only carry večeře, arrives with bread and its calories, and never appears twice in one day; every main that is eaten with a příloha gets one inside its ingredients and nutrition.

**Architecture:** Two new `CuratedRecipe` roles (`breakfast`, `supper`) replace the ambiguous `light`; two new fields (`side_options`, `dish_family`) are filled by one recalibrated Gemini tag pass with an owner-reviewed dry run and a YAML override file. A static příloha table (`services/priloha.py`) is written into the meal's `ingredients` + `nutritional_info` by `scale_recipe_to_meal`, so every downstream consumer (shopping list, deals, public recipe, social facts) works unchanged. Selection and both swap paths exclude a dish family already served that day.

**Tech Stack:** Django 5.1 (sqlite test DB, `manage.py test`), google-generativeai (JSON mode), PyYAML, React 18 + TypeScript + vitest.

**Spec:** `docs/superpowers/specs/2026-09-06-dish-roles-priloha-design.md`

**Conventions for every task:**
- Backend tests: `cd /opt/llmDietPlanner && GEMINI_API_KEY=dummy python3 manage.py test <dotted.path> -v 2`. Django prints the summary on stderr; look for `OK` / `FAILED`.
- Frontend tests: `cd /opt/llmDietPlanner/frontend && npx vitest run <file>`; types: `npx tsc --noEmit`.
- Commit messages end with the two attribution lines:
  ```
  Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01SLKzDZptfyBGpbeKu7DND8
  ```
- Branch: `feat/dish-roles-priloha` (already exists, spec committed on it).
- Never run a Bash line with `&&` between two commands in this environment (the classifier refuses it); one command per Bash call.

---

## File map

| file | responsibility |
|---|---|
| `diet_planner/models/curated.py` | `DishRole` gains `BREAKFAST`, `SUPPER`; fields `side_options`, `dish_family` |
| `diet_planner/migrations/0038_dish_family_side_options.py` | schema for the above |
| `diet_planner/services/nutrition_plausibility.py` | kcal floors for the two new roles |
| `diet_planner/services/priloha.py` (new) | the five-row příloha table, `pick_side`, ingredient/nutrition rendering of a side |
| `diet_planner/data/canonical_ingredients.yaml`, `canonical_prices.yaml`, `docs/ingredient-availability-review.csv`, `diet_planner/data/ingredient_availability.yaml` | new canonical `bread-dumpling` |
| `diet_planner/services/recipe_retrieval.py` | slot table, `scale_recipe_to_meal(side=)`, `portions_for_target(side=)`, `render_curated_meal`, family dedupe in eligibility/scoring/selection, overlay |
| `diet_planner/views.py` | replace + refine paths use `render_curated_meal` and the family exclusion |
| `diet_planner/services/refine_agent.py` | corpus search tool gets the family exclusion |
| `diet_planner/services/dish_classification.py` (new) | Gemini classification (role, meal_types, side_options, dish_family), validation, override file |
| `diet_planner/data/dish_role_overrides.yaml` (new) | owner-pinned classifications |
| `diet_planner/llm_service.py` | `GeminiService.classify_dishes` |
| `diet_planner/management/commands/retag_dish_roles.py` | uses the service; `--force`; dry-run review report |
| `diet_planner/services/recipe_curation.py` | new recipes are classified at intake |
| `frontend/src/lib/portions.ts`, `components/recipe/RecipeIngredients.tsx`, `components/recipe/MealSideLine.tsx` (new), `pages/PlanView.tsx` | "Příloha" group + "s chlebem" line |
| `docs/dish-roles-ops.md` (new) | prod runbook for the tag pass |

---

### Task 1: Model — new roles, new fields, kcal floors

**Files:**
- Modify: `diet_planner/models/curated.py:42-47` (DishRole) and `:69-80` (after `dish_role`)
- Create: `diet_planner/migrations/0038_dish_family_side_options.py` (generated)
- Modify: `diet_planner/services/nutrition_plausibility.py:43-49`
- Test: `diet_planner/tests/test_dish_roles.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_dish_roles.py
"""Role vocabulary + corpus fields introduced by the příloha spec (2026-09-06)."""
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.nutrition_plausibility import min_portion_kcal


class DishRoleVocabularyTest(TestCase):
    def test_breakfast_and_supper_roles_exist(self):
        self.assertEqual(CuratedRecipe.DishRole.BREAKFAST, 'breakfast')
        self.assertEqual(CuratedRecipe.DishRole.SUPPER, 'supper')

    def test_light_is_still_accepted_as_legacy(self):
        # Untagged/legacy rows must keep deploying until the tag pass rewrites them.
        self.assertEqual(CuratedRecipe.DishRole.LIGHT, 'light')

    def test_new_fields_default_empty(self):
        r = CuratedRecipe.objects.create(
            name_cs='Lečo', source_url='https://example.test/leco', source_name='Ex',
        )
        r.refresh_from_db()
        self.assertEqual(r.side_options, [])
        self.assertEqual(r.dish_family, '')

    def test_new_roles_have_a_kcal_floor(self):
        self.assertEqual(min_portion_kcal('breakfast'), 150.0)
        self.assertEqual(min_portion_kcal('supper'), 150.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_dish_roles -v 2`
Expected: FAIL — `AttributeError: BREAKFAST` and `side_options`.

- [ ] **Step 3: Edit the model**

In `diet_planner/models/curated.py` replace the `DishRole` class:

```python
    class DishRole(models.TextChoices):
        MAIN = 'main', 'Main — can carry an oběd/večeře'
        SUPPER = 'supper', 'Supper — quick večeře dish (lečo, topinky); never oběd'
        BREAKFAST = 'breakfast', 'Breakfast — snídaně dish (kaše, vejce, toasty)'
        SOUP = 'soup', 'Soup — brothy, accompanies rather than carries'
        SIDE = 'side', 'Side — salad/dip/accompaniment/preserving base'
        DESSERT = 'dessert', 'Dessert / sweet'
        # Legacy: breakfast + quick supper in one bucket. The tag pass rewrites
        # every row carrying it; remove once prod reports zero.
        LIGHT = 'light', 'Light (legacy — retag to breakfast/supper)'
```

Directly after the `dish_role` field add:

```python
    side_options = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Ordered příloha keys the dish is eaten with (see services/priloha.py: "
            "chleb, brambory, ryze, knedlik, testoviny). [] = complete dish."
        ),
    )
    dish_family = models.CharField(
        max_length=60,
        blank=True,
        default='',
        db_index=True,
        help_text="Dedupe key (leco, gulas, svickova…). '' = untagged, never deduped.",
    )
```

- [ ] **Step 4: Generate the migration**

Run: `GEMINI_API_KEY=dummy python3 manage.py makemigrations diet_planner -n dish_family_side_options`
Expected: `diet_planner/migrations/0038_dish_family_side_options.py` with `AddField` ×2 and `AlterField` for `dish_role` choices.

- [ ] **Step 5: Add the kcal floors**

In `diet_planner/services/nutrition_plausibility.py` replace the table:

```python
ROLE_MIN_PORTION_KCAL: Dict[str, float] = {
    'main': 200.0,
    'light': 150.0,      # legacy
    'breakfast': 150.0,
    'supper': 150.0,
    'soup': 100.0,
    'dessert': 100.0,
    'side': 40.0,
}
```

- [ ] **Step 6: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_dish_roles diet_planner.tests.test_retag_dish_roles -v 2`
Expected: OK (5 + 6 tests).

- [ ] **Step 7: Commit**

```
git add diet_planner/models/curated.py diet_planner/migrations/0038_dish_family_side_options.py diet_planner/services/nutrition_plausibility.py diet_planner/tests/test_dish_roles.py
git commit -m "feat(corpus): breakfast/supper roles, side_options and dish_family fields"
```

---

### Task 2: Slot table — supper is dinner-only, main leaves breakfast

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py:80-90`
- Test: `diet_planner/tests/test_recipe_retrieval.py` (RoleGate class, after `test_side_ok_for_small_meal_and_snack`)

- [ ] **Step 1: Write the failing tests**

Add inside the role-gate `TestCase` class in `diet_planner/tests/test_recipe_retrieval.py`:

```python
    def test_supper_allowed_for_dinner_only(self):
        leco = make_recipe(
            name_cs='Lečo', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.SUPPER)
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
        self.assertEqual(eligible_recipes_for_slot('breakfast', set()), [])
        self.assertEqual([r.id for r in eligible_recipes_for_slot('dinner', set())], [leco.id])

    def test_breakfast_role_allowed_for_breakfast_only(self):
        kase = make_recipe(
            name_cs='Ovesná kaše', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.BREAKFAST)
        self.assertEqual([r.id for r in eligible_recipes_for_slot('breakfast', set())], [kase.id])
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
        self.assertEqual(eligible_recipes_for_slot('dinner', set()), [])

    def test_main_no_longer_carries_breakfast(self):
        make_recipe(
            name_cs='Guláš', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.MAIN)
        self.assertEqual(eligible_recipes_for_slot('breakfast', set()), [])

    def test_legacy_light_still_passes_breakfast_and_dinner(self):
        om = make_recipe(
            name_cs='Omeleta', meal_types=['breakfast', 'lunch', 'dinner'],
            dish_role=CuratedRecipe.DishRole.LIGHT)
        self.assertEqual([r.id for r in eligible_recipes_for_slot('breakfast', set())], [om.id])
        self.assertEqual([r.id for r in eligible_recipes_for_slot('dinner', set())], [om.id])
        self.assertEqual(eligible_recipes_for_slot('lunch', set()), [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval -v 2 -k supper -k breakfast_role -k no_longer_carries`
Expected: 3 FAIL (supper reaches lunch; main reaches breakfast).

- [ ] **Step 3: Replace the slot table**

In `diet_planner/services/recipe_retrieval.py`:

```python
# Which dish roles can CARRY each slot (Czech meal culture: oběd is a warm
# main; večeře may also be a quick supper dish or a soup; snídaně is its own
# family of dishes). None = no role gate. Untagged ('') always passes —
# rollout safety until `retag_dish_roles` has tagged the corpus. 'light' is
# the legacy breakfast+supper bucket and keeps its old reach until retagged.
_SLOT_ALLOWED_ROLES = {
    'breakfast': {'breakfast', 'dessert', 'light'},
    'lunch': {'main'},
    'dinner': {'main', 'supper', 'soup', 'light'},
    'small_meal': None,
    'snack': None,
}
```

- [ ] **Step 4: Run the whole retrieval module**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval -v 2`
Expected: OK. If `test_overlay_fills_empty_main_slot` or another overlay test used a `main` recipe for breakfast, give that fixture `dish_role=''` (untagged) — untagged behaviour is unchanged by design.

- [ ] **Step 5: Commit**

```
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_retrieval.py
git commit -m "feat(planner): supper carries dinner only, main no longer carries breakfast"
```

---

### Task 3: New canonical `bread-dumpling`

**Files:**
- Modify: `diet_planner/data/canonical_ingredients.yaml` (append after the `bread roll` entry, ~line 1608)
- Modify: `diet_planner/data/canonical_prices.yaml` (alphabetical, after `bread-loaf`)
- Modify: `docs/ingredient-availability-review.csv` (append a row)
- Regenerate: `diet_planner/data/ingredient_availability.yaml`
- Test: `diet_planner/tests/test_priloha.py` (created here, extended in Task 4)

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_priloha.py
"""The fixed příloha table and its data dependencies."""
from pathlib import Path

import yaml
from django.conf import settings
from django.test import TestCase
from django.utils.text import slugify

DATA = Path(settings.BASE_DIR) / 'diet_planner' / 'data'


def canonical_slugs():
    with open(DATA / 'canonical_ingredients.yaml', encoding='utf-8') as fh:
        return {slugify(e['name']) for e in yaml.safe_load(fh)}


def price_book_slugs():
    with open(DATA / 'canonical_prices.yaml', encoding='utf-8') as fh:
        book = yaml.safe_load(fh)
    return set((book.get('prices') or book).keys())


class BreadDumplingCanonicalTest(TestCase):
    def test_dictionary_has_bread_dumpling(self):
        self.assertIn('bread-dumpling', canonical_slugs())

    def test_price_book_has_bread_dumpling(self):
        self.assertIn('bread-dumpling', price_book_slugs())

    def test_availability_has_bread_dumpling_common(self):
        with open(DATA / 'ingredient_availability.yaml', encoding='utf-8') as fh:
            rows = {r['slug']: r for r in yaml.safe_load(fh)}
        self.assertEqual(rows['bread-dumpling']['availability'], 'common')
```

Check the price-book top-level shape first: `head -5 diet_planner/data/canonical_prices.yaml`. If the slugs sit under a top-level key (e.g. `prices:`), the helper above already handles it; if not, it reads the root.

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_priloha -v 2`
Expected: 3 FAIL.

- [ ] **Step 3: Add the dictionary entry**

Append to `diet_planner/data/canonical_ingredients.yaml` directly after the `bread roll` block:

```yaml
- name: bread dumpling
  name_cs: houskový knedlík
  category: grains
  default_unit: g
  aliases:
    - { alias: "houskové knedlíky", language_code: cs }
    - { alias: "knedlík", language_code: cs }
    - { alias: "knedlíky", language_code: cs }
    - { alias: "kynutý knedlík", language_code: cs }
    - { alias: "kynuté knedlíky", language_code: cs }
```

Verify no other entry already owns `knedlík`: `grep -n "knedl" diet_planner/data/canonical_ingredients.yaml` must show only these lines.

- [ ] **Step 4: Add the price-book entry**

Insert after the `bread-loaf` block in `diet_planner/data/canonical_prices.yaml`, same indentation as its neighbours:

```yaml
  bread-dumpling:
    name_cs: "houskový knedlík"
    unit: g
    price_per_unit: 0.09
    pack: 500.0
    samples: 0
    verified: false
    source: manual-estimate-2026-09
```

- [ ] **Step 5: Add the availability row and regenerate**

Append to `docs/ingredient-availability-review.csv`:

```
,0,bread-dumpling,houskový knedlík,grains,common,high,chilled houskový knedlík in every supermarket,,
```

Run: `GEMINI_API_KEY=dummy python3 manage.py import_availability_review`
Expected: the command rewrites `diet_planner/data/ingredient_availability.yaml`; `grep -n -A3 "slug: bread-dumpling" diet_planner/data/ingredient_availability.yaml` shows `availability: common`.

- [ ] **Step 6: Run the test**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_priloha -v 2`
Expected: OK (3 tests).

- [ ] **Step 7: Commit**

```
git add diet_planner/data/canonical_ingredients.yaml diet_planner/data/canonical_prices.yaml docs/ingredient-availability-review.csv diet_planner/data/ingredient_availability.yaml diet_planner/tests/test_priloha.py
git commit -m "feat(dictionary): bread-dumpling canonical for the příloha table"
```

---

### Task 4: The příloha table and `pick_side`

**Files:**
- Create: `diet_planner/services/priloha.py`
- Test: `diet_planner/tests/test_priloha.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_priloha.py`:

```python
from types import SimpleNamespace

from diet_planner.services.priloha import (
    SIDES, SIDE_KEYS, pick_side, side_ingredient, side_nutrition,
)


class SideTableTest(TestCase):
    def test_five_keys_in_spec_order(self):
        self.assertEqual(SIDE_KEYS, ('chleb', 'brambory', 'ryze', 'knedlik', 'testoviny'))

    def test_every_canonical_exists_in_dictionary_and_price_book(self):
        slugs = canonical_slugs()
        book = price_book_slugs()
        for side in SIDES.values():
            self.assertIn(side.canonical, slugs, side.key)
            self.assertIn(side.canonical, book, side.key)

    def test_every_row_is_complete(self):
        for side in SIDES.values():
            self.assertTrue(side.name_cs and side.with_cs and side.display, side.key)
            self.assertGreater(side.grams, 0)
            for n in (side.calories, side.protein, side.carbs, side.fat):
                self.assertGreaterEqual(n, 0)
            self.assertGreater(side.calories, 0)

    def test_dietary_breaks(self):
        self.assertIn('gluten_free', SIDES['chleb'].breaks_tags)
        self.assertIn('gluten_free', SIDES['knedlik'].breaks_tags)
        self.assertIn('vegan', SIDES['knedlik'].breaks_tags)
        self.assertIn('gluten_free', SIDES['testoviny'].breaks_tags)
        self.assertEqual(SIDES['brambory'].breaks_tags, frozenset())
        self.assertEqual(SIDES['ryze'].breaks_tags, frozenset())


class PickSideTest(TestCase):
    def _recipe(self, options):
        return SimpleNamespace(side_options=options)

    def test_first_option_wins(self):
        self.assertEqual(pick_side(self._recipe(['chleb', 'brambory']), set()).key, 'chleb')

    def test_dietary_break_skips_to_next(self):
        self.assertEqual(
            pick_side(self._recipe(['chleb', 'brambory']), {'gluten_free'}).key, 'brambory')

    def test_no_options_is_none(self):
        self.assertIsNone(pick_side(self._recipe([]), set()))
        self.assertIsNone(pick_side(self._recipe(None), set()))

    def test_no_fit_is_none(self):
        self.assertIsNone(pick_side(self._recipe(['chleb', 'knedlik']), {'gluten_free'}))

    def test_unknown_key_is_ignored(self):
        self.assertEqual(pick_side(self._recipe(['sushi', 'ryze']), set()).key, 'ryze')


class SideRenderTest(TestCase):
    def test_ingredient_scales_with_portions(self):
        ing = side_ingredient(SIDES['chleb'], portions=2)
        self.assertEqual(ing, {
            'name': 'chléb', 'quantity': 160.0, 'unit': 'g',
            'canonical': 'bread-loaf', 'catalog_id': None,
            'optional': False, 'role': 'side',
        })

    def test_nutrition_scales_with_portions(self):
        n = side_nutrition(SIDES['ryze'], portions=3)
        self.assertEqual(n['calories'], 630.0)
        self.assertEqual(n['carbs'], SIDES['ryze'].carbs * 3)
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_priloha -v 2`
Expected: ImportError on `diet_planner.services.priloha`.

- [ ] **Step 3: Create the module**

```python
# diet_planner/services/priloha.py
"""
The fixed příloha (side) table.

A Czech main is eaten WITH something — guláš with knedlík or bread, lečo with
bread, řízek with potatoes — but source recipes carry that only in prose, so
the corpus lost it (spec 2026-09-06). Rather than curate side recipes, the
planner attaches one of these five rows to a main whose `side_options` name
it. The row becomes an ordinary ingredient (`role: 'side'`) plus nutrition on
the meal, so the shopping list, deals headline and every other reader pick it
up without knowing sides exist.

Quantities are the PURCHASED form per portion (raw potatoes, dry rice/pasta,
bought bread/knedlík). Nutrients are standard food-table values rounded to
10 kcal — labeled estimates, like every other number in the product. Keep
this table the only place they live.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Iterable, Optional


@dataclass(frozen=True)
class Side:
    key: str
    name_cs: str        # ingredient-list name
    with_cs: str        # card line: "s chlebem"
    canonical: str      # must resolve in data/canonical_ingredients.yaml
    grams: float        # purchased-form grams per portion
    display: str        # per-portion display: "2 krajíce"
    calories: float     # per portion
    protein: float      # g per portion
    carbs: float
    fat: float
    breaks_tags: FrozenSet[str]  # dietary_tags this side would violate


SIDES: Dict[str, Side] = {
    'chleb': Side('chleb', 'chléb', 's chlebem', 'bread-loaf',
                  80, '2 krajíce', 200, 7, 38, 2, frozenset({'gluten_free'})),
    'brambory': Side('brambory', 'vařené brambory', 's vařenými bramborami', 'potatoes',
                     250, '250 g', 190, 5, 42, 0, frozenset()),
    'ryze': Side('ryze', 'rýže', 's rýží', 'rice-basmati',
                 60, '60 g suché rýže', 210, 4, 47, 0, frozenset()),
    'knedlik': Side('knedlik', 'houskový knedlík', 's houskovým knedlíkem', 'bread-dumpling',
                    120, '3 plátky', 240, 8, 48, 2, frozenset({'gluten_free', 'vegan'})),
    'testoviny': Side('testoviny', 'těstoviny', 's těstovinami', 'pasta',
                      70, '70 g suchých těstovin', 250, 9, 50, 1, frozenset({'gluten_free'})),
}
SIDE_KEYS = tuple(SIDES)


def pick_side(recipe: Any, required_tags: Iterable[str]) -> Optional[Side]:
    """First `side_options` entry the plan's dietary tags allow, else None.
    Unknown keys are skipped (a stale tag must not crash a plan)."""
    tags = set(required_tags or ())
    for key in (getattr(recipe, 'side_options', None) or []):
        side = SIDES.get(str(key))
        if side is None or (side.breaks_tags & tags):
            continue
        return side
    return None


def side_ingredient(side: Side, *, portions: int) -> Dict[str, Any]:
    """The side as a meal ingredient row, in the same shape `scale_recipe_to_meal`
    emits, marked `role: 'side'` so the frontend can group it."""
    return {
        'name': side.name_cs,
        'quantity': round(side.grams * portions, 2),
        'unit': 'g',
        'canonical': side.canonical,
        'catalog_id': None,
        'optional': False,
        'role': 'side',
    }


def side_nutrition(side: Side, *, portions: int) -> Dict[str, float]:
    return {
        'calories': side.calories * portions,
        'protein': side.protein * portions,
        'carbs': side.carbs * portions,
        'fat': side.fat * portions,
    }


def side_meta(side: Side) -> Dict[str, str]:
    """The `meal['side']` object the plan card reads."""
    return {'key': side.key, 'name_cs': side.name_cs, 'with_cs': side.with_cs, 'display': side.display}
```

- [ ] **Step 4: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_priloha -v 2`
Expected: OK (15 tests).

- [ ] **Step 5: Commit**

```
git add diet_planner/services/priloha.py diet_planner/tests/test_priloha.py
git commit -m "feat(planner): fixed příloha table with pick_side"
```

---

### Task 5: Meal shape — `scale_recipe_to_meal(side=)`, `portions_for_target(side=)`, `render_curated_meal`

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py:682-770` (rendering section)
- Test: `diet_planner/tests/test_recipe_retrieval.py` (new class at end of file)

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_recipe_retrieval.py`:

```python
class PrilohaOnMealTest(TestCase):
    """The side is written INTO ingredients + nutrition so every downstream
    reader (shopping list, deals, public recipe, social facts) sees it."""

    def _leco(self, **kw):
        return make_recipe(
            name_cs='Lečo', base_servings=4,
            base_nutrition={'calories': 2000, 'protein': 80, 'carbs': 100, 'fat': 120},
            side_options=['chleb', 'brambory'], dish_role=CuratedRecipe.DishRole.SUPPER,
            meal_types=['dinner'], **kw)

    def test_no_side_is_byte_identical_to_before(self):
        r = self._leco()
        meal = scale_recipe_to_meal(r, portions=1)
        self.assertNotIn('side', meal)
        self.assertEqual([i['name'] for i in meal['ingredients']], ['rýže'])
        self.assertEqual(meal['nutritional_info']['calories'], 500)

    def test_side_appended_as_role_side_ingredient(self):
        from diet_planner.services.priloha import SIDES
        r = self._leco()
        meal = scale_recipe_to_meal(r, portions=2, side=SIDES['chleb'])
        last = meal['ingredients'][-1]
        self.assertEqual(last['role'], 'side')
        self.assertEqual(last['name'], 'chléb')
        self.assertEqual(last['quantity'], 160.0)
        self.assertEqual(last['canonical'], 'bread-loaf')
        self.assertNotIn('role', meal['ingredients'][0])

    def test_side_counted_in_nutrition(self):
        from diet_planner.services.priloha import SIDES
        r = self._leco()
        meal = scale_recipe_to_meal(r, portions=2, side=SIDES['chleb'])
        self.assertEqual(meal['nutritional_info']['calories'], 1000 + 400)
        self.assertEqual(meal['nutritional_info']['carbs'], '126g')  # 50 + 76

    def test_meal_carries_side_meta(self):
        from diet_planner.services.priloha import SIDES
        meal = scale_recipe_to_meal(self._leco(), portions=1, side=SIDES['chleb'])
        self.assertEqual(meal['side'], {
            'key': 'chleb', 'name_cs': 'chléb', 'with_cs': 's chlebem', 'display': '2 krajíce'})

    def test_portions_for_target_counts_the_side(self):
        from diet_planner.services.priloha import SIDES
        from diet_planner.services.recipe_retrieval import portions_for_target
        r = self._leco()  # 500 kcal/portion; chléb adds 200
        self.assertEqual(portions_for_target(r, 1400), 3)
        self.assertEqual(portions_for_target(r, 1400, side=SIDES['chleb']), 2)

    def test_render_curated_meal_attaches_allowed_side(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        meal, gap = render_curated_meal(self._leco(), target_kcal=700, required_tags=set())
        self.assertEqual(meal['side']['key'], 'chleb')
        self.assertIsNone(gap)

    def test_render_curated_meal_respects_diet(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        meal, gap = render_curated_meal(self._leco(), target_kcal=700, required_tags={'gluten_free'})
        self.assertEqual(meal['side']['key'], 'brambory')
        self.assertIsNone(gap)

    def test_render_curated_meal_reports_unavailable_side(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        r = self._leco(side_options=['chleb', 'knedlik'])
        meal, gap = render_curated_meal(r, target_kcal=700, required_tags={'gluten_free'})
        self.assertNotIn('side', meal)
        self.assertEqual(gap, 'side_unavailable')

    def test_render_curated_meal_no_options_no_gap(self):
        from diet_planner.services.recipe_retrieval import render_curated_meal
        meal, gap = render_curated_meal(self._leco(side_options=[]), target_kcal=700, required_tags=set())
        self.assertNotIn('side', meal)
        self.assertIsNone(gap)
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval.PrilohaOnMealTest -v 2`
Expected: FAIL — unexpected keyword `side`, no `render_curated_meal`.

- [ ] **Step 3: Implement**

In `diet_planner/services/recipe_retrieval.py` add to the imports:

```python
from diet_planner.services.priloha import Side, pick_side, side_ingredient, side_meta, side_nutrition
```

Change `scale_recipe_to_meal`'s signature and body:

```python
def scale_recipe_to_meal(
    recipe: CuratedRecipe,
    *,
    factor: float = 1.0,
    portions: Optional[int] = None,
    side: Optional[Side] = None,
) -> Dict[str, Any]:
    """Render a CuratedRecipe into a meal object, scaling quantities/nutrition by
    `factor` (default 1.0 = base servings). `portions` overrides factor: serve
    that many of the recipe's base_servings portions (factor = portions/base),
    and the meal's `servings` reports the portions actually served. Ingredients
    keep their canonical / catalog_id so the shopping list stays coherent by
    construction. Source attribution is attached for the frontend credit line.

    `side` (a příloha row) is written INTO the meal: one more ingredient with
    `role: 'side'`, its nutrients added to the totals, and a `side` object for
    the card — so nothing downstream has to know sides exist."""
    if portions is not None:
        factor = portions / max(int(recipe.base_servings or 1), 1)
    served = portions if portions is not None else recipe.base_servings
    ingredients: List[Dict[str, Any]] = []
    for ing in (recipe.ingredients or []):
        qty = ing.get('quantity')
        ingredients.append({
            'name': ing.get('name'),
            'quantity': (round(qty * factor, 2) if isinstance(qty, (int, float)) else qty),
            'unit': ing.get('unit'),
            'canonical': ing.get('canonical'),
            'catalog_id': ing.get('catalog_id'),
            'optional': bool(ing.get('optional', False)),
        })

    instructions = [
        s.get('text') if isinstance(s, dict) else str(s)
        for s in (recipe.instructions or [])
        if (s.get('text') if isinstance(s, dict) else s)
    ]

    base = recipe.base_nutrition or {}
    totals = {
        'calories': base.get('calories', 0) * factor if base.get('calories') else None,
        'protein': base.get('protein', 0) * factor if base.get('protein') is not None else None,
        'carbs': base.get('carbs', 0) * factor if base.get('carbs') is not None else None,
        'fat': base.get('fat', 0) * factor if base.get('fat') is not None else None,
    }
    if side is not None:
        side_portions = max(int(served or 1), 1)
        ingredients.append(side_ingredient(side, portions=side_portions))
        for key, add in side_nutrition(side, portions=side_portions).items():
            totals[key] = (totals[key] or 0) + add
    nutritional_info = {
        'calories': int(round(totals['calories'])) if totals['calories'] else None,
        'protein': _fmt_grams(totals['protein']) if totals['protein'] is not None else None,
        'carbs': _fmt_grams(totals['carbs']) if totals['carbs'] is not None else None,
        'fat': _fmt_grams(totals['fat']) if totals['fat'] is not None else None,
    }

    meal = {
        'name': recipe.name_cs,
        'servings': served,
        'description': recipe.description or '',
        'food_category': '',  # stock-image slug; left blank -> generic fallback
        'preparation_time': recipe.total_time or recipe.prep_time or None,
        'ingredients': ingredients,
        'instructions': instructions,
        'nutritional_info': nutritional_info,
        # --- grounding provenance (consumed by RecipePage attribution) ---
        'source': 'curated',
        'curated_recipe_id': recipe.id,
        'curated_recipe_slug': recipe.slug,
        'source_name': recipe.source_name,
        'source_url': recipe.source_url,
        'source_author': recipe.source_author or '',
    }
    if side is not None:
        meal['side'] = side_meta(side)
    return meal
```

Change `portions_for_target`:

```python
def portions_for_target(
    recipe: CuratedRecipe, target: Optional[float], side: Optional[Side] = None,
) -> int:
    """How many of the recipe's portions fill the slot's calorie target.
    Without a target (or usable nutrition) serve ONE portion — never the whole
    multi-serving pot (goal 133: 1709 kcal / 6 servings rendered as one
    dinner). Capped at base_servings: we never invent more food than the
    recipe makes. A `side` counts toward the per-portion figure, so attaching
    bread cannot overshoot the slot."""
    base = max(int(recipe.base_servings or 1), 1)
    per_portion = per_portion_calories(recipe)
    if not target or not per_portion:
        return 1
    if side is not None:
        per_portion += side.calories
    # ... keep the existing rounding/cap logic below unchanged ...
```

(Only the three lines above change; the remainder of the function body stays as it is today.)

Add after `portions_for_target`:

```python
def render_curated_meal(
    recipe: CuratedRecipe,
    *,
    target_kcal: Optional[float],
    required_tags: Set[str],
) -> tuple:
    """The ONE way a curated recipe becomes a plan meal: pick the příloha the
    diet allows, size the portions on main+side, render. Used by the overlay,
    the replace swap, and refine preview/accept, so the card never differs
    from what accept writes. Returns (meal, gap_reason) where gap_reason is
    'side_unavailable' when the recipe wants a side and the diet forbids all
    of them (served bare — a corpus/diet gap worth counting), else None."""
    side = pick_side(recipe, required_tags)
    gap = 'side_unavailable' if (side is None and (recipe.side_options or [])) else None
    meal = scale_recipe_to_meal(
        recipe, portions=portions_for_target(recipe, target_kcal, side=side), side=side,
    )
    return meal, gap
```

- [ ] **Step 4: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval -v 2`
Expected: OK (all, including the nine new). If `test_string_nutritional_info…` or any rounding test regresses, compare against the previous `nutritional_info` arithmetic — the totals must round exactly as before when `side is None`.

- [ ] **Step 5: Commit**

```
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_retrieval.py
git commit -m "feat(planner): scale_recipe_to_meal writes the příloha into ingredients and nutrition"
```

---

### Task 6: Overlay uses `render_curated_meal` and records side gaps

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py:849-978` (`overlay_curated_recipes`)
- Test: `diet_planner/tests/test_recipe_retrieval.py`

- [ ] **Step 1: Write the failing tests**

Append to the `PrilohaOnMealTest` class:

```python
    def test_overlay_attaches_side_to_dinner(self):
        r = self._leco()
        days = [{'day_number': 1, 'dinner': {'name': 'x', 'nutritional_info': {'calories': 700}}}]
        result = overlay_curated_recipes(days, goal(breakfast=False, lunch=False))
        meal = result['days'][0]['dinner']
        self.assertEqual(meal['curated_recipe_id'], r.id)
        self.assertEqual(meal['side']['key'], 'chleb')
        self.assertEqual(meal['ingredients'][-1]['role'], 'side')

    def test_overlay_records_side_gap(self):
        self._leco(side_options=['chleb', 'knedlik'], dietary_tags=['gluten_free'])
        days = [{'day_number': 1, 'dinner': {'name': 'x', 'nutritional_info': {'calories': 700}}}]
        result = overlay_curated_recipes(
            days, goal(breakfast=False, lunch=False, dietary_restrictions='bezlepková'))
        reasons = [g['reason'] for g in result['gaps']]
        self.assertIn('side_unavailable', reasons)
        self.assertNotIn('side', result['days'][0]['dinner'])
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval.PrilohaOnMealTest -v 2`
Expected: 2 FAIL (no `side` on the meal, no gap).

- [ ] **Step 3: Rewire the overlay**

In `overlay_curated_recipes`, after `required_tags`-less code, compute the tags once near the top (after `store_derived_dietary_tags(...)`):

```python
    required_tags = required_tags_for_goal(goal)
    gaps: List[Dict[str, Any]] = list(selection['gaps'])
```

(Move the `gaps` line to just after `selection = select_recipes_for_plan(...)`.)

Replace both `scale_recipe_to_meal(recipe, portions=portions_for_target(recipe, target))` calls with:

```python
            meal, side_gap = render_curated_meal(recipe, target_kcal=target, required_tags=required_tags)
            if side_gap:
                gaps.append({'day_number': day_number, 'slot': slot, 'reason': side_gap,
                             'required_tags': sorted(required_tags), 'unmatched_wanted': []})
```

(in the list-slot loop use `f'{slot_type}:{i}'` for `'slot'`). Return `'gaps': gaps` instead of `selection['gaps']`.

- [ ] **Step 4: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval -v 2`
Expected: OK.

- [ ] **Step 5: Commit**

```
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_retrieval.py
git commit -m "feat(planner): overlay serves mains with their příloha, counts side gaps"
```

---

### Task 7: Dish-family dedupe in eligibility, scoring and selection

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py` (`eligible_recipes_for_slot`, `score_recipe`, `select_recipes_for_plan`)
- Test: `diet_planner/tests/test_recipe_retrieval.py`

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_recipe_retrieval.py`:

```python
class DishFamilyDedupeTest(TestCase):
    """Same family never twice in a day; discouraged across the plan."""

    def _pair(self):
        a = make_recipe(name_cs='Lečo', dish_family='leco', meal_types=['lunch', 'dinner'])
        b = make_recipe(name_cs='Lečo s klobásou', dish_family='leco', meal_types=['lunch', 'dinner'])
        return a, b

    def test_exclude_families_drops_candidates(self):
        a, b = self._pair()
        c = make_recipe(name_cs='Guláš', dish_family='gulas')
        ids = {r.id for r in eligible_recipes_for_slot('lunch', set(), exclude_families={'leco'})}
        self.assertEqual(ids, {c.id})

    def test_empty_family_is_never_excluded(self):
        r = make_recipe(name_cs='Bez rodiny', dish_family='')
        ids = {x.id for x in eligible_recipes_for_slot('lunch', set(), exclude_families={''})}
        self.assertEqual(ids, {r.id})

    def test_family_repeat_in_plan_is_penalised_below_wanted_weight(self):
        from collections import Counter
        a, _ = self._pair()
        base = score_recipe(a, used_recipe_ids=set(), used_cuisines=[])
        once = score_recipe(a, used_recipe_ids=set(), used_cuisines=[], used_families=Counter({'leco': 1}))
        thrice = score_recipe(a, used_recipe_ids=set(), used_cuisines=[], used_families=Counter({'leco': 3}))
        self.assertEqual(base - once, 8.0)
        self.assertEqual(base - thrice, 16.0)  # capped

    def test_same_day_never_gets_two_of_a_family(self):
        a, b = self._pair()
        make_recipe(name_cs='Guláš', dish_family='gulas')
        make_recipe(name_cs='Svíčková', dish_family='svickova')
        for seed in range(1, 8):
            sel = select_recipes_for_plan(goal(id=seed, breakfast=False))
            fams = [r.dish_family for r in sel['days'][0]['slots'].values()]
            self.assertEqual(len(fams), len(set(fams)), fams)

    def test_tiny_pool_relaxes_with_a_gap(self):
        self._pair()  # only lečo-family recipes exist
        sel = select_recipes_for_plan(goal(breakfast=False))
        self.assertEqual(sel['coverage']['filled'], 2)
        self.assertIn('family_relaxed', [g['reason'] for g in sel['gaps']])
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval.DishFamilyDedupeTest -v 2`
Expected: FAIL (unexpected kwargs).

- [ ] **Step 3: Implement**

`eligible_recipes_for_slot` — add the parameter and the gate (after the `exclude_ids` check):

```python
    exclude_families: Optional[Set[str]] = None,
    ...
    exclude_families = {f for f in (exclude_families or set()) if f}
    ...
        if r.dish_family and r.dish_family in exclude_families:
            continue
```

`score_recipe` — add the parameter and the term (after the cuisine penalty):

```python
    used_families: Optional[Mapping[str, int]] = None,
    ...
    # Dish family across the plan: a second guláš this week ranks below a
    # fresh dish, but stays under the wanted-ingredient weight so "chci guláš"
    # still wins. Same-day repeats are excluded before scoring, not here.
    if used_families and recipe.dish_family:
        repeats = used_families.get(recipe.dish_family, 0)
        score -= min(_RECENT_SERVE_PENALTY * repeats, 2 * _RECENT_SERVE_PENALTY)
```

Add `Mapping` and `Counter` to the imports (`from collections import Counter`; `from typing import ... Mapping`).

`select_recipes_for_plan` — track families and gate:

```python
    used_families_plan: Counter = Counter()
    ...
    for day_number in range(1, num_days + 1):
        chosen: Dict[str, Any] = {}
        used_families_today: Set[str] = set()
        for slot_type, slot_key in slot_plan:
            total += 1
            candidates = eligible_recipes_for_slot(
                slot_type, required_tags, pool=pool, facets=facets,
                exclude_families=used_families_today)
            if not candidates and used_families_today:
                # Family dedupe starved the slot: a repeat family beats an
                # empty plate, but it is a signal worth counting.
                candidates = eligible_recipes_for_slot(
                    slot_type, required_tags, pool=pool, facets=facets)
                if candidates:
                    record_gap(day_number, slot_key, 'family_relaxed')
            if not candidates:
                # (existing role-relaxed fallback block, unchanged)
```

pass `used_families=used_families_plan` into `score_recipe(...)`, and after `chosen[slot_key] = best`:

```python
            if best.dish_family:
                used_families_today.add(best.dish_family)
                used_families_plan[best.dish_family] += 1
```

- [ ] **Step 4: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_retrieval -v 2`
Expected: OK.

- [ ] **Step 5: Commit**

```
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_retrieval.py
git commit -m "feat(planner): dish-family dedupe per day, penalty across the plan"
```

---

### Task 8: Swap paths — replace, refine preview/accept, refine agent

**Files:**
- Modify: `diet_planner/views.py` (`_plan_swap_state`, `_commit_slot_swap`, `_candidate_payload`, `RecipeReplaceView.post`, `RecipeRefineView` pick)
- Modify: `diet_planner/services/refine_agent.py:198-260` (`_tool_search_corpus`) and its caller in `run_refine_turn`
- Tests: `diet_planner/tests/test_recipe_replace.py`, `diet_planner/tests/test_recipe_refine.py`, `diet_planner/tests/test_refine_agent.py`

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_recipe_replace.py`:

```python
class PrilohaAndFamilyOnSwapTest(ReplaceRecipeTestBase):
    def _with_dinner(self, plan, recipe):
        from diet_planner.services.recipe_retrieval import scale_recipe_to_meal
        dinner = scale_recipe_to_meal(recipe)
        dinner['meal_identifier'] = f'{self.goal.id}:1:dinner:0'
        plan.days[0]['dinner'] = dinner
        plan.save(update_fields=['days'])
        return plan

    def test_swap_never_offers_a_family_already_on_that_day(self):
        current = make_recipe(name_cs='Kuřecí rizoto', dish_family='rizoto')
        leco_a = make_recipe(name_cs='Lečo s klobásou', dish_family='leco')
        leco_b = make_recipe(name_cs='Lečo', dish_family='leco')
        other = make_recipe(name_cs='Guláš', dish_family='gulas')
        plan = self._with_dinner(self._plan_with_lunch(current), leco_a)

        resp = self.client.post(self._url(), {'hint': ''}, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['replaced'])
        plan.refresh_from_db()
        self.assertEqual(plan.days[0]['lunch']['curated_recipe_id'], other.id)
        self.assertNotEqual(plan.days[0]['lunch']['curated_recipe_id'], leco_b.id)

    def test_swap_writes_the_side_into_the_cached_recipe(self):
        current = make_recipe(name_cs='Kuřecí rizoto')
        make_recipe(name_cs='Svíčková', side_options=['knedlik'])
        self._plan_with_lunch(current)

        resp = self.client.post(self._url(), {'hint': ''}, format='json')

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data['data']['replaced'])
        row = Recipe.objects.get(meal_identifier=f'{self.goal.id}:1:lunch:0')
        self.assertEqual(row.ingredients[-1]['role'], 'side')
        self.assertEqual(row.ingredients[-1]['canonical'], 'bread-dumpling')
```

Append to `diet_planner/tests/test_recipe_refine.py` inside `PreviewTurnTest`:

```python
    def test_preview_candidate_calories_include_the_side(self):
        current = make_recipe(name_cs='Kuře s rýží')
        chicken = make_recipe(
            name_cs='Kuřecí řízek', side_options=['brambory'],
            ingredients=[{'name': 'kuřecí prsa', 'quantity': 150, 'unit': 'g', 'canonical': 'chicken-breast'}],
        )
        self._plan_with_lunch(current)  # lunch slot carries 500 kcal (make_recipe default)

        facets = PromptFacets(wanted_ingredients={'kuřecí'})
        with patch('diet_planner.views.refine_conversation',
                   return_value=(facets, 'Chcete to spíš rychlé?')):
            resp = self._preview(USER_MSG)

        self.assertEqual(resp.status_code, 200)
        body = resp.data['data']
        self.assertEqual(body['candidate']['curated_recipe_id'], chicken.id)
        # 1 portion of the main (500) + brambory (190): the card must show what accept writes.
        self.assertEqual(body['candidate']['calories'], 690)
```

Append to `diet_planner/tests/test_refine_agent.py`:

```python
class SearchCorpusFamilyExclusionTest(TestCase):
    def test_family_already_on_the_day_is_not_offered(self):
        leco = make_recipe(name_cs='Lečo', dish_family='leco')
        gulas = make_recipe(name_cs='Guláš', dish_family='gulas')
        payload = refine_agent._tool_search_corpus(
            {},
            meal_type='lunch',
            required_tags=set(),
            pool=[leco, gulas],
            exclude_ids=set(),
            used_recipe_ids=set(),
            used_cuisines=[],
            exclude_families={'leco'},
        )
        self.assertEqual([c['id'] for c in payload['candidates']], [gulas.id])
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_replace.PrilohaAndFamilyOnSwapTest diet_planner.tests.test_recipe_refine.PreviewTurnTest diet_planner.tests.test_refine_agent -v 2`
Expected: the three new tests FAIL.

- [ ] **Step 3: Implement in `views.py`**

`_plan_swap_state` returns families of the target day too:

```python
def _plan_swap_state(plan, current_id, *, day_number=None):
    """Selection context for swapping one slot: (pool, used_recipe_ids,
    used_cuisines, used_families_today). ... `used_families_today` is the set
    of dish families served on `day_number` in OTHER slots, so a swap cannot
    bring lečo back onto a day that already has it."""
    used_recipe_ids: set = set()
    used_families_today: set = set()
    family_by_id = {r.id: (r.dish_family or '') for r in published_pool()}
    for d in (plan.days or []):
        same_day = day_number is not None and d.get('day_number') == day_number
        for slot in ('breakfast', 'lunch', 'dinner'):
            m = d.get(slot)
            if isinstance(m, dict) and m.get('curated_recipe_id'):
                used_recipe_ids.add(m['curated_recipe_id'])
                if same_day and m['curated_recipe_id'] != current_id:
                    fam = family_by_id.get(m['curated_recipe_id'])
                    if fam:
                        used_families_today.add(fam)
        for list_key in ('small_meals', 'snacks'):
            for m in (d.get(list_key) or []):
                if isinstance(m, dict) and m.get('curated_recipe_id'):
                    used_recipe_ids.add(m['curated_recipe_id'])
    used_recipe_ids.discard(current_id)
    pool = published_pool()
    cuisine_by_id = {r.id: (r.cuisine or '') for r in pool}
    used_cuisines = [cuisine_by_id[i] for i in used_recipe_ids if cuisine_by_id.get(i)]
    return pool, used_recipe_ids, used_cuisines, used_families_today
```

Every caller of `_plan_swap_state` (replace view, refine view) unpacks four values and passes `day_number=ctx.target_day.get('day_number')`, and every `eligible_recipes_for_slot(...)` inside `pick` gains `exclude_families=used_families_today`.

`_commit_slot_swap` — replace the two portioning lines with:

```python
        old = target_day.get(meal_type)
        old_cal = (old.get('nutritional_info') or {}).get('calories') if isinstance(old, dict) else None
        new_meal, _ = render_curated_meal(chosen, target_kcal=old_cal, required_tags=required_tags_for_goal(goal))
```

`_candidate_payload` — replace the `scale_recipe_to_meal(...)` call with:

```python
    meal, _ = render_curated_meal(recipe, target_kcal=target_calories, required_tags=required_tags)
```

and add `required_tags` as a keyword parameter (`required_tags=frozenset()` default). Both callers in `RecipeRefineView` (the agent branch at `views.py:~896` and the v1 facet branch below it) pass `required_tags=required_tags`, which that view already computes.

Import `render_curated_meal` next to the other `recipe_retrieval` imports at the top of `views.py`.

- [ ] **Step 4: Implement in `refine_agent.py`**

`_tool_search_corpus` gains `exclude_families: Set[str] = frozenset()` (keyword-only, after `time_budget`) and passes `exclude_families=exclude_families` to BOTH `eligible_recipes_for_slot` calls inside it. `run_refine_turn` gains the same keyword-only parameter `exclude_families: Set[str] = frozenset()` and forwards it in its `_tool_search_corpus(...)` call (`refine_agent.py:362`). In `views.py` `RecipeRefineView`, pass `exclude_families=used_families_today` into `run_refine_turn(...)` — `used_families_today` is the fourth value `_plan_swap_state` now returns.

- [ ] **Step 5: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_recipe_replace diet_planner.tests.test_recipe_refine diet_planner.tests.test_refine_agent diet_planner.tests.test_refine_chat diet_planner.tests.test_recipe_refine_agent -v 2`
Expected: OK.

- [ ] **Step 6: Commit**

```
git add diet_planner/views.py diet_planner/services/refine_agent.py diet_planner/tests/test_recipe_replace.py diet_planner/tests/test_recipe_refine.py diet_planner/tests/test_refine_agent.py
git commit -m "feat(swap): replace and refine attach the příloha and respect same-day dish families"
```

---

### Task 9: `dish_classification` service + overrides file

**Files:**
- Create: `diet_planner/services/dish_classification.py`
- Create: `diet_planner/data/dish_role_overrides.yaml`
- Modify: `diet_planner/llm_service.py` (add `classify_dishes`)
- Test: `diet_planner/tests/test_dish_classification.py` (new)

- [ ] **Step 1: Write the failing tests**

```python
# diet_planner/tests/test_dish_classification.py
"""Gemini dish classification: parsing, vocabulary validation, overrides."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase

from diet_planner.services import dish_classification as dc


def recipe(slug, name='X', **kw):
    base = dict(slug=slug, name_cs=name, description='', meal_types=['lunch'],
                ingredients=[{'name': 'sůl'}], base_servings=2,
                base_nutrition={'calories': 600}, cuisine='czech')
    base.update(kw)
    return SimpleNamespace(**base)


class ParseAnswerTest(TestCase):
    def test_parses_all_four_fields(self):
        raw = json.dumps([{'slug': 'leco', 'dish_role': 'supper', 'meal_types': ['dinner'],
                           'side_options': ['chleb'], 'dish_family': 'leco'}])
        out = dc.parse_answer(raw)
        c = out['leco']
        self.assertEqual((c.dish_role, c.meal_types, c.side_options, c.dish_family),
                         ('supper', ['dinner'], ['chleb'], 'leco'))
        self.assertEqual(c.problems, [])

    def test_unknown_values_are_dropped_and_reported(self):
        raw = json.dumps([{'slug': 'x', 'dish_role': 'banquet', 'meal_types': ['brunch', 'lunch'],
                           'side_options': ['sushi', 'ryze'], 'dish_family': 'Kuře Pečené'}])
        c = dc.parse_answer(raw)['x']
        self.assertEqual(c.dish_role, '')
        self.assertEqual(c.meal_types, ['lunch'])
        self.assertEqual(c.side_options, ['ryze'])
        self.assertEqual(c.dish_family, 'kure-pecene')
        self.assertTrue(any('banquet' in p for p in c.problems))

    def test_light_is_never_accepted_from_the_llm(self):
        c = dc.parse_answer(json.dumps([{'slug': 'x', 'dish_role': 'light'}]))['x']
        self.assertEqual(c.dish_role, '')

    def test_garbage_is_empty_dict(self):
        self.assertEqual(dc.parse_answer('not json'), {})
        self.assertEqual(dc.parse_answer('{"a": 1}'), {})


class ClassifyRecipesTest(TestCase):
    def test_batches_and_keys_by_slug(self):
        calls = []
        def gen(system, user):
            asked = [i['slug'] for i in json.loads(user)]
            calls.append(asked)
            return json.dumps([{'slug': s, 'dish_role': 'main', 'meal_types': ['lunch'],
                                'side_options': [], 'dish_family': s} for s in asked])
        recipes = [recipe(f'r{i}') for i in range(30)]
        out = dc.classify_recipes(recipes, generate=gen, batch_size=25)
        self.assertEqual(len(calls), 2)
        self.assertEqual(set(out), {r.slug for r in recipes})

    def test_failed_batch_is_skipped_not_raised(self):
        def gen(system, user):
            raise RuntimeError('boom')
        self.assertEqual(dc.classify_recipes([recipe('a')], generate=gen), {})


class OverridesTest(TestCase):
    OVR = {
        'by_slug': {'domaci-leco': {'dish_role': 'side', 'meal_types': ['small_meal'], 'side_options': []}},
        'by_family': {'leco': {'dish_role': 'supper', 'meal_types': ['dinner'], 'side_options': ['chleb']}},
    }

    def _c(self, **kw):
        base = dict(dish_role='main', meal_types=['lunch', 'dinner'], side_options=[], dish_family='leco')
        base.update(kw)
        return dc.Classification(**base)

    def test_family_override_applies(self):
        out = dc.apply_overrides('leco-s-klobasou', self._c(), overrides=self.OVR)
        self.assertEqual((out.dish_role, out.meal_types, out.side_options), ('supper', ['dinner'], ['chleb']))

    def test_slug_override_beats_family(self):
        out = dc.apply_overrides('domaci-leco', self._c(), overrides=self.OVR)
        self.assertEqual(out.dish_role, 'side')
        self.assertEqual(out.meal_types, ['small_meal'])

    def test_override_sets_only_named_fields(self):
        ovr = {'by_slug': {'x': {'dish_family': 'gulas'}}, 'by_family': {}}
        out = dc.apply_overrides('x', self._c(dish_family=''), overrides=ovr)
        self.assertEqual(out.dish_family, 'gulas')
        self.assertEqual(out.dish_role, 'main')

    def test_shipped_file_parses_and_pins_leco(self):
        ovr = dc.load_overrides()
        self.assertEqual(ovr['by_family']['leco']['dish_role'], 'supper')
        self.assertEqual(ovr['by_slug']['domaci-leco']['dish_role'], 'side')
        for section in ('by_slug', 'by_family'):
            for key, entry in ovr[section].items():
                self.assertRegex(key, r'^[a-z0-9-]+$')
                self.assertTrue(set(entry) <= {'dish_role', 'meal_types', 'side_options', 'dish_family', 'note'}, key)
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_dish_classification -v 2`
Expected: ImportError.

- [ ] **Step 3: Create the overrides file**

```yaml
# diet_planner/data/dish_role_overrides.yaml
# Owner-pinned dish classifications. Applied AFTER the LLM answer by
# services/dish_classification.apply_overrides, at intake and in
# `manage.py retag_dish_roles`. by_slug wins over by_family wins over the LLM.
# Each entry may set any of: dish_role, meal_types, side_options, dish_family.
# Keep a `note` with the reason and date; this file IS the review trail.
by_slug:
  domaci-leco:
    dish_role: side
    meal_types: [small_meal]
    side_options: []
    note: "2026-09-06 — preserving base (18 servings of lard/onion/pepper/tomato), not a meal"
by_family:
  leco:
    dish_role: supper
    meal_types: [dinner]
    side_options: [chleb]
    note: "2026-09-06 owner — lečo is a quick supper with bread; never oběd, never snídaně"
```

- [ ] **Step 4: Add `GeminiService.classify_dishes`**

In `diet_planner/llm_service.py`, after `match_canonical_ingredients_batch`:

```python
    def classify_dishes(self, system_prompt: str, user_text: str, model: Optional[str] = None) -> str:
        """JSON-mode classification call used by services.dish_classification.
        Returns the raw JSON text; the caller parses and validates."""
        gemini_model = genai.GenerativeModel(
            model_name=model or self.default_model,
            system_instruction=system_prompt,
        )
        response = gemini_model.generate_content(
            user_text,
            generation_config={"response_mime_type": "application/json", "temperature": 0.0},
            request_options={"timeout": 300},
        )
        return getattr(response, 'text', '') or ''
```

- [ ] **Step 5: Create the service**

```python
# diet_planner/services/dish_classification.py
"""
Classify a curated recipe by what it can CARRY in a Czech day, when it may
appear, what it is eaten with, and which dish family it belongs to.

One Gemini call per batch answers four fields per slug; a deterministic
validator drops anything outside the vocabularies; then
data/dish_role_overrides.yaml pins whatever the owner has decided. Used at
curation intake (every new recipe) and by `manage.py retag_dish_roles`
(backfill + review report). Spec: docs/superpowers/specs/2026-09-06-dish-roles-priloha-design.md.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import yaml
from django.utils.text import slugify

from diet_planner.models import CuratedRecipe
from diet_planner.services.canonical_lookup import fold_diacritics
from diet_planner.services.priloha import SIDE_KEYS

logger = logging.getLogger(__name__)

OVERRIDES_PATH = Path(__file__).resolve().parents[1] / 'data' / 'dish_role_overrides.yaml'

# 'light' is legacy: the LLM must choose breakfast or supper instead.
VALID_ROLES = {c.value for c in CuratedRecipe.DishRole} - {CuratedRecipe.DishRole.LIGHT.value}
VALID_MEAL_TYPES = {'breakfast', 'lunch', 'dinner', 'snack', 'small_meal'}
VALID_SIDES = set(SIDE_KEYS)
_FAMILY_RE = re.compile(r'^[a-z0-9-]{1,60}$')

SYSTEM_PROMPT = (
    "You classify recipes for a CZECH meal planner. For each recipe return four fields.\n"
    "\n"
    "dish_role — what the dish can CARRY:\n"
    "  main — a warm, substantial dish that carries a Czech oběd (and may carry večeře): "
    "svíčková, guláš, řízek, pečené kuře, rizoto, plněné papriky, omáčky s masem, "
    "hearty one-pot dishes like segedínský guláš, composed salads with a full protein portion.\n"
    "  supper — a quick dish Czechs eat as VEČEŘE, never as oběd: lečo, topinky, bramboráky, "
    "smažený sýr bez přílohy, chlebíčky, míchaná vejce k večeři, menemen/shakshuka, quesadilla.\n"
    "  breakfast — a SNÍDANĚ dish: kaše, ovesná kaše, vejce na snídani, toasty, palačinky, lívance, "
    "jogurt s granolou, smoothie bowl.\n"
    "  soup — a brothy or starter soup that accompanies a meal rather than carrying it: "
    "česnečka, kulajda, čočková polévka, hrachová polévka, vývar.\n"
    "  side — accompaniments and components: basic salads, dips, spreads, sauces, breads, plain "
    "grains or vegetables, AND preserving bases / batch components (e.g. a 'lečo' that is only "
    "peppers, onion, tomato and lard in 18 servings for jars).\n"
    "  dessert — sweet dishes and baked desserts.\n"
    "\n"
    "meal_types — WHEN the dish may appear, any of: breakfast, lunch, dinner, snack, small_meal. "
    "A supper dish lists dinner only. A main lists lunch and dinner. A breakfast dish lists breakfast "
    "(and small_meal if it also works as a light bite).\n"
    "\n"
    "side_options — for main and supper ONLY: the příloha a Czech household eats it with, as an "
    "ordered list from: chleb (bread), brambory (boiled potatoes), ryze (rice), knedlik (houskový "
    "knedlík), testoviny (pasta). Order by what is most usual for that dish. Empty list when the "
    "dish is complete on its own (rizoto, plněné papriky, pasta dishes, bowls, composed salads) or "
    "when the recipe already contains its starch. Examples: lečo → [chleb]; guláš → [knedlik, chleb]; "
    "svíčková → [knedlik]; řízek → [brambory]; kuře na paprice → [knedlik, testoviny]; "
    "rajská omáčka → [knedlik, testoviny]; pečené kuře → [brambory, ryze]. Other roles: [].\n"
    "\n"
    "dish_family — a short lowercase ASCII key naming the dish type so the planner never serves two "
    "of a family in one day: leco, gulas, svickova, rizek, rizoto, omacka-rajska, omacka-koprova, "
    "polevka-cockova, kure-pecene, kase-ovesna, palacinky. Variants share a key (Lečo, Lečo s klobásou, "
    "Domácí lečo → leco).\n"
    "\n"
    "Input is a JSON array of recipes. Answer ONLY with a JSON array of objects "
    '{"slug", "dish_role", "meal_types", "side_options", "dish_family"} covering every input slug. No prose.'
)


@dataclass
class Classification:
    dish_role: str = ''
    meal_types: List[str] = field(default_factory=list)
    side_options: List[str] = field(default_factory=list)
    dish_family: str = ''
    problems: List[str] = field(default_factory=list)


def _default_generate(system_prompt: str, user_text: str) -> str:
    from diet_planner.llm_service import GeminiService
    return GeminiService().classify_dishes(system_prompt, user_text)


# Patched in tests; the management command and curation may inject their own.
_generate: Callable[[str, str], str] = _default_generate


def describe(recipe: Any) -> Dict[str, Any]:
    return {
        'slug': recipe.slug or slugify(recipe.name_cs),
        'name': recipe.name_cs,
        'description': recipe.description or '',
        'cuisine': getattr(recipe, 'cuisine', '') or '',
        'meal_types': recipe.meal_types or [],
        'ingredients': [i.get('name') for i in (recipe.ingredients or []) if i.get('name')],
        'base_servings': recipe.base_servings,
        'calories_total': (recipe.base_nutrition or {}).get('calories'),
    }


def normalize_family(raw: Any) -> str:
    text = fold_diacritics(str(raw or '')).strip().lower()
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')[:60]
    return text if _FAMILY_RE.match(text or '') else ''


def _clean_list(values: Any, allowed: set, problems: List[str], label: str) -> List[str]:
    out: List[str] = []
    for v in (values if isinstance(values, list) else []):
        key = str(v).strip().lower()
        if key in allowed:
            if key not in out:
                out.append(key)
        else:
            problems.append(f'{label} {key!r} dropped')
    return out


def parse_answer(raw: str) -> Dict[str, Classification]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, list):
        return {}
    out: Dict[str, Classification] = {}
    for item in data:
        if not isinstance(item, dict) or not item.get('slug'):
            continue
        c = Classification()
        role = str(item.get('dish_role', '')).strip().lower()
        if role in VALID_ROLES:
            c.dish_role = role
        elif role:
            c.problems.append(f'dish_role {role!r} dropped')
        c.meal_types = _clean_list(item.get('meal_types'), VALID_MEAL_TYPES, c.problems, 'meal_type')
        c.side_options = _clean_list(item.get('side_options'), VALID_SIDES, c.problems, 'side')
        c.dish_family = normalize_family(item.get('dish_family'))
        out[str(item['slug'])] = c
    return out


def classify_recipes(
    recipes: Iterable[Any],
    *,
    generate: Optional[Callable[[str, str], str]] = None,
    batch_size: int = 25,
) -> Dict[str, Classification]:
    """LLM pass over `recipes`, keyed by slug (or slugified name for unsaved
    rows). A failed batch is logged and skipped — never raises."""
    gen = generate or _generate
    recipes = list(recipes)
    out: Dict[str, Classification] = {}
    for start in range(0, len(recipes), batch_size):
        batch = recipes[start:start + batch_size]
        payload = json.dumps([describe(r) for r in batch], ensure_ascii=False)
        try:
            out.update(parse_answer(gen(SYSTEM_PROMPT, payload)))
        except Exception as exc:  # noqa: BLE001
            logger.warning('dish_classification: batch at #%d failed: %r', start, exc)
    return out


def load_overrides(path: Path = OVERRIDES_PATH) -> Dict[str, Dict[str, Dict[str, Any]]]:
    with open(path, encoding='utf-8') as fh:
        data = yaml.safe_load(fh) or {}
    return {'by_slug': data.get('by_slug') or {}, 'by_family': data.get('by_family') or {}}


_FIELDS = ('dish_role', 'meal_types', 'side_options', 'dish_family')


def _merge(c: Classification, entry: Dict[str, Any]) -> None:
    for key in _FIELDS:
        if key in entry:
            setattr(c, key, entry[key] if key != 'dish_family' else normalize_family(entry[key]))


def apply_overrides(
    slug: str, classification: Classification, *, overrides: Optional[Dict] = None,
) -> Classification:
    """by_slug beats by_family beats the LLM. The family used for the by_family
    lookup is the slug override's, if it sets one, else the LLM's."""
    ovr = overrides if overrides is not None else load_overrides()
    c = Classification(**{k: getattr(classification, k) for k in _FIELDS}, problems=list(classification.problems))
    slug_entry = ovr['by_slug'].get(slug) or {}
    family = normalize_family(slug_entry.get('dish_family', c.dish_family))
    family_entry = ovr['by_family'].get(family) or {}
    _merge(c, family_entry)
    _merge(c, slug_entry)
    return c


def classify_and_override(
    recipes: Iterable[Any], *, generate: Optional[Callable[[str, str], str]] = None,
) -> Dict[str, Classification]:
    recipes = list(recipes)
    ovr = load_overrides()
    raw = classify_recipes(recipes, generate=generate)
    return {
        (r.slug or slugify(r.name_cs)): apply_overrides(r.slug or slugify(r.name_cs), raw[r.slug or slugify(r.name_cs)], overrides=ovr)
        for r in recipes if (r.slug or slugify(r.name_cs)) in raw
    }
```

- [ ] **Step 6: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_dish_classification -v 2`
Expected: OK (11 tests).

- [ ] **Step 7: Commit**

```
git add diet_planner/services/dish_classification.py diet_planner/data/dish_role_overrides.yaml diet_planner/llm_service.py diet_planner/tests/test_dish_classification.py
git commit -m "feat(corpus): dish classification service with owner override file"
```

---

### Task 10: `retag_dish_roles` — service-backed, `--force`, dry-run review report

**Files:**
- Rewrite: `diet_planner/management/commands/retag_dish_roles.py`
- Rewrite: `diet_planner/tests/test_retag_dish_roles.py`

- [ ] **Step 1: Rewrite the tests**

Replace `diet_planner/tests/test_retag_dish_roles.py` with:

```python
"""retag_dish_roles: backfill of dish_role/meal_types/side_options/dish_family
with a dry-run review report the owner reads before anything is written."""
import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def make_recipe(name_cs, **kw):
    defaults = dict(
        name_cs=name_cs,
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=['lunch', 'dinner'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[{'name': 'rýže', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'}],
        instructions=[{'text': 'Uvař.'}],
        base_servings=2,
        base_nutrition={'calories': 600},
        source_url='https://example.test/r',
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


def fake_generate_for(mapping):
    """{slug: {dish_role, meal_types, side_options, dish_family}} → generate stub."""
    def _gen(system_prompt, user_text):
        asked = [item['slug'] for item in json.loads(user_text)]
        return json.dumps([{'slug': s, **mapping[s]} for s in asked if s in mapping])
    return _gen


def full(role, meal_types=None, sides=None, family=''):
    return {'dish_role': role, 'meal_types': meal_types or ['lunch', 'dinner'],
            'side_options': sides or [], 'dish_family': family}


class RetagDishRolesTest(TestCase):
    def _run(self, mapping, *args):
        out = StringIO()
        with patch('diet_planner.services.dish_classification._generate',
                   side_effect=fake_generate_for(mapping)):
            call_command('retag_dish_roles', *args, stdout=out)
        return out.getvalue()

    def test_tags_untagged_recipes_with_all_fields(self):
        r = make_recipe('Lečo s klobásou')
        self._run({r.slug: full('supper', ['dinner'], ['chleb'], 'leco')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'supper')
        self.assertEqual(r.meal_types, ['dinner'])
        self.assertEqual(r.side_options, ['chleb'])
        self.assertEqual(r.dish_family, 'leco')

    def test_dry_run_writes_nothing_and_reports_change(self):
        r = make_recipe('Guláš')
        out = self._run({r.slug: full('main', sides=['knedlik'], family='gulas')}, '--dry-run')
        r.refresh_from_db()
        self.assertEqual(r.dish_role, '')
        self.assertIn('(empty) -> main', out)
        self.assertIn('knedlik', out)

    def test_already_tagged_skipped_without_force(self):
        r = make_recipe('Omeleta', dish_role=CuratedRecipe.DishRole.LIGHT)
        self._run({r.slug: full('breakfast')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'light')

    def test_force_retags_light_rows(self):
        r = make_recipe('Omeleta 2', dish_role=CuratedRecipe.DishRole.LIGHT)
        self._run({r.slug: full('breakfast', ['breakfast'])}, '--force')
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'breakfast')

    def test_invalid_role_from_llm_is_not_written(self):
        r = make_recipe('Podivné jídlo')
        out = self._run({r.slug: full('banquet')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, '')
        self.assertIn('banquet', out)

    def test_overrides_win_over_llm(self):
        r = make_recipe('Lečo')
        self._run({r.slug: full('main', ['lunch', 'dinner'], [], 'leco')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'supper')      # by_family: leco
        self.assertEqual(r.meal_types, ['dinner'])
        self.assertEqual(r.side_options, ['chleb'])

    def test_report_has_histogram_and_lunch_pool_warning(self):
        mains = [make_recipe(f'Jídlo {i}', dish_role='main') for i in range(3)]
        mapping = {m.slug: full('supper', ['dinner'], [], f'f{i}') for i, m in enumerate(mains)}
        out = self._run(mapping, '--force', '--dry-run')
        self.assertIn('Role histogram', out)
        self.assertIn('before: main 3', out)
        self.assertIn('after:', out)
        self.assertIn('Lunch pool', out)
        self.assertIn('WARNING', out)  # 0 < 15

    def test_drafts_are_tagged_too(self):
        r = make_recipe('Koncept', status=CuratedRecipe.Status.DRAFT)
        self._run({r.slug: full('main')})
        r.refresh_from_db()
        self.assertEqual(r.dish_role, 'main')
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_retag_dish_roles -v 2`
Expected: FAIL (old command ignores new fields; no report).

- [ ] **Step 3: Rewrite the command**

```python
# diet_planner/management/commands/retag_dish_roles.py
"""
Backfill CuratedRecipe.dish_role / meal_types / side_options / dish_family via
services.dish_classification, with a dry-run REVIEW REPORT the owner reads
before anything is written.

`meal_types` says WHEN a dish may appear; `dish_role` says whether it can BE
the meal (a Czech oběd is a warm main; lečo is a supper — see
recipe_retrieval._SLOT_ALLOWED_ROLES). `side_options` is the příloha it is
eaten with; `dish_family` is the dedupe key.

Prod usage (via prod_run.py or the DO console):
  python manage.py retag_dish_roles --force --dry-run   # review report
  python manage.py retag_dish_roles --force             # write
Runbook: docs/dish-roles-ops.md
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services.dish_classification import Classification, classify_and_override
from diet_planner.services.recipe_retrieval import eligible_recipes_for_slot

LUNCH_POOL_MIN = 15
LUNCH_TAG_SETS = (
    ('none', set()), ('vegetarian', {'vegetarian'}), ('vegan', {'vegan'}),
    ('gluten_free', {'gluten_free'}), ('dairy_free', {'dairy_free'}),
)


class Command(BaseCommand):
    help = "Classify CuratedRecipe dish_role/meal_types/side_options/dish_family via LLM + overrides."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report, write nothing.')
        parser.add_argument('--force', action='store_true',
                            help='Re-tag every recipe, including light/already-tagged rows.')
        parser.add_argument('--batch-size', type=int, default=25)

    def handle(self, *args, **opts):
        qs = CuratedRecipe.objects.order_by('id')
        if not opts['force']:
            qs = qs.filter(dish_role='')
        recipes: List[CuratedRecipe] = list(qs)
        if not recipes:
            self.stdout.write('Nothing to tag.')
            return

        # classify_and_override batches internally; batch_size is honoured via
        # a thin wrapper so the flag still means something.
        from diet_planner.services import dish_classification as dc
        answers: Dict[str, Classification] = {}
        for start in range(0, len(recipes), opts['batch_size']):
            answers.update(dc.classify_and_override(recipes[start:start + opts['batch_size']]))

        published = list(CuratedRecipe.objects.filter(status=CuratedRecipe.Status.PUBLISHED))
        before_hist = Counter(r.dish_role or '(empty)' for r in published)
        before_pool = self._lunch_pool(published)

        changes = defaultdict(list)   # cuisine -> lines
        written = skipped = 0
        proposed: Dict[int, Classification] = {}
        for r in recipes:
            c = answers.get(r.slug)
            if c is None or not c.dish_role:
                self.stdout.write(f'SKIP {r.slug}: unusable role '
                                  f'{(c.problems if c else ["no answer"])!r}')
                skipped += 1
                continue
            for p in c.problems:
                self.stdout.write(f'  note {r.slug}: {p}')
            old_role = r.dish_role or '(empty)'
            old_mt = list(r.meal_types or [])
            line = (f'{r.slug} | {r.name_cs} | {old_role} -> {c.dish_role} | '
                    f'meal_types {old_mt} -> {c.meal_types} | sides {c.side_options} | family {c.dish_family}')
            if old_role != c.dish_role or old_mt != c.meal_types:
                changes[r.cuisine or '(none)'].append(line)
            self.stdout.write(line)
            proposed[r.id] = c
            written += 1

        # Simulate the outcome in memory for the histogram + pool report.
        for r in published:
            c = proposed.get(r.id)
            if c:
                r.dish_role, r.meal_types = c.dish_role, c.meal_types
        after_hist = Counter(r.dish_role or '(empty)' for r in published)
        after_pool = self._lunch_pool(published)

        self.stdout.write('\n== Changes (role or meal_types), Czech first ==')
        for cuisine in sorted(changes, key=lambda k: (k != 'czech', k)):
            self.stdout.write(f'[{cuisine}]')
            for line in changes[cuisine]:
                self.stdout.write('  ' + line)
        self.stdout.write('\n== Role histogram (published) ==')
        self.stdout.write('  before: ' + ', '.join(f'{k} {v}' for k, v in before_hist.most_common()))
        self.stdout.write('  after:  ' + ', '.join(f'{k} {v}' for k, v in after_hist.most_common()))
        self.stdout.write('\n== Lunch pool (published, role main, lunch in meal_types, catalog-mapped) ==')
        for label, _ in LUNCH_TAG_SETS:
            b, a = before_pool[label], after_pool[label]
            warn = '  WARNING: below %d' % LUNCH_POOL_MIN if a < LUNCH_POOL_MIN else ''
            self.stdout.write(f'  {label}: {b} -> {a}{warn}')

        if not opts['dry_run']:
            for r in recipes:
                c = proposed.get(r.id)
                if not c:
                    continue
                r.dish_role, r.meal_types = c.dish_role, c.meal_types
                r.side_options, r.dish_family = c.side_options, c.dish_family
                r.save(update_fields=['dish_role', 'meal_types', 'side_options', 'dish_family'])

        verb = 'Would write' if opts['dry_run'] else 'Wrote'
        self.stdout.write(self.style.SUCCESS(
            f'\n{verb} {written} recipe(s), skipped {skipped}, of {len(recipes)} candidate(s).'
        ))

    @staticmethod
    def _lunch_pool(pool: List[CuratedRecipe]) -> Dict[str, int]:
        return {
            label: len(eligible_recipes_for_slot('lunch', tags, pool=pool))
            for label, tags in LUNCH_TAG_SETS
        }
```

- [ ] **Step 4: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_retag_dish_roles diet_planner.tests.test_dish_classification -v 2`
Expected: OK (8 + 11).

- [ ] **Step 5: Commit**

```
git add diet_planner/management/commands/retag_dish_roles.py diet_planner/tests/test_retag_dish_roles.py
git commit -m "feat(corpus): retag_dish_roles tags four fields, --force, dry-run review report"
```

---

### Task 11: Curation intake classifies new recipes

**Files:**
- Modify: `diet_planner/services/recipe_curation.py:415-437` (after `recipe = CuratedRecipe(**fields)`)
- Test: `diet_planner/tests/test_curation_dish_classification.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# diet_planner/tests/test_curation_dish_classification.py
"""A newly curated recipe leaves intake with dish_role/meal_types/side_options/
dish_family set, so the corpus never drifts back to untagged."""
import json
from unittest.mock import patch

from django.test import TestCase

from diet_planner.models import Availability, CuratedRecipe
from diet_planner.services import recipe_curation
from diet_planner.tests.factories import make_canonical

_CURATED = {
    "name_cs": "Lečo s klobásou",
    "name_en": "Lecho with sausage",
    "description": "Rychlá večeře.",
    "meal_types": ["lunch", "dinner"],
    "cuisine": "czech",
    "difficulty": "easy",
    "dietary_tags": [],
    "ingredients": [{"name": "sůl", "quantity": 5, "unit": "g"}],
    "instructions": [{"text": "Osmahni cibuli, přidej papriky a rajčata, vejce, podávej s chlebem."}],
    "base_servings": 2,
    "base_nutrition": {"calories": 900},
    "prep_time": 10,
    "cook_time": 20,
}


class CurationClassifiesTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)

    def _run(self, answer):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = _CURATED
            gem.return_value.classify_dishes.return_value = answer
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/leco", "source_name": "Example"},
                run_judge=False, enforce_plausibility=False,
            )

    def test_new_recipe_is_tagged_and_overridden(self):
        # LLM says main; the shipped by_family override for 'leco' pins supper/dinner/chleb.
        answer = json.dumps([{'slug': 'leco-s-klobasou', 'dish_role': 'main',
                              'meal_types': ['lunch', 'dinner'], 'side_options': [],
                              'dish_family': 'leco'}])
        result = self._run(answer)
        self.assertTrue(result.ok, result.error)
        r = CuratedRecipe.objects.get()
        self.assertEqual(r.dish_role, 'supper')
        self.assertEqual(r.meal_types, ['dinner'])
        self.assertEqual(r.side_options, ['chleb'])
        self.assertEqual(r.dish_family, 'leco')

    def test_classifier_failure_leaves_recipe_untagged_but_saved(self):
        result = self._run('not json')
        self.assertTrue(result.ok, result.error)
        r = CuratedRecipe.objects.get()
        self.assertEqual(r.dish_role, '')
        self.assertEqual(r.meal_types, ['lunch', 'dinner'])  # curation's own value kept
```

- [ ] **Step 2: Run to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_curation_dish_classification -v 2`
Expected: first test FAIL (`dish_role == ''`).

- [ ] **Step 3: Hook classification into intake**

In `recipe_curation.py`, after `recipe.shopping_difficulty, recipe.shopping_blockers = compute_shopping_difficulty(recipe)`:

```python
    # Slot-fit tags at intake (spec 2026-09-06): role, when, příloha, family.
    # Fail-open — an untagged recipe still passes every gate as today; the
    # backfill command catches it later.
    try:
        from diet_planner.services.dish_classification import classify_and_override
        key = recipe.slug or slugify(recipe.name_cs)
        tagged = classify_and_override([recipe], generate=gemini.classify_dishes).get(key)
        if tagged and tagged.dish_role:
            recipe.dish_role = tagged.dish_role
            recipe.side_options = tagged.side_options
            recipe.dish_family = tagged.dish_family
            if tagged.meal_types:
                recipe.meal_types = tagged.meal_types
    except Exception as exc:  # noqa: BLE001
        logger.warning("recipe_curation: dish classification failed for %s: %s", url, exc)
```

`gemini` is already bound earlier in `curate_from_source` (`gemini = gemini or GeminiService()`, ~line 370), so replace `svc = gemini or GeminiService()` with plain `gemini`. Add `from django.utils.text import slugify` to the imports.

- [ ] **Step 4: Run the tests, including the other curation gates**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_curation_dish_classification diet_planner.tests.test_curation_availability_gate diet_planner.tests.test_curation_plausibility_gate diet_planner.tests.test_curation_nutrition_basis -v 2`
Expected: OK. The older gate tests leave `classify_dishes` as a MagicMock, which `json.loads` rejects — the hook fails open, which is the second test's contract.

- [ ] **Step 5: Commit**

```
git add diet_planner/services/recipe_curation.py diet_planner/tests/test_curation_dish_classification.py
git commit -m "feat(curation): classify dish role, meal types, příloha and family at intake"
```

---

### Task 12: Frontend — "Příloha" group and "s chlebem" line

**Files:**
- Modify: `frontend/src/lib/portions.ts:22-27` (`IngredientInput`)
- Modify: `frontend/src/components/recipe/RecipeIngredients.tsx`
- Create: `frontend/src/components/recipe/MealSideLine.tsx`
- Create: `frontend/src/components/recipe/MealSideLine.test.tsx`
- Modify: `frontend/src/components/recipe/RecipeIngredients.test.tsx`
- Modify: `frontend/src/pages/PlanView.tsx:287` (after the `<h3>` dish name)

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/components/recipe/RecipeIngredients.test.tsx`:

```tsx
describe('RecipeIngredients — příloha group', () => {
  it('renders role=side rows under a Příloha heading, scaled with the stepper', () => {
    render(
      <RecipeIngredients
        ingredients={[
          { name: 'Paprika', quantity: 400, unit: 'g' },
          { name: 'chléb', quantity: 160, unit: 'g', role: 'side' },
        ]}
        baseServings={2}
      />,
    );
    expect(screen.getByText('Příloha')).toBeInTheDocument();
    expect(screen.getByText('chléb')).toBeInTheDocument();
    expect(screen.getByText('160 g')).toBeInTheDocument();
  });

  it('shows no Příloha heading without side rows', () => {
    render(<RecipeIngredients ingredients={[{ name: 'Paprika', quantity: 400, unit: 'g' }]} baseServings={2} />);
    expect(screen.queryByText('Příloha')).toBeNull();
  });

  it('keeps price lines aligned when a side row is present', () => {
    const shoppingList: ShoppingList = {
      lines: [
        { name: 'Paprika', canonical: 'bell-pepper', consumed_cost: 30, priced: true, verified: true },
        { name: 'chléb', canonical: 'bread-loaf', consumed_cost: 7, priced: true, verified: true },
      ],
      total_low: 37, total_high: 46, per_portion_low: 18.5, per_portion_high: 23,
      priced_count: 2, total_count: 2, verified_count: 2, currency: 'CZK', confident: true,
    };
    render(
      <RecipeIngredients
        ingredients={[
          { name: 'Paprika', quantity: 400, unit: 'g' },
          { name: 'chléb', quantity: 160, unit: 'g', role: 'side' },
        ]}
        baseServings={2}
        shoppingList={shoppingList}
      />,
    );
    expect(screen.getByText(/~7\s?Kč/)).toBeInTheDocument();
  });
});
```

Check how the existing tests in that file assert the scaled amount label (e.g. `'160 g'` vs `'160 g'` with a non-breaking space) and copy their matcher.

Create `frontend/src/components/recipe/MealSideLine.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MealSideLine } from './MealSideLine';

describe('MealSideLine', () => {
  it('renders "s chlebem · 2 krajíce"', () => {
    render(<MealSideLine side={{ key: 'chleb', name_cs: 'chléb', with_cs: 's chlebem', display: '2 krajíce' }} />);
    expect(screen.getByText(/s chlebem/)).toBeInTheDocument();
    expect(screen.getByText(/2 krajíce/)).toBeInTheDocument();
  });

  it('renders nothing without a side', () => {
    const { container } = render(<MealSideLine side={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd /opt/llmDietPlanner/frontend` then `npx vitest run src/components/recipe`
Expected: FAIL (no `MealSideLine`, no Příloha heading).

- [ ] **Step 3: Type + components**

`frontend/src/lib/portions.ts`:

```ts
export interface IngredientInput {
  name: string;
  quantity: number | string | null;
  unit?: string | null;
  optional?: boolean;
  /** 'side' = the příloha the planner attached (rendered in its own group). */
  role?: 'side' | null;
}
```

`frontend/src/components/recipe/MealSideLine.tsx`:

```tsx
export interface MealSide {
  key: string;
  name_cs: string;
  with_cs: string;
  display: string;
}

/** "s chlebem · 2 krajíce" under a plan-card dish name. Copy comes from the
 * backend příloha table (services/priloha.py), already in the right case. */
export const MealSideLine = ({ side }: { side: MealSide | null | undefined }) => {
  if (!side) return null;
  return (
    <p className="text-sm font-bold text-muted italic tracking-wide mb-4 relative z-10">
      {side.with_cs} · {side.display}
    </p>
  );
};
```

`RecipeIngredients.tsx` — replace the entry partition and the running price index:

```tsx
  const entries = list.map((ing, idx) => ({ ing, idx }));
  const isSide = (e: { ing: IngredientInput | string }) => typeof e.ing !== 'string' && e.ing.role === 'side';
  const isOptional = (e: { ing: IngredientInput | string }) => typeof e.ing !== 'string' && !!e.ing.optional;
  const requiredEntries = entries.filter((e) => !isOptional(e) && !isSide(e));
  const sideEntries = entries.filter((e) => !isOptional(e) && isSide(e));
  const optionalEntries = entries.filter(isOptional);

  // price_recipe_lines skips optional ingredients; map each non-optional row
  // (in ORIGINAL order) to its shopping-list line so regrouping cannot
  // misalign prices.
  const priceIndexByIdx = new Map<number, number>();
  let running = 0;
  entries.forEach((e) => {
    if (!isOptional(e)) priceIndexByIdx.set(e.idx, running++);
  });
```

In `renderRow`, replace the `priceIdx` block with:

```tsx
    let line = undefined as ShoppingList['lines'][number] | undefined;
    if (!isOptional) {
      const pi = priceIndexByIdx.get(idx);
      line = pi === undefined ? undefined : shoppingList?.lines[pi];
    }
```

(and delete `let priceIdx = -1;`). After the required `<ul>` add:

```tsx
      {sideEntries.length > 0 && (
        <>
          <h3 className={`${eyebrowCls} block mt-6 mb-3`}>Příloha</h3>
          <ul className="space-y-2.5">
            {sideEntries.map(renderRow)}
          </ul>
        </>
      )}
```

`PlanView.tsx` — import `MealSideLine` and insert directly after the `<h3 …>{day[m].name}</h3>` line:

```tsx
                          <MealSideLine side={day[m].side} />
```

- [ ] **Step 4: Run tests and types**

Run: `npx vitest run src/components/recipe`
Expected: OK.
Run: `npx tsc --noEmit`
Expected: no errors. If `day[m].side` is untyped (`any`), no change is needed; if `day` has an explicit meal type, add `side?: MealSide | null` to it.

- [ ] **Step 5: Commit**

```
git add frontend/src/lib/portions.ts frontend/src/components/recipe/RecipeIngredients.tsx frontend/src/components/recipe/RecipeIngredients.test.tsx frontend/src/components/recipe/MealSideLine.tsx frontend/src/components/recipe/MealSideLine.test.tsx frontend/src/pages/PlanView.tsx
git commit -m "feat(web): Příloha group on the recipe page, 's chlebem' line on the plan card"
```

---

### Task 13: Runbook + full test run + PR

**Files:**
- Create: `docs/dish-roles-ops.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Dish roles, příloha and dish families — prod runbook

Spec: `docs/superpowers/specs/2026-09-06-dish-roles-priloha-design.md`.

## What the tag pass writes
`dish_role` (main/supper/breakfast/soup/side/dessert), `meal_types`,
`side_options` (chleb/brambory/ryze/knedlik/testoviny), `dish_family`.
`light` is legacy and must reach zero.

## Order of operations
1. Deploy the code (migration 0038). Untagged and `light` rows behave as before.
2. Dry run on prod:
   `python manage.py retag_dish_roles --force --dry-run > /tmp/retag-report.txt`
   (~460 recipes / 25 per batch ≈ 19 Gemini calls, 2–3 minutes.)
3. Read the report: the "Changes" block (Czech first), the role histogram, and
   the lunch-pool block. Any lunch pool under 15 prints WARNING.
4. Disagree with a line? Add it to `diet_planner/data/dish_role_overrides.yaml`
   (`by_slug` for one recipe, `by_family` for a whole family), commit, deploy,
   repeat step 2 until the report reads right.
5. Write: `python manage.py retag_dish_roles --force`.
6. Probe (read-only): count of `dish_role='light'` must be 0; `domaci-leco`
   must be `side`; every `leco` family row must be `supper` + `[dinner]` +
   `[chleb]`.
7. Generate a QA plan asking for Czech classics; check lečo only at dinner
   with bread, never twice a day; svíčková with knedlík; the shopping list and
   deals headline include the side. Then `/qa-prod`.

## Gotchas
- `prod_run.py`'s idle drain (12 s) is shorter than a Gemini batch; use
  drain(timeout=90, total=600) or run in the DO console.
- New recipes are classified at curation; the command is only a backfill.
- The judge/Anthropic balance does not matter here — classification is Gemini.
```

- [ ] **Step 2: Run the full backend suite**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner billing analytics social 2>&1 | grep -E "^(OK|FAILED|Ran )"`
Expected: `Ran 9xx tests` … `OK`. (~6 minutes; pass `timeout: 600000` to Bash.)

- [ ] **Step 3: Run the frontend suite and types**

Run: `cd /opt/llmDietPlanner/frontend` then `npx vitest run` then `npx tsc --noEmit`
Expected: all green.

- [ ] **Step 4: Commit and open the PR**

```
git add docs/dish-roles-ops.md
git commit -m "docs: prod runbook for the dish-role tag pass"
git push -u origin feat/dish-roles-priloha
gh pr create --base develop --title "feat(planner): dish roles, příloha line and dish-family dedupe" --body-file /tmp/claude-0/-opt-llmDietPlanner/a482f190-9504-43bf-b53f-5a8cb6e97ebd/scratchpad/pr-body.md
```

PR body (write it to the scratchpad file first): the problem paragraph and the goals list from the spec, the "Order of operations" from the runbook, and the standard footer:

```
🤖 Generated with [Claude Code](https://claude.com/claude-code)

https://claude.ai/code/session_01SLKzDZptfyBGpbeKu7DND8
```

Then watch CI: `gh pr checks <n>` in a `for i in $(seq 1 20); do gh pr checks <n>; sleep 25; done` loop with a long Bash timeout.

- [ ] **Step 5: After merge — prod steps are the owner's call**

The tag pass (runbook steps 2–7) runs after deploy and is gated by the owner's review of the report. Update memory `mains-without-priloha-gap` with the outcome.

---

## Self-review against the spec

- §1 vocabulary, fields, slot table, kcal floors → Tasks 1, 2.
- §2 tag pass: service, prompt with Czech examples, overrides (by_slug/by_family), validation, `--force`, review report with histogram + lunch pools + WARNING <15, curation intake → Tasks 9, 10, 11.
- §3 příloha table, `bread-dumpling` canonical, `pick_side`, `side_unavailable` gap → Tasks 3, 4, 5, 6.
- §4 meal shape (`role: 'side'`, totals, `side` object, `portions_for_target(side=)`) → Task 5.
- §5 dedupe (same-day exclusion, plan penalty capped at 16, `family_relaxed`, swap paths) → Tasks 7, 8.
- §6 one helper for all write paths incl. preview → Tasks 5, 8.
- §7 frontend → Task 12.
- §8 rollout → Task 13 + runbook.
- Testing section: every bullet has a test in the task that builds it.

Type consistency: `render_curated_meal(recipe, *, target_kcal, required_tags) -> (meal, gap)` is used identically in Tasks 5, 6, 8. `Classification` fields `dish_role/meal_types/side_options/dish_family/problems` match between Tasks 9, 10, 11. `Side` fields match between Tasks 4, 5, 12 (`with_cs`, `display`).
