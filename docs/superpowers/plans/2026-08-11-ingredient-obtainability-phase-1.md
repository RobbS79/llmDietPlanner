# Ingredient Obtainability — Phase 1 (Rate, Measure, Gate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rate every canonical ingredient's Czech-supermarket obtainability, roll it up to each curated recipe, measure how much of the corpus is affected, and stop new unshoppable recipes from entering — without mutating a single existing recipe.

**Architecture:** A three-tier `availability` rating lands on `CanonicalIngredient`, seeded from a git-tracked YAML that is itself generated from the owner-reviewed CSV. A pure function rolls the worst non-optional ingredient up into `CuratedRecipe.shopping_difficulty` plus a `shopping_blockers` list. A read-only report slices the result by meal_type × dietary_tag. Finally an intake gate rejects new `specialty`/`unrated` recipes at curation time, behind a flag that ships off.

**Tech Stack:** Django 5.1, PostgreSQL (Supabase) in prod / SQLite locally, `django.test.TestCase`, pytest runner, PyYAML, management commands.

**Scope boundary:** This plan stops at the spec's decision gate. It creates no substitutions, unpublishes nothing, and changes no ranking. See `docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md` §"Decision gate".

---

## File Structure

**Created:**
- `diet_planner/services/ingredient_availability.py` — the pure rollup + gate logic. Single source of truth; commands and the curation gate all call it.
- `diet_planner/data/ingredient_availability.yaml` — generated rating seed (slug → tier/note/confidence).
- `diet_planner/management/commands/import_availability_review.py` — CSV → YAML (one-way, re-runnable as the owner fills in more rows).
- `diet_planner/management/commands/rate_ingredient_availability.py` — YAML → DB.
- `diet_planner/management/commands/recompute_shopping_difficulty.py` — rollup over the corpus.
- `diet_planner/management/commands/report_shopping_difficulty.py` — read-only measurement.
- `diet_planner/migrations/0035_ingredient_availability.py`
- `diet_planner/migrations/0036_curatedrecipe_shopping_difficulty.py`
- `diet_planner/tests/test_ingredient_availability.py`
- `diet_planner/tests/test_rate_ingredient_availability.py`
- `diet_planner/tests/test_curation_availability_gate.py`

**Modified:**
- `diet_planner/models/catalog.py` — module-level `Availability` choices + two fields.
- `diet_planner/models/curated.py` — four fields.
- `diet_planner/models/__init__.py` — export `Availability`.
- `diet_planner/services/recipe_curation.py` — `enforce_availability` gate + rollup on save.
- `diet_planner/services/recipe_research.py` — explicitly opt out of the gate (see Task 8).
- `llm_diet_planner_project/settings.py` — `AVAILABILITY_GATE_ENABLED`.

---

### Task 1: Availability choices + CanonicalIngredient fields

**Files:**
- Modify: `diet_planner/models/catalog.py`
- Modify: `diet_planner/models/__init__.py`
- Create: `diet_planner/migrations/0035_ingredient_availability.py`
- Test: `diet_planner/tests/test_ingredient_availability.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_ingredient_availability.py`:

```python
"""Availability rating: model defaults and the pure rollup."""
from django.test import TestCase

from diet_planner.models import Availability, CanonicalIngredient


class AvailabilityFieldTest(TestCase):
    def test_new_canonical_defaults_to_unrated(self):
        ci = CanonicalIngredient.objects.create(
            name='tahini', name_cs='tahini', slug='tahini',
        )
        self.assertEqual(ci.availability, Availability.UNRATED)
        self.assertEqual(ci.availability_note, '')

    def test_availability_note_is_optional_free_text(self):
        ci = CanonicalIngredient.objects.create(
            name='kale', name_cs='kadeřávek', slug='kale',
            availability=Availability.FINDABLE,
            availability_note='velké Albert/Kaufland sezónně',
        )
        ci.refresh_from_db()
        self.assertEqual(ci.availability, 'findable')
        self.assertEqual(ci.availability_note, 'velké Albert/Kaufland sezónně')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability -v 2`
Expected: FAIL with `ImportError: cannot import name 'Availability' from 'diet_planner.models'`

- [ ] **Step 3: Add the choices class and fields**

In `diet_planner/models/catalog.py`, add at **module level** (above `class CanonicalIngredient`, not nested inside it — `curated.py` imports it and nesting would force a circular-ish import through the model class):

```python
class Availability(models.TextChoices):
    """How obtainable an ingredient is in an ordinary Czech supermarket.

    The bar for COMMON is "any Albert / Billa / Kaufland / Tesco / Lidl —
    one stop, no planning".

    UNRATED is deliberately asymmetric: it RANKS as FINDABLE (a mild penalty,
    so a migration cannot collapse the corpus) but BLOCKS at intake (so a
    newly-encountered unknown ingredient forces a human decision instead of
    leaking forever). See the spec's asymmetry table.
    """
    COMMON = 'common', 'Common — any supermarket'
    FINDABLE = 'findable', 'Findable — large store or Rohlík only'
    SPECIALTY = 'specialty', 'Specialty — asian/bio shop or online only'
    UNRATED = 'unrated', 'Unrated'
```

Then inside `class CanonicalIngredient`, directly after the `is_pantry_staple` field:

```python
    availability = models.CharField(
        max_length=10,
        choices=Availability.choices,
        default=Availability.UNRATED,
        db_index=True,
        help_text="Obtainability in an ordinary Czech supermarket",
    )
    availability_note = models.CharField(
        max_length=200,
        blank=True,
        help_text='Why this rating, e.g. "Albert ano, Lidl ne"',
    )
```

In `diet_planner/models/__init__.py`, add `Availability` to the import from `.catalog` (alongside `CanonicalIngredient`) and to `__all__` if the file defines one.

- [ ] **Step 4: Generate the migration**

Run: `python manage.py makemigrations diet_planner --name ingredient_availability`
Expected: `Migrations for 'diet_planner': 0035_ingredient_availability.py - Add field availability to canonicalingredient - Add field availability_note to canonicalingredient`

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability -v 2`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add diet_planner/models/catalog.py diet_planner/models/__init__.py \
        diet_planner/migrations/0035_ingredient_availability.py \
        diet_planner/tests/test_ingredient_availability.py
git commit -m "feat(catalog): add three-tier availability rating to CanonicalIngredient"
```

---

### Task 2: CuratedRecipe rollup fields

**Files:**
- Modify: `diet_planner/models/curated.py`
- Create: `diet_planner/migrations/0036_curatedrecipe_shopping_difficulty.py`
- Test: `diet_planner/tests/test_ingredient_availability.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_ingredient_availability.py`:

```python
from diet_planner.models import CuratedRecipe


class ShoppingDifficultyFieldTest(TestCase):
    def _recipe(self, **kw):
        defaults = dict(
            slug='test-dish', name_cs='Testovací jídlo',
            source_url='https://example.test/x', source_name='Example',
        )
        defaults.update(kw)
        return CuratedRecipe.objects.create(**defaults)

    def test_defaults_mean_not_yet_computed(self):
        r = self._recipe()
        self.assertEqual(r.shopping_difficulty, Availability.UNRATED)
        self.assertEqual(r.shopping_blockers, [])
        self.assertEqual(r.adaptation_note, '')
        self.assertIsNone(r.original_ingredients)

    def test_fields_round_trip(self):
        r = self._recipe(
            slug='test-dish-2',
            shopping_difficulty=Availability.SPECIALTY,
            shopping_blockers=['tahini', 'sumac'],
            adaptation_note='Upraveno pro dostupnost v českých obchodech',
            original_ingredients=[{'name': 'tahini', 'quantity': 30, 'unit': 'g'}],
        )
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, 'specialty')
        self.assertEqual(r.shopping_blockers, ['tahini', 'sumac'])
        self.assertEqual(r.original_ingredients[0]['name'], 'tahini')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability.ShoppingDifficultyFieldTest -v 2`
Expected: FAIL with `TypeError: CuratedRecipe() got unexpected keyword arguments: 'shopping_difficulty'`

- [ ] **Step 3: Add the fields**

In `diet_planner/models/curated.py`, add the import at the top:

```python
from diet_planner.models.catalog import Availability
```

Inside `class CuratedRecipe`, in the `--- Lifecycle / quality ---` block directly after `quality_score`:

```python
    shopping_difficulty = models.CharField(
        max_length=10,
        choices=Availability.choices,
        default=Availability.UNRATED,
        db_index=True,
        help_text=(
            "Worst non-optional ingredient's availability. Denormalised — "
            "recompute_shopping_difficulty is the writer. INVARIANT: the "
            "rollup never writes 'unrated' (it maps an unrated ingredient to "
            "'findable'), so 'unrated' here means ONLY 'not yet computed'."
        ),
    )
    shopping_blockers = models.JSONField(
        default=list,
        blank=True,
        help_text="Canonical slugs rated worse than common that set shopping_difficulty",
    )
    adaptation_note = models.CharField(
        max_length=300,
        blank=True,
        help_text='Disclosed change vs the credited source, e.g. "Upraveno pro dostupnost v českých obchodech"',
    )
    original_ingredients = models.JSONField(
        null=True,
        blank=True,
        help_text="Pre-rewrite snapshot of `ingredients`; makes a substitution revertible",
    )
```

- [ ] **Step 4: Generate the migration**

Run: `python manage.py makemigrations diet_planner --name curatedrecipe_shopping_difficulty`
Expected: four `Add field ... to curatedrecipe` lines

- [ ] **Step 5: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability -v 2`
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add diet_planner/models/curated.py \
        diet_planner/migrations/0036_curatedrecipe_shopping_difficulty.py \
        diet_planner/tests/test_ingredient_availability.py
git commit -m "feat(curated): add shopping_difficulty rollup fields to CuratedRecipe"
```

---

### Task 3: The pure rollup function

This is the single source of truth. The rollup command, the report and the intake gate all call it — nothing reimplements the ordering.

**Files:**
- Create: `diet_planner/services/ingredient_availability.py`
- Test: `diet_planner/tests/test_ingredient_availability.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_ingredient_availability.py`:

```python
from diet_planner.services.ingredient_availability import (
    availability_index,
    compute_shopping_difficulty,
    unshoppable_ingredients,
)
from diet_planner.tests.factories import make_canonical


class ComputeShoppingDifficultyTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('kadeřávek', availability=Availability.FINDABLE)
        make_canonical('tahini', availability=Availability.SPECIALTY)
        make_canonical('záhadná věc')  # left UNRATED on purpose

    def _ings(self, *specs):
        return [{'name': n, 'canonical': s, 'optional': o} for n, s, o in specs]

    def test_all_common_is_common_with_no_blockers(self):
        r = CuratedRecipe(ingredients=self._ings(('sůl', 'sul', False)))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.COMMON)
        self.assertEqual(blockers, [])

    def test_worst_ingredient_wins(self):
        r = CuratedRecipe(ingredients=self._ings(
            ('sůl', 'sul', False),
            ('kadeřávek', 'kaderavek', False),
            ('tahini', 'tahini', False),
        ))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.SPECIALTY)
        self.assertEqual(blockers, ['kaderavek', 'tahini'])

    def test_optional_ingredients_are_ignored(self):
        r = CuratedRecipe(ingredients=self._ings(
            ('sůl', 'sul', False),
            ('tahini', 'tahini', True),
        ))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.COMMON)
        self.assertEqual(blockers, [])

    def test_unrated_ingredient_ranks_as_findable_but_is_recorded(self):
        r = CuratedRecipe(ingredients=self._ings(('záhadná věc', 'zahadna-vec', False)))
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.FINDABLE)
        self.assertEqual(blockers, ['zahadna-vec'])

    def test_rollup_never_writes_unrated(self):
        r = CuratedRecipe(ingredients=self._ings(('záhadná věc', 'zahadna-vec', False)))
        tier, _ = compute_shopping_difficulty(r)
        self.assertNotEqual(tier, Availability.UNRATED)

    def test_unresolvable_name_is_treated_as_unrated(self):
        r = CuratedRecipe(ingredients=[{'name': 'blorptium', 'quantity': 1}])
        tier, blockers = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.FINDABLE)
        self.assertEqual(blockers, ['blorptium'])

    def test_empty_recipe_is_common(self):
        tier, blockers = compute_shopping_difficulty(CuratedRecipe(ingredients=[]))
        self.assertEqual(tier, Availability.COMMON)
        self.assertEqual(blockers, [])

    def test_plain_string_ingredients_do_not_crash(self):
        # Generated (non-corpus) meals carry bare strings; see normalize_ingredient_entries.
        r = CuratedRecipe(ingredients=['sůl', 'tahini'])
        tier, _ = compute_shopping_difficulty(r)
        self.assertEqual(tier, Availability.COMMON)

    def test_index_avoids_per_ingredient_queries(self):
        idx = availability_index()
        r = CuratedRecipe(ingredients=self._ings(('tahini', 'tahini', False)))
        with self.assertNumQueries(0):
            tier, _ = compute_shopping_difficulty(r, index=idx)
        self.assertEqual(tier, Availability.SPECIALTY)


class UnshoppableIngredientsTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('kadeřávek', availability=Availability.FINDABLE)
        make_canonical('tahini', availability=Availability.SPECIALTY)

    def test_specialty_and_unrated_block_findable_does_not(self):
        ings = [
            {'name': 'sůl', 'canonical': 'sul'},
            {'name': 'kadeřávek', 'canonical': 'kaderavek'},
            {'name': 'tahini', 'canonical': 'tahini'},
            {'name': 'blorptium'},
        ]
        self.assertEqual(unshoppable_ingredients(ings), ['blorptium', 'tahini'])

    def test_optional_specialty_does_not_block(self):
        ings = [{'name': 'tahini', 'canonical': 'tahini', 'optional': True}]
        self.assertEqual(unshoppable_ingredients(ings), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability -v 2`
Expected: FAIL with `ModuleNotFoundError: No module named 'diet_planner.services.ingredient_availability'`

- [ ] **Step 3: Write the implementation**

Create `diet_planner/services/ingredient_availability.py`:

```python
"""Obtainability of ingredients in ordinary Czech supermarkets.

Single source of truth for the availability rollup. The recompute command,
the measurement report and the curation intake gate all call in here — none
of them reimplement the ordering.

See docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from diet_planner.models.catalog import Availability, CanonicalIngredient
from diet_planner.services.canonical_lookup import resolve_canonical

# UNRATED ranks alongside FINDABLE: a rating we have not made yet must not
# behave like a known-bad ingredient (that would collapse the corpus on the
# day the migration lands). Intake uses a different rule — see BLOCKING.
_RANK = {
    Availability.COMMON: 0,
    Availability.FINDABLE: 1,
    Availability.UNRATED: 1,
    Availability.SPECIALTY: 2,
}
_BY_RANK = {
    0: Availability.COMMON,
    1: Availability.FINDABLE,
    2: Availability.SPECIALTY,
}

#: Tiers a NEW recipe may not carry. Note UNRATED is here but not in the
#: ranking penalty — the asymmetry is deliberate.
BLOCKING = {Availability.SPECIALTY, Availability.UNRATED}


def availability_index() -> Dict[str, str]:
    """slug -> availability, for bulk walks.

    Pass this to compute_shopping_difficulty when iterating the corpus;
    otherwise each ingredient costs a query.
    """
    return dict(CanonicalIngredient.objects.values_list('slug', 'availability'))


def _entry_availability(
    ing: dict, index: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """(availability, blocker_key) for one ingredient dict.

    blocker_key is the canonical slug when we know it, else the raw name —
    an unresolvable ingredient still needs to be nameable in a report.
    """
    slug = ing.get('canonical')
    if slug:
        if index is not None:
            if slug in index:
                return index[slug], slug
        else:
            ci = CanonicalIngredient.objects.filter(slug=slug).first()
            if ci is not None:
                return ci.availability, ci.slug

    name = (ing.get('name') or '').strip()
    if index is None:
        ci = resolve_canonical(name)
        if ci is not None:
            return ci.availability, ci.slug
    return Availability.UNRATED, (slug or name.lower())


def _dict_entries(ingredients) -> List[dict]:
    """Non-optional ingredient dicts only.

    Generated (non-corpus) meals carry bare strings rather than dicts; those
    have no canonical to rate, so they are skipped rather than crashing.
    See normalize_ingredient_entries in canonical_lookup.
    """
    out = []
    for ing in ingredients or []:
        if not isinstance(ing, dict):
            continue
        if ing.get('optional'):
            continue
        out.append(ing)
    return out


def compute_shopping_difficulty(
    recipe, index: Optional[Dict[str, str]] = None,
) -> Tuple[str, List[str]]:
    """(shopping_difficulty, shopping_blockers) for one recipe.

    Worst non-optional ingredient wins: one un-buyable item ruins the trip as
    thoroughly as five. Never returns UNRATED — see the field's docstring.
    """
    worst = 0
    blockers = set()
    for ing in _dict_entries(recipe.ingredients):
        availability, key = _entry_availability(ing, index)
        rank = _RANK.get(availability, 1)
        if rank > 0 and key:
            blockers.add(key)
        worst = max(worst, rank)
    return _BY_RANK[worst], sorted(blockers)


def unshoppable_ingredients(
    ingredients, index: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Blocker keys that disqualify a NEW recipe at intake.

    Reads ingredient tiers directly rather than the recipe rollup: the rollup
    softens UNRATED to FINDABLE, which is right for ranking and wrong here.
    """
    blocked = set()
    for ing in _dict_entries(ingredients):
        availability, key = _entry_availability(ing, index)
        if availability in BLOCKING and key:
            blocked.add(key)
    return sorted(blocked)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability -v 2`
Expected: PASS (16 tests)

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/ingredient_availability.py \
        diet_planner/tests/test_ingredient_availability.py
git commit -m "feat(availability): pure shopping-difficulty rollup and intake predicate"
```

---

### Task 4: CSV → YAML importer

The owner's review lives in `docs/ingredient-availability-review.csv`. This converts it into the seed the DB actually loads, so the owner can keep filling in `YOUR_TIER` and re-run.

**Files:**
- Create: `diet_planner/management/commands/import_availability_review.py`
- Create: `diet_planner/data/ingredient_availability.yaml` (generated output — commit it)
- Test: `diet_planner/tests/test_rate_ingredient_availability.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_rate_ingredient_availability.py`:

```python
"""CSV -> YAML import and YAML -> DB rating."""
import csv
import tempfile
from pathlib import Path

import yaml
from django.core.management import CommandError, call_command
from django.test import TestCase

from diet_planner.models import Availability, CanonicalIngredient
from diet_planner.tests.factories import make_canonical

_COLUMNS = ['REVIEW', 'recipes', 'slug', 'name_cs', 'category',
            'claude_tier', 'confidence', 'claude_note', 'YOUR_TIER', 'YOUR_NOTE']


def write_csv(path, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in _COLUMNS})


class ImportAvailabilityReviewTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.csv_path = self.tmp / 'review.csv'
        self.yaml_path = self.tmp / 'availability.yaml'

    def _run(self):
        call_command('import_availability_review',
                     csv_file=str(self.csv_path), out=str(self.yaml_path))
        return yaml.safe_load(self.yaml_path.read_text(encoding='utf-8'))

    def test_claude_tier_is_used_when_owner_left_it_blank(self):
        write_csv(self.csv_path, [
            {'slug': 'tahini', 'claude_tier': 'specialty',
             'confidence': 'high', 'claude_note': 'asian shops'},
        ])
        data = self._run()
        self.assertEqual(data[0]['slug'], 'tahini')
        self.assertEqual(data[0]['availability'], 'specialty')
        self.assertEqual(data[0]['confidence'], 'high')
        self.assertEqual(data[0]['note'], 'asian shops')

    def test_owner_tier_overrides_and_marks_confidence_owner(self):
        write_csv(self.csv_path, [
            {'slug': 'smoked-paprika', 'claude_tier': 'findable',
             'confidence': 'low', 'claude_note': 'Lidl?',
             'YOUR_TIER': 'common', 'YOUR_NOTE': 'everywhere'},
        ])
        data = self._run()
        self.assertEqual(data[0]['availability'], 'common')
        self.assertEqual(data[0]['confidence'], 'owner')
        self.assertEqual(data[0]['note'], 'everywhere')

    def test_owner_tier_is_normalised_and_validated(self):
        write_csv(self.csv_path, [
            {'slug': 'x', 'claude_tier': 'common', 'confidence': 'high',
             'YOUR_TIER': '  COMMON '},
        ])
        self.assertEqual(self._run()[0]['availability'], 'common')

    def test_unknown_tier_is_a_hard_error(self):
        write_csv(self.csv_path, [
            {'slug': 'x', 'claude_tier': 'common', 'confidence': 'high',
             'YOUR_TIER': 'maybe'},
        ])
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('maybe', str(ctx.exception))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_rate_ingredient_availability.ImportAvailabilityReviewTest -v 2`
Expected: FAIL with `CommandError: Unknown command: 'import_availability_review'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/import_availability_review.py`:

```python
"""Convert the owner review CSV into the availability seed YAML.

The CSV (docs/ingredient-availability-review.csv) is the human surface: the
owner fills YOUR_TIER only where he disagrees. This produces the machine
surface that rate_ingredient_availability loads. Re-run it whenever more
rows get reviewed.
"""
import csv
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import Availability

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CSV = REPO_ROOT / 'docs' / 'ingredient-availability-review.csv'
DEFAULT_OUT = Path(__file__).resolve().parents[2] / 'data' / 'ingredient_availability.yaml'

VALID = {c for c in Availability.values if c != Availability.UNRATED}

HEADER = (
    "# GENERATED by `manage.py import_availability_review` — do not hand-edit.\n"
    "# Source of truth is docs/ingredient-availability-review.csv (owner review).\n"
    "# confidence: owner = arbitrated by the owner; low = Claude is guessing.\n"
)


class Command(BaseCommand):
    help = 'Convert the availability review CSV into data/ingredient_availability.yaml'

    def add_arguments(self, parser):
        parser.add_argument('--csv-file', dest='csv_file', default=str(DEFAULT_CSV))
        parser.add_argument('--out', dest='out', default=str(DEFAULT_OUT))

    def handle(self, *args, **options):
        csv_path = Path(options['csv_file'])
        if not csv_path.exists():
            raise CommandError(f'Review CSV not found: {csv_path}')

        rows = []
        with csv_path.open(encoding='utf-8-sig', newline='') as fh:
            for line in csv.DictReader(fh):
                slug = (line.get('slug') or '').strip()
                if not slug:
                    continue
                owner_tier = (line.get('YOUR_TIER') or '').strip().lower()
                claude_tier = (line.get('claude_tier') or '').strip().lower()
                tier = owner_tier or claude_tier
                if tier not in VALID:
                    raise CommandError(
                        f'{slug}: unknown tier {tier!r} '
                        f'(expected one of {sorted(VALID)})'
                    )
                note = (line.get('YOUR_NOTE') or '').strip() \
                    or (line.get('claude_note') or '').strip()
                rows.append({
                    'slug': slug,
                    'availability': tier,
                    'confidence': 'owner' if owner_tier else (
                        line.get('confidence') or 'high').strip(),
                    'note': note[:200],
                })

        rows.sort(key=lambda r: r['slug'])
        out_path = Path(options['out'])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open('w', encoding='utf-8') as fh:
            fh.write(HEADER)
            yaml.safe_dump(rows, fh, allow_unicode=True, sort_keys=False)

        owner = sum(1 for r in rows if r['confidence'] == 'owner')
        guess = sum(1 for r in rows if r['confidence'] == 'low')
        self.stdout.write(self.style.SUCCESS(
            f'wrote {len(rows)} ratings to {out_path} '
            f'(owner-settled={owner}, still-guessing={guess})'
        ))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_rate_ingredient_availability.ImportAvailabilityReviewTest -v 2`
Expected: PASS (4 tests)

- [ ] **Step 5: Generate the real seed file**

Run: `python manage.py import_availability_review`
Expected: `wrote 297 ratings to .../ingredient_availability.yaml (owner-settled=13, still-guessing=57)`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/management/commands/import_availability_review.py \
        diet_planner/data/ingredient_availability.yaml \
        diet_planner/tests/test_rate_ingredient_availability.py
git commit -m "feat(availability): generate rating seed YAML from the owner review CSV"
```

---

### Task 5: YAML → DB rating command

**Files:**
- Create: `diet_planner/management/commands/rate_ingredient_availability.py`
- Test: `diet_planner/tests/test_rate_ingredient_availability.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_rate_ingredient_availability.py`:

```python
class RateIngredientAvailabilityTest(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.yaml_path = self.tmp / 'availability.yaml'
        make_canonical('tahini')
        make_canonical('sůl')

    def _write(self, rows):
        self.yaml_path.write_text(
            yaml.safe_dump(rows, allow_unicode=True), encoding='utf-8')

    def _run(self, **kw):
        call_command('rate_ingredient_availability', file=str(self.yaml_path), **kw)

    def _full(self):
        return [
            {'slug': 'tahini', 'availability': 'specialty',
             'confidence': 'high', 'note': 'asian shops'},
            {'slug': 'sul', 'availability': 'common',
             'confidence': 'high', 'note': ''},
        ]

    def test_applies_ratings_and_notes(self):
        self._write(self._full())
        self._run()
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability, 'specialty')
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability_note,
            'asian shops')
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='sul').availability, 'common')

    def test_is_idempotent(self):
        self._write(self._full())
        self._run()
        self._run()
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability, 'specialty')

    def test_dry_run_writes_nothing(self):
        self._write(self._full())
        self._run(dry_run=True)
        self.assertEqual(
            CanonicalIngredient.objects.get(slug='tahini').availability,
            Availability.UNRATED)

    def test_missing_canonical_is_a_hard_error(self):
        # 'sul' deliberately absent from the YAML: growing the dictionary must
        # not silently leave rows unrated.
        self._write([{'slug': 'tahini', 'availability': 'specialty',
                      'confidence': 'high', 'note': ''}])
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('sul', str(ctx.exception))

    def test_yaml_row_for_unknown_slug_is_a_hard_error(self):
        rows = self._full() + [{'slug': 'ghost', 'availability': 'common',
                                'confidence': 'high', 'note': ''}]
        self._write(rows)
        with self.assertRaises(CommandError) as ctx:
            self._run()
        self.assertIn('ghost', str(ctx.exception))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_rate_ingredient_availability.RateIngredientAvailabilityTest -v 2`
Expected: FAIL with `CommandError: Unknown command: 'rate_ingredient_availability'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/rate_ingredient_availability.py`:

```python
"""Apply data/ingredient_availability.yaml to CanonicalIngredient rows.

Idempotent. Fails loudly when the YAML and the canonical table disagree in
either direction — growing the ingredient dictionary must not silently leave
rows unrated, and a stale YAML row must not pass unnoticed.
"""
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import Availability, CanonicalIngredient

DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'ingredient_availability.yaml'
VALID = {c for c in Availability.values if c != Availability.UNRATED}


class Command(BaseCommand):
    help = 'Apply the availability seed YAML to CanonicalIngredient rows.'

    def add_arguments(self, parser):
        parser.add_argument('--file', dest='file', default=str(DEFAULT_FILE))
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            help='Print the diff, write nothing.')
        parser.add_argument('--report-uncertain', dest='report_uncertain',
                            action='store_true',
                            help='Print only the rows Claude is still guessing on.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'Availability file not found: {path}')

        rows = yaml.safe_load(path.read_text(encoding='utf-8')) or []
        by_slug = {}
        for row in rows:
            slug = (row.get('slug') or '').strip()
            tier = (row.get('availability') or '').strip().lower()
            if not slug:
                raise CommandError(f'Row without a slug: {row!r}')
            if tier not in VALID:
                raise CommandError(f'{slug}: unknown tier {tier!r}')
            by_slug[slug] = row

        if options['report_uncertain']:
            uncertain = [r for r in rows if (r.get('confidence') or '') == 'low']
            for r in sorted(uncertain, key=lambda r: r['slug']):
                self.stdout.write(
                    f"  {r['slug']:<28} {r['availability']:<10} {r.get('note') or ''}")
            self.stdout.write(self.style.WARNING(
                f'{len(uncertain)} row(s) still resting on a guess.'))
            return

        db_slugs = set(CanonicalIngredient.objects.values_list('slug', flat=True))
        missing = sorted(db_slugs - set(by_slug))
        if missing:
            raise CommandError(
                f'{len(missing)} canonical(s) have no rating in {path.name}: '
                f'{", ".join(missing[:20])}'
                + (' ...' if len(missing) > 20 else '')
            )
        ghosts = sorted(set(by_slug) - db_slugs)
        if ghosts:
            raise CommandError(
                f'{len(ghosts)} rating(s) reference unknown canonicals: '
                f'{", ".join(ghosts[:20])}'
                + (' ...' if len(ghosts) > 20 else '')
            )

        changed = 0
        for ci in CanonicalIngredient.objects.all().order_by('slug'):
            row = by_slug[ci.slug]
            tier = row['availability'].strip().lower()
            note = (row.get('note') or '')[:200]
            if ci.availability == tier and ci.availability_note == note:
                continue
            self.stdout.write(
                f'  {ci.slug:<28} {ci.availability} -> {tier}')
            changed += 1
            if not options['dry_run']:
                ci.availability = tier
                ci.availability_note = note
                ci.save(update_fields=['availability', 'availability_note', 'updated_at'])

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}rated={len(by_slug)} changed={changed}'))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_rate_ingredient_availability -v 2`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/rate_ingredient_availability.py \
        diet_planner/tests/test_rate_ingredient_availability.py
git commit -m "feat(availability): idempotent command applying rating YAML to canonicals"
```

---

### Task 6: Recompute the rollup across the corpus

**Files:**
- Create: `diet_planner/management/commands/recompute_shopping_difficulty.py`
- Modify: `diet_planner/services/recipe_curation.py`
- Test: `diet_planner/tests/test_ingredient_availability.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_ingredient_availability.py`:

```python
from django.core.management import call_command
from io import StringIO


class RecomputeShoppingDifficultyTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('tahini', availability=Availability.SPECIALTY)

    def _recipe(self, slug, ings, status=CuratedRecipe.Status.PUBLISHED):
        return CuratedRecipe.objects.create(
            slug=slug, name_cs=slug, status=status, ingredients=ings,
            source_url=f'https://example.test/{slug}', source_name='Example',
        )

    def test_sets_difficulty_and_blockers(self):
        r = self._recipe('a', [{'name': 'tahini', 'canonical': 'tahini'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.SPECIALTY)
        self.assertEqual(r.shopping_blockers, ['tahini'])

    def test_covers_drafts_not_just_published(self):
        r = self._recipe('b', [{'name': 'tahini', 'canonical': 'tahini'}],
                         status=CuratedRecipe.Status.DRAFT)
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.SPECIALTY)

    def test_dry_run_writes_nothing(self):
        r = self._recipe('c', [{'name': 'tahini', 'canonical': 'tahini'}])
        call_command('recompute_shopping_difficulty', dry_run=True, stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.UNRATED)

    def test_is_idempotent(self):
        r = self._recipe('d', [{'name': 'sůl', 'canonical': 'sul'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        out = StringIO()
        call_command('recompute_shopping_difficulty', stdout=out)
        self.assertIn('changed=0', out.getvalue())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, Availability.COMMON)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability.RecomputeShoppingDifficultyTest -v 2`
Expected: FAIL with `CommandError: Unknown command: 'recompute_shopping_difficulty'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/recompute_shopping_difficulty.py`:

```python
"""Recompute CuratedRecipe.shopping_difficulty / shopping_blockers.

Walks every status, not just published: drafts must be correct the moment
they are promoted. Writes nothing else.
"""
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services.ingredient_availability import (
    availability_index,
    compute_shopping_difficulty,
)


class Command(BaseCommand):
    help = 'Recompute the shopping-difficulty rollup for every curated recipe.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')

    def handle(self, *args, **options):
        index = availability_index()
        changed = 0
        total = 0

        for r in CuratedRecipe.objects.all().only(
            'id', 'slug', 'ingredients', 'shopping_difficulty', 'shopping_blockers',
        ).iterator():
            total += 1
            tier, blockers = compute_shopping_difficulty(r, index=index)
            if r.shopping_difficulty == tier and (r.shopping_blockers or []) == blockers:
                continue
            changed += 1
            if not options['dry_run']:
                r.shopping_difficulty = tier
                r.shopping_blockers = blockers
                r.save(update_fields=[
                    'shopping_difficulty', 'shopping_blockers', 'updated_at'])

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}recipes={total} changed={changed}'))
```

- [ ] **Step 4: Wire the rollup into curation**

In `diet_planner/services/recipe_curation.py`, add the import near the other service imports:

```python
from diet_planner.services.ingredient_availability import compute_shopping_difficulty
```

In `curate_from_source`, immediately after `recipe = CuratedRecipe(**fields)` and before the `if run_judge:` block:

```python
    # A freshly curated recipe must never be left "not yet computed".
    recipe.shopping_difficulty, recipe.shopping_blockers = compute_shopping_difficulty(recipe)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability diet_planner.tests.test_curation_plausibility_gate -v 2`
Expected: PASS (20 tests; the plausibility gate tests must still pass)

- [ ] **Step 6: Commit**

```bash
git add diet_planner/management/commands/recompute_shopping_difficulty.py \
        diet_planner/services/recipe_curation.py \
        diet_planner/tests/test_ingredient_availability.py
git commit -m "feat(availability): recompute rollup command, wired into curation"
```

---

### Task 7: The measurement report

This is the output the whole phase exists to produce. It decides whether Substitute/Unpublish go ahead.

**Files:**
- Create: `diet_planner/management/commands/report_shopping_difficulty.py`
- Test: `diet_planner/tests/test_ingredient_availability.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_ingredient_availability.py`:

```python
class ReportShoppingDifficultyTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('tahini', availability=Availability.SPECIALTY)
        make_canonical('kadeřávek', availability=Availability.FINDABLE)

    def _recipe(self, slug, ings, meal_types, tags):
        r = CuratedRecipe.objects.create(
            slug=slug, name_cs=slug, status=CuratedRecipe.Status.PUBLISHED,
            ingredients=ings, meal_types=meal_types, dietary_tags=tags,
            source_url=f'https://example.test/{slug}', source_name='Example',
        )
        return r

    def _report(self):
        out = StringIO()
        self._recipe('clean', [{'name': 'sůl', 'canonical': 'sul'}],
                     ['lunch'], ['gluten_free'])
        self._recipe('blocked', [{'name': 'tahini', 'canonical': 'tahini'}],
                     ['lunch'], ['gluten_free'])
        self._recipe('mid', [{'name': 'kadeřávek', 'canonical': 'kaderavek'}],
                     ['dinner'], [])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        call_command('report_shopping_difficulty', stdout=out)
        return out.getvalue()

    def test_reports_tier_distribution(self):
        text = self._report()
        self.assertIn('common', text)
        self.assertIn('specialty', text)
        self.assertIn('published recipes: 3', text)

    def test_reports_meal_type_by_dietary_tag_slice(self):
        text = self._report()
        self.assertIn('lunch', text)
        self.assertIn('gluten_free', text)

    def test_reports_blocker_frequency(self):
        text = self._report()
        self.assertIn('tahini', text)

    def test_writes_nothing(self):
        self._report()
        before = list(CuratedRecipe.objects.values_list('shopping_difficulty', flat=True))
        call_command('report_shopping_difficulty', stdout=StringIO())
        after = list(CuratedRecipe.objects.values_list('shopping_difficulty', flat=True))
        self.assertEqual(before, after)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability.ReportShoppingDifficultyTest -v 2`
Expected: FAIL with `CommandError: Unknown command: 'report_shopping_difficulty'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/report_shopping_difficulty.py`:

```python
"""Read-only measurement of corpus obtainability. Writes nothing.

This is the report the spec gates corpus mutation on: the number that matters
is not "how many recipes are clean" but "does each slot still have a pool".
"""
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from diet_planner.models import Availability, CuratedRecipe

ORDER = [Availability.COMMON, Availability.FINDABLE,
         Availability.SPECIALTY, Availability.UNRATED]


class Command(BaseCommand):
    help = 'Report how much of the published corpus is unshoppable. Read-only.'

    def add_arguments(self, parser):
        parser.add_argument('--top-blockers', type=int, default=25,
                            help='How many blocking ingredients to list.')

    def handle(self, *args, **options):
        recipes = list(CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED,
        ).only('id', 'shopping_difficulty', 'shopping_blockers',
               'meal_types', 'dietary_tags'))

        total = len(recipes)
        self.stdout.write(f'published recipes: {total}')
        if not total:
            return

        tiers = Counter(r.shopping_difficulty for r in recipes)
        self.stdout.write('\n-- distribution --')
        for tier in ORDER:
            n = tiers.get(tier, 0)
            self.stdout.write(f'  {tier:<10} {n:>4}  ({100.0 * n / total:.1f}%)')
        if tiers.get(Availability.UNRATED):
            self.stdout.write(self.style.WARNING(
                '  NOTE: "unrated" here means the rollup has not run for those '
                'rows — run recompute_shopping_difficulty.'))

        # The number that actually matters: does each slot keep a pool?
        self.stdout.write('\n-- pool by meal_type x dietary_tag (common / total) --')
        pools = defaultdict(lambda: [0, 0])
        for r in recipes:
            tags = list(r.dietary_tags or []) or ['(none)']
            for slot in (r.meal_types or ['(untagged)']):
                for tag in tags:
                    cell = pools[(slot, tag)]
                    cell[1] += 1
                    if r.shopping_difficulty == Availability.COMMON:
                        cell[0] += 1
        for (slot, tag), (clean, tot) in sorted(pools.items()):
            flag = '  <-- THIN' if clean < 10 else ''
            self.stdout.write(f'  {slot:<12} {tag:<16} {clean:>4} / {tot:<4}{flag}')

        self.stdout.write('\n-- blocking ingredients by recipes cost --')
        blockers = Counter()
        for r in recipes:
            for slug in (r.shopping_blockers or []):
                blockers[slug] += 1
        limit = options['top_blockers']
        for slug, n in blockers.most_common(limit):
            self.stdout.write(f'  {n:>4}  {slug}')
        if len(blockers) > limit:
            self.stdout.write(
                f'  ... and {len(blockers) - limit} more blocking ingredient(s) '
                f'not shown (raise --top-blockers)')

        non_common = total - tiers.get(Availability.COMMON, 0)
        self.stdout.write(self.style.WARNING(
            f'\n{non_common} of {total} published recipes '
            f'({100.0 * non_common / total:.1f}%) fail the one-stop bar.'))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_ingredient_availability -v 2`
Expected: PASS (24 tests)

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/report_shopping_difficulty.py \
        diet_planner/tests/test_ingredient_availability.py
git commit -m "feat(availability): read-only corpus obtainability report"
```

---

### Task 8: The intake gate

**Files:**
- Modify: `llm_diet_planner_project/settings.py`
- Modify: `diet_planner/services/recipe_curation.py:285-380`
- Modify: `diet_planner/services/recipe_research.py:252`
- Test: `diet_planner/tests/test_curation_availability_gate.py`

**Sequencing note — read before implementing.** The spec gives chat web research an extra move: substitute first, reject only if unsaveable. The substitution table does not exist until the *next* plan. So in this phase `recipe_research` explicitly opts **out** of the gate. Turning it on before substitutions exist would make "najdi mi něco s tofu" start failing for a live, shipped feature. This is a deliberate, documented deferral, not an omission.

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_curation_availability_gate.py`:

```python
"""Integration test: the availability gate rejects unshoppable new recipes."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from diet_planner.models import Availability, CuratedRecipe
from diet_planner.services import recipe_curation
from diet_planner.tests.factories import make_canonical

_CURATED = {
    "name_cs": "Salát s tahini",
    "name_en": "Tahini salad",
    "description": "Svěží salát.",
    "meal_types": ["lunch"],
    "cuisine": "mediterranean",
    "difficulty": "easy",
    "dietary_tags": [],
    "ingredients": [
        {"name": "sůl", "quantity": 5, "unit": "g"},
        {"name": "tahini", "quantity": 30, "unit": "g"},
    ],
    "instructions": [{"text": "Smíchej suroviny a podávej."}],
    "base_servings": 2,
    "base_nutrition": {"calories": 400},
    "prep_time": 10,
    "cook_time": 0,
}


class CurationAvailabilityGateTest(TestCase):
    def setUp(self):
        make_canonical('sůl', availability=Availability.COMMON)
        make_canonical('tahini', availability=Availability.SPECIALTY)

    def _run(self, **kwargs):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = _CURATED
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/salat", "source_name": "Example"},
                run_judge=False,
                **kwargs,
            )

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_rejects_specialty_ingredient(self):
        result = self._run()
        self.assertFalse(result.ok)
        self.assertTrue(result.error.startswith('unshoppable ingredients:'))
        self.assertIn('tahini', result.error)
        self.assertEqual(CuratedRecipe.objects.count(), 0)

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_enforce_availability_false_bypasses_the_gate(self):
        result = self._run(enforce_availability=False)
        self.assertTrue(result.ok)
        self.assertEqual(CuratedRecipe.objects.count(), 1)

    @override_settings(AVAILABILITY_GATE_ENABLED=False)
    def test_flag_off_bypasses_the_gate(self):
        result = self._run()
        self.assertTrue(result.ok)
        self.assertEqual(CuratedRecipe.objects.count(), 1)

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_unrated_ingredient_also_blocks(self):
        make_canonical('záhadná věc')  # UNRATED
        payload = dict(_CURATED)
        payload['ingredients'] = [
            {"name": "sůl", "quantity": 5, "unit": "g"},
            {"name": "záhadná věc", "quantity": 5, "unit": "g"},
        ]
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = payload
            result = recipe_curation.curate_from_source(
                {"source_url": "https://example.test/zahada", "source_name": "Example"},
                run_judge=False,
            )
        self.assertFalse(result.ok)
        self.assertIn('unshoppable', result.error)

    @override_settings(AVAILABILITY_GATE_ENABLED=True)
    def test_all_common_recipe_passes(self):
        payload = dict(_CURATED)
        payload['ingredients'] = [{"name": "sůl", "quantity": 5, "unit": "g"}]
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = payload
            result = recipe_curation.curate_from_source(
                {"source_url": "https://example.test/sul", "source_name": "Example"},
                run_judge=False,
            )
        self.assertTrue(result.ok)
        self.assertEqual(result.recipe.shopping_difficulty, Availability.COMMON)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_curation_availability_gate -v 2`
Expected: FAIL — `curate_from_source() got an unexpected keyword argument 'enforce_availability'`

- [ ] **Step 3: Add the settings flag**

In `llm_diet_planner_project/settings.py`, next to the other feature flags (near `RECIPE_GROUNDING_ENABLED`, line ~385):

```python
# Reject newly curated recipes carrying ingredients you cannot buy in an
# ordinary Czech supermarket. Ships off; flip on once ratings are loaded.
AVAILABILITY_GATE_ENABLED = config('AVAILABILITY_GATE_ENABLED', default=False, cast=bool)
```

- [ ] **Step 4: Add the gate to curate_from_source**

In `diet_planner/services/recipe_curation.py`, add to the imports:

```python
from django.conf import settings as django_settings

from diet_planner.services.ingredient_availability import unshoppable_ingredients
```

Change the signature of `curate_from_source`:

```python
def curate_from_source(
    entry: Dict[str, str],
    *,
    gemini: Optional[GeminiService] = None,
    run_judge: bool = True,
    persist: bool = True,
    enforce_plausibility: bool = True,
    enforce_availability: bool = True,
) -> CurationResult:
```

Then, directly after the `if enforce_plausibility:` block and before `recipe = CuratedRecipe(**fields)`:

```python
    if enforce_availability and getattr(
        django_settings, 'AVAILABILITY_GATE_ENABLED', False,
    ):
        # Reads ingredient tiers directly, NOT the recipe rollup: the rollup
        # softens 'unrated' to 'findable', which is right for ranking and
        # wrong for intake.
        blocked = unshoppable_ingredients(fields["ingredients"])
        if blocked:
            result.error = "unshoppable ingredients: " + ", ".join(blocked)
            return result
```

- [ ] **Step 5: Opt chat research out, explicitly**

In `diet_planner/services/recipe_research.py`, at the `curate_from_source(` call around line 252:

```python
        result = curate_from_source(
            {'dish_name': job.query, 'source_url': src['url'], 'source_name': src['name']},
            persist=False,
            # Deliberately opted out until the CZ substitution table exists.
            # Gating here first would make "najdi mi něco s tofu" fail outright
            # instead of substituting. Flip to the default when the
            # substitution phase lands.
            enforce_availability=False,
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python manage.py test diet_planner.tests.test_curation_availability_gate diet_planner.tests.test_curation_plausibility_gate -v 2`
Expected: PASS (7 tests)

- [ ] **Step 7: Run the whole backend suite for regressions**

Run: `python manage.py test diet_planner -v 1`
Expected: PASS, no new failures vs the pre-change baseline

- [ ] **Step 8: Commit**

```bash
git add llm_diet_planner_project/settings.py \
        diet_planner/services/recipe_curation.py \
        diet_planner/services/recipe_research.py \
        diet_planner/tests/test_curation_availability_gate.py
git commit -m "feat(curation): gate new recipes on Czech-supermarket availability"
```

---

### Task 9: Load the ratings and produce the report

No new code — this is the operational run that produces the number the next phase depends on.

**Files:** none modified.

- [ ] **Step 1: Apply the migrations locally and rate**

```bash
python manage.py migrate diet_planner
python manage.py rate_ingredient_availability --dry-run
```

Expected: a list of `slug  unrated -> <tier>` lines ending in `[dry-run] rated=297 changed=297`

- [ ] **Step 2: Apply for real, then roll up**

```bash
python manage.py rate_ingredient_availability
python manage.py recompute_shopping_difficulty
```

Expected: `rated=297 changed=297`, then `recipes=<N> changed=<N>`

- [ ] **Step 3: Produce the report**

```bash
python manage.py report_shopping_difficulty > docs/shopping-difficulty-report-2026-08-11.txt
cat docs/shopping-difficulty-report-2026-08-11.txt
```

Expected: distribution, the meal_type × dietary_tag pool table with `<-- THIN` markers, blocker frequency, and a closing "N of 458 published recipes (X%) fail the one-stop bar."

- [ ] **Step 4: Commit the report**

```bash
git add docs/shopping-difficulty-report-2026-08-11.txt
git commit -m "docs: corpus obtainability measurement report"
```

- [ ] **Step 5: STOP — decision gate**

Do not proceed to substitution or unpublishing. Present the report to the owner. His three options:

1. **Go** — corpus survives the cut; proceed to the substitution plan.
2. **Stop** — ship Phase 1 only (ratings, report, intake gate); no corpus mutation.
3. **Re-scope** — pools are too thin; curate Czech-shoppable recipes *before* dropping anything.

Prod rollout of Phase 1 (running `rate_ingredient_availability` + `recompute_shopping_difficulty` against the prod DB via the console harness, then flipping `AVAILABILITY_GATE_ENABLED`) also waits for this conversation — see `[[prod-console-exec-harness]]` for the chunked-upload requirement.

---

## Self-Review

**Spec coverage:**

| Spec deliverable | Task | Status |
|---|---|---|
| `CanonicalIngredient.availability` + note | 1 | covered |
| `unrated` asymmetry (ranks findable, blocks intake) | 1, 3 | covered — `_RANK` vs `BLOCKING`, tested both ways |
| `CuratedRecipe` rollup fields | 2 | covered |
| Ratings live in git | 4 | covered |
| `--report-uncertain` | 5 | covered |
| Fail loudly on a canonical missing from YAML | 5 | covered, tested both directions |
| Rollup: worst-wins, optional ignored, unresolvable → unrated | 3, 6 | covered |
| Rollup runs from batch command *and* curation | 6 | covered |
| Report incl. meal_type × dietary_tag + blocker frequency | 7 | covered |
| Decision gate before corpus mutation | 9 | covered as an explicit STOP |
| Intake gate + kill switch | 8 | covered |
| Chat research substitute-then-reject | — | **deferred with reason** (Task 8 note); needs the substitution table |
| `IngredientSubstitute.purpose` / `substitute_unit` | — | next plan (substitution phase) |
| Substitution rewrite, unpublish, ranking term | — | next plan (gated on Task 9's report) |

The three deferrals are the spec's own conditional steps plus one sequencing decision that prevents a live UX regression. Everything unconditional in the spec is planned.

**Placeholder scan:** no TBD/TODO, no "add error handling", no "similar to Task N". Every code step carries complete code; every command step carries its expected output.

**Type consistency:** `compute_shopping_difficulty(recipe, index=None) -> (str, List[str])` and `unshoppable_ingredients(ingredients, index=None) -> List[str]` are defined in Task 3 and called with those exact signatures in Tasks 6, 7 and 8. `availability_index()` returns `Dict[str, str]` and is consumed as such. `Availability` is imported from `diet_planner.models` in tests and from `diet_planner.models.catalog` in services — both valid once Task 1 exports it.

**One known risk not resolved here:** `_entry_availability` falls back to `resolve_canonical(name)` only when no `index` is supplied. During a bulk walk (index present) an ingredient whose `canonical` slug is missing from the index is treated as `unrated` rather than being re-resolved by name. That is the intended fast path — a corpus ingredient without a valid canonical *is* unmapped — but it means bulk and single-recipe evaluation can disagree for malformed rows. Tested via `test_unresolvable_name_is_treated_as_unrated` (single) and `test_index_avoids_per_ingredient_queries` (bulk).
