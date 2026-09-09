# Demand-Driven Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make plan selection prefer dishes Czech and Slovak households actually search for, with seasonality, and use the owner's ratings only to break ties between recipes of the same dish.

**Architecture:** A committed YAML demand map (`diet_planner/data/demand_map_cz.yaml`) is loaded by a small service; a management command copies each recipe's demand term, score, and peak month onto four new denormalised `CuratedRecipe` fields; `score_recipe` reads those fields and adds three terms. Nothing joins the YAML at request time. Fields default to null, so deploy order does not matter and unpopulated rows score exactly as today.

**Tech Stack:** Django 5.1 models/migrations/management commands, PyYAML, `unittest` via `manage.py test`. Run tests with `GEMINI_API_KEY=dummy python3 manage.py test <dotted.path>`.

**Spec:** `docs/superpowers/specs/2026-09-09-demand-ranking-design.md`

---

## File structure

| File | Responsibility |
|---|---|
| `diet_planner/data/demand_map_cz.yaml` | Data. One row per demand term: `term, demand, peak_month, kind, slot, aliases`. Already generated from the Trends run; Task 1 only validates and commits it. |
| `diet_planner/data/demand_overrides.yaml` | Data. `slug: term` pins by the owner. Starts with the lečo pins. |
| `diet_planner/services/demand_map.py` | Load + validate the YAML, expose `DemandTerm`, `load_demand_map()`, `load_overrides()`, and `match_demand_term(recipe, terms, overrides)`. No DB writes. |
| `diet_planner/models/curated.py` | Four new fields on `CuratedRecipe`. |
| `diet_planner/migrations/0039_demand_fields.py` | The migration. |
| `diet_planner/management/commands/attach_demand_terms.py` | Writes the four fields for every `CuratedRecipe`; `--dry-run`; `--ratings` JSON import. |
| `diet_planner/services/recipe_retrieval.py` | Three new score terms in `score_recipe`. |
| `diet_planner/management/commands/build_curated_recipes.py` | Attaches the demand term to each newly curated recipe. |
| `diet_planner/tests/test_demand_map.py` | Loader + matcher tests. |
| `diet_planner/tests/test_attach_demand_terms.py` | Command tests. |
| `diet_planner/tests/test_demand_ranking.py` | Scoring tests. |
| `docs/demand-ranking-ops.md` | Runbook: how to refresh the map, pin overrides, run the command on prod. |

---

### Task 1: Demand map loader and data file

**Files:**
- Create: `diet_planner/services/demand_map.py`
- Create: `diet_planner/data/demand_overrides.yaml`
- Commit (already generated): `diet_planner/data/demand_map_cz.yaml`
- Test: `diet_planner/tests/test_demand_map.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Demand map: the committed Trends data and the loader that reads it."""
from pathlib import Path

from django.test import SimpleTestCase

from diet_planner.services.demand_map import (
    DemandTerm, load_demand_map, load_overrides, DEFAULT_MAP, DEFAULT_OVERRIDES,
)


class DemandMapFileTests(SimpleTestCase):
    def test_committed_map_loads_and_is_anchored_on_gulas(self):
        terms = load_demand_map()
        self.assertIn('guláš', terms)
        self.assertEqual(terms['guláš'].demand, 100.0)
        self.assertEqual(terms['guláš'].kind, 'dish')

    def test_every_row_has_the_fields_ranking_needs(self):
        for term in load_demand_map().values():
            self.assertIsInstance(term, DemandTerm)
            self.assertGreaterEqual(term.demand, 0.0)
            self.assertIn(term.kind, {'dish', 'category', 'restaurant', 'intent'})
            self.assertTrue(term.peak_month is None or 1 <= term.peak_month <= 12)

    def test_slovak_alias_is_carried(self):
        self.assertIn('sviečková', load_demand_map()['svíčková'].aliases)

    def test_overrides_file_loads_as_slug_to_term(self):
        overrides = load_overrides()
        self.assertEqual(overrides.get('leco'), 'lečo')

    def test_loader_rejects_a_row_without_demand(self):
        bad = Path('/tmp/bad_demand_map.yaml')
        bad.write_text('anchor: guláš\nterms:\n  - term: x\n    kind: dish\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            load_demand_map(bad)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_demand_map`
Expected: `ImportError: cannot import name 'DemandTerm'` (module missing).

- [ ] **Step 3: Write the overrides file**

`diet_planner/data/demand_overrides.yaml`:

```yaml
# Owner pins: CuratedRecipe slug -> demand term. Wins over the name matcher.
# Add a line whenever `attach_demand_terms --dry-run` attaches the wrong term.
leco: lečo
leco-s-klobasou-a-vejci: lečo
domaci-leco: lečo
```

- [ ] **Step 4: Write the loader**

`diet_planner/services/demand_map.py`:

```python
"""The demand map: what CZ/SK households search for, relative to guláš = 100.

Data lives in diet_planner/data/demand_map_cz.yaml (Google Trends, refreshed
by hand, see docs/demand-ranking-ops.md). This module only reads it and
matches recipes to terms; writing the result onto CuratedRecipe is the
attach_demand_terms command's job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from diet_planner.services.user_simulation import _significant_words, _strict_hit

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
DEFAULT_MAP = DATA_DIR / 'demand_map_cz.yaml'
DEFAULT_OVERRIDES = DATA_DIR / 'demand_overrides.yaml'

#: Only these rows may attach to a recipe. Generic words ("salát"), delivery
#: searches ("pizza") and diet queries ("keto recepty") describe intent, not a dish.
ATTACHABLE_KINDS = {'dish'}


@dataclass(frozen=True)
class DemandTerm:
    term: str
    demand: float
    kind: str
    slot: str
    peak_month: Optional[int] = None
    aliases: List[str] = field(default_factory=list)

    @property
    def names(self) -> List[str]:
        return [self.term, *self.aliases]


def load_demand_map(path: Path = DEFAULT_MAP) -> Dict[str, DemandTerm]:
    doc = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    out: Dict[str, DemandTerm] = {}
    for row in doc.get('terms') or []:
        term = (row.get('term') or '').strip()
        if not term or row.get('demand') is None:
            raise ValueError(f'demand map row needs term and demand: {row!r}')
        peak = row.get('peak_month')
        out[term] = DemandTerm(
            term=term, demand=float(row['demand']), kind=row.get('kind') or 'dish',
            slot=row.get('slot') or 'main', peak_month=int(peak) if peak else None,
            aliases=[str(a) for a in (row.get('aliases') or [])],
        )
    return out


def load_overrides(path: Path = DEFAULT_OVERRIDES) -> Dict[str, str]:
    if not Path(path).exists():
        return {}
    doc = yaml.safe_load(Path(path).read_text(encoding='utf-8')) or {}
    return {str(k): str(v) for k, v in doc.items()}


def match_demand_term(recipe, terms: Dict[str, DemandTerm], overrides: Dict[str, str]):
    """(DemandTerm | None, how) for one recipe. how ∈ {'override', 'name', ''}."""
    pinned = overrides.get(recipe.slug)
    if pinned:
        return terms.get(pinned), 'override'
    best = None
    for term in terms.values():
        if term.kind not in ATTACHABLE_KINDS:
            continue
        if any(_strict_hit(_significant_words(name), recipe) for name in term.names):
            if best is None or term.demand > best.demand:
                best = term
    return best, ('name' if best else '')
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_demand_map`
Expected: `Ran 5 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/services/demand_map.py diet_planner/data/demand_map_cz.yaml diet_planner/data/demand_overrides.yaml diet_planner/tests/test_demand_map.py
git commit -m "feat(demand): commit the CZ/SK demand map and its loader"
```

---

### Task 2: Matcher behaviour

**Files:**
- Modify: `diet_planner/services/demand_map.py` (no change expected; this task pins behaviour)
- Test: `diet_planner/tests/test_demand_map.py`

- [ ] **Step 1: Write the failing tests** (append to the same test file)

```python
from django.test import TestCase
from diet_planner.models import CuratedRecipe
from diet_planner.services.demand_map import match_demand_term


def _recipe(slug, name_cs):
    return CuratedRecipe.objects.create(
        slug=slug, name_cs=name_cs, meal_types=['lunch'], ingredients=[], instructions=[],
        source_url=f'https://example.com/{slug}', source_name='Example',
    )


class MatchDemandTermTests(TestCase):
    def setUp(self):
        self.terms = {
            'guláš': DemandTerm('guláš', 100.0, 'dish', 'main'),
            'segedínský guláš': DemandTerm('segedínský guláš', 18.4, 'dish', 'main', aliases=['segedínsky guláš']),
            'salát': DemandTerm('salát', 192.8, 'category', 'light'),
            'řízek': DemandTerm('řízek', 48.5, 'dish', 'main', aliases=['rezeň']),
        }

    def test_override_wins_over_name(self):
        r = _recipe('leco', 'Lečo')
        term, how = match_demand_term(r, {**self.terms, 'lečo': DemandTerm('lečo', 19.8, 'dish', 'main')}, {'leco': 'lečo'})
        self.assertEqual((term.term, how), ('lečo', 'override'))

    def test_name_match_prefers_the_higher_demand_term(self):
        r = _recipe('hovezi-gulas', 'Hovězí guláš')
        term, how = match_demand_term(r, self.terms, {})
        self.assertEqual((term.term, how), ('guláš', 'name'))

    def test_slovak_alias_matches(self):
        r = _recipe('bravcovy-rezen', 'Bravčový rezeň')
        term, _ = match_demand_term(r, self.terms, {})
        self.assertEqual(term.term, 'řízek')

    def test_category_rows_never_attach(self):
        r = _recipe('caprese-salat', 'Caprese salát')
        term, how = match_demand_term(r, self.terms, {})
        self.assertEqual((term, how), (None, ''))

    def test_no_match_is_blank(self):
        r = _recipe('pad-thai', 'Pad Thai')
        self.assertEqual(match_demand_term(r, self.terms, {}), (None, ''))
```

- [ ] **Step 2: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_demand_map`
Expected: all pass if Task 1's matcher is right. If `test_name_match_prefers_the_higher_demand_term` fails because "Hovězí guláš" also strict-matches "segedínský guláš" (it should not: 1 of 2 significant words = 0.5 < 0.6), fix the matcher, not the test.

- [ ] **Step 3: Commit**

```bash
git add diet_planner/tests/test_demand_map.py
git commit -m "test(demand): pin override, alias, category and no-match behaviour"
```

---

### Task 3: Model fields and migration

**Files:**
- Modify: `diet_planner/models/curated.py` (after `quality_score`, before `shopping_difficulty`)
- Create: `diet_planner/migrations/0039_demand_fields.py`
- Test: `diet_planner/tests/test_attach_demand_terms.py`

- [ ] **Step 1: Write the failing test**

```python
"""attach_demand_terms: copies the demand map onto CuratedRecipe rows."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, name_cs, **kw):
    defaults = dict(
        slug=slug, name_cs=name_cs, meal_types=['lunch', 'dinner'], ingredients=[], instructions=[],
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class DemandFieldsTests(TestCase):
    def test_new_rows_carry_null_demand_fields(self):
        r = _recipe('x', 'X')
        self.assertEqual(r.demand_term, '')
        self.assertIsNone(r.demand_score)
        self.assertIsNone(r.demand_peak_month)
        self.assertIsNone(r.owner_rating)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_attach_demand_terms`
Expected: `AttributeError: 'CuratedRecipe' object has no attribute 'demand_term'`

- [ ] **Step 3: Add the fields**

In `diet_planner/models/curated.py`, directly after the `quality_score` field:

```python
    # --- Demand (see docs/superpowers/specs/2026-09-09-demand-ranking-design.md) --
    # Denormalised from data/demand_map_cz.yaml by `attach_demand_terms`; ranking
    # reads these per slot and must not join the YAML at request time.
    demand_term = models.CharField(
        max_length=120, blank=True, default='', db_index=True,
        help_text="Demand-map term this recipe serves ('' = no measurable demand)",
    )
    demand_score = models.FloatField(
        null=True, blank=True,
        help_text="Search demand relative to guláš = 100, copied at attach time",
    )
    demand_peak_month = models.SmallIntegerField(
        null=True, blank=True, help_text="Month (1-12) the dish is searched most",
    )
    owner_rating = models.SmallIntegerField(
        null=True, blank=True,
        help_text="Owner's 1-5 appeal rating; breaks ties between recipes of the same dish",
    )
```

- [ ] **Step 4: Create the migration**

Run: `GEMINI_API_KEY=dummy python3 manage.py makemigrations diet_planner -n demand_fields`
Expected: `diet_planner/migrations/0039_demand_fields.py` with four `AddField` operations depending on `0038_dish_family_side_options`. Open it and confirm nothing else was picked up.

- [ ] **Step 5: Run the test to verify it passes**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_attach_demand_terms`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/models/curated.py diet_planner/migrations/0039_demand_fields.py diet_planner/tests/test_attach_demand_terms.py
git commit -m "feat(demand): demand_term/score/peak_month and owner_rating on CuratedRecipe"
```

---

### Task 4: `attach_demand_terms` command

**Files:**
- Create: `diet_planner/management/commands/attach_demand_terms.py`
- Test: `diet_planner/tests/test_attach_demand_terms.py`

- [ ] **Step 1: Write the failing tests** (append to the test file)

```python
import json
import tempfile
from pathlib import Path

import yaml


def _write_map(path, terms):
    path.write_text(yaml.safe_dump({'anchor': 'guláš', 'terms': terms}, allow_unicode=True), encoding='utf-8')


class AttachDemandTermsTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.map_path = self.tmp / 'map.yaml'
        self.ovr_path = self.tmp / 'overrides.yaml'
        _write_map(self.map_path, [
            {'term': 'guláš', 'demand': 100.0, 'kind': 'dish', 'slot': 'main', 'peak_month': None},
            {'term': 'lečo', 'demand': 19.8, 'kind': 'dish', 'slot': 'main', 'peak_month': 8},
            {'term': 'salát', 'demand': 192.8, 'kind': 'category', 'slot': 'light'},
        ])
        self.ovr_path.write_text('domaci-leco: lečo\n', encoding='utf-8')
        self.gulas = _recipe('hovezi-gulas', 'Hovězí guláš')
        self.leco = _recipe('domaci-leco', 'Základ na lečo')   # only the override can attach this
        self.salad = _recipe('caprese-salat', 'Caprese salát')
        self.other = _recipe('pad-thai', 'Pad Thai')

    def _run(self, *args):
        out = StringIO()
        call_command('attach_demand_terms', '--map', str(self.map_path), '--overrides', str(self.ovr_path), *args, stdout=out)
        for r in (self.gulas, self.leco, self.salad, self.other):
            r.refresh_from_db()
        return out.getvalue()

    def test_attaches_by_name_and_override_and_leaves_others_blank(self):
        out = self._run()
        self.assertEqual((self.gulas.demand_term, self.gulas.demand_score, self.gulas.demand_peak_month), ('guláš', 100.0, None))
        self.assertEqual((self.leco.demand_term, self.leco.demand_score, self.leco.demand_peak_month), ('lečo', 19.8, 8))
        self.assertEqual(self.salad.demand_term, '')     # category rows never attach
        self.assertEqual(self.other.demand_term, '')
        self.assertIn('hovezi-gulas', out)                # tier-2 attaches are listed for review
        self.assertIn('attached=2', out)

    def test_dry_run_writes_nothing(self):
        out = self._run('--dry-run')
        self.assertEqual(self.gulas.demand_term, '')
        self.assertIn('attached=2', out)

    def test_rerun_is_idempotent_and_clears_a_term_that_no_longer_matches(self):
        self._run()
        _write_map(self.map_path, [{'term': 'lečo', 'demand': 19.8, 'kind': 'dish', 'slot': 'main', 'peak_month': 8}])
        self._run()
        self.assertEqual(self.gulas.demand_term, '')
        self.assertIsNone(self.gulas.demand_score)
        self.assertEqual(self.leco.demand_term, 'lečo')

    def test_ratings_json_sets_owner_rating(self):
        ratings = self.tmp / 'ratings.json'
        ratings.write_text(json.dumps([{'slug': 'hovezi-gulas', 'score': 5}, {'slug': 'unknown', 'score': 1}]), encoding='utf-8')
        out = self._run('--ratings', str(ratings))
        self.assertEqual(self.gulas.owner_rating, 5)
        self.assertIsNone(self.other.owner_rating)
        self.assertIn('ratings=1', out)
```

- [ ] **Step 2: Run to verify they fail**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_attach_demand_terms`
Expected: `CommandError: Unknown command: 'attach_demand_terms'`

- [ ] **Step 3: Write the command**

`diet_planner/management/commands/attach_demand_terms.py`:

```python
"""Copy the demand map onto CuratedRecipe rows (all statuses).

Idempotent: every run recomputes every row, so a recipe whose term vanished
from the map goes back to blank. Tier-2 (name) attaches are printed so the
owner can pin mistakes into data/demand_overrides.yaml and re-run.
"""
import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import CuratedRecipe
from diet_planner.services.demand_map import (
    DEFAULT_MAP, DEFAULT_OVERRIDES, load_demand_map, load_overrides, match_demand_term,
)


class Command(BaseCommand):
    help = 'Attach demand terms, scores and peak months to curated recipes.'

    def add_arguments(self, parser):
        parser.add_argument('--map', default=str(DEFAULT_MAP))
        parser.add_argument('--overrides', default=str(DEFAULT_OVERRIDES))
        parser.add_argument('--ratings', default=None,
                            help='JSON list of {slug, score}; sets owner_rating (1-5).')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        terms = load_demand_map(Path(options['map']))
        overrides = load_overrides(Path(options['overrides']))
        dry = options['dry_run']

        ratings = {}
        if options['ratings']:
            p = Path(options['ratings'])
            if not p.exists():
                raise CommandError(f'ratings file not found: {p}')
            for row in json.loads(p.read_text(encoding='utf-8')):
                score = int(row.get('score') or 0)
                if row.get('slug') and 1 <= score <= 5:
                    ratings[row['slug']] = score

        how_counts = Counter()
        attached = changed = rated = 0
        for recipe in CuratedRecipe.objects.all().order_by('slug'):
            term, how = match_demand_term(recipe, terms, overrides)
            how_counts[how or 'none'] += 1
            new = dict(
                demand_term=term.term if term else '',
                demand_score=term.demand if term else None,
                demand_peak_month=term.peak_month if term else None,
            )
            if recipe.slug in ratings:
                new['owner_rating'] = ratings[recipe.slug]
                rated += 1
            if term:
                attached += 1
                if how == 'name':
                    self.stdout.write(f"  {recipe.slug:<48} -> {term.term}  ({term.demand:.0f})")
            diff = {k: v for k, v in new.items() if getattr(recipe, k) != v}
            if diff:
                changed += 1
                if not dry:
                    for k, v in diff.items():
                        setattr(recipe, k, v)
                    recipe.save(update_fields=list(diff))

        self.stdout.write(self.style.SUCCESS(
            f"{'[dry-run] ' if dry else ''}recipes={CuratedRecipe.objects.count()} attached={attached} "
            f"by_override={how_counts['override']} by_name={how_counts['name']} "
            f"blank={how_counts['none']} changed={changed} ratings={rated}"
        ))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_attach_demand_terms`
Expected: `Ran 5 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/attach_demand_terms.py diet_planner/tests/test_attach_demand_terms.py
git commit -m "feat(demand): attach_demand_terms command with overrides, dry-run and ratings import"
```

---

### Task 5: Ranking terms in `score_recipe`

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py` (constants near line 452; body of `score_recipe` between the prompt-fit block and the ingredient-reuse block)
- Test: `diet_planner/tests/test_demand_ranking.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Demand terms in score_recipe: demand beats reuse, wanted hits beat demand,
season only in window, owner rating only breaks near-ties, blank scores 0."""
from unittest import mock

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services.prompt_facets import PromptFacets
from diet_planner.services.recipe_retrieval import (
    _DEMAND_WEIGHT, _SAMPLING_WINDOW, _SEASON_BONUS, score_recipe,
)


def _recipe(slug, canonicals, **kw):
    defaults = dict(
        name_cs=slug, slug=slug, meal_types=['lunch', 'dinner'], cuisine='czech',
        dietary_tags=[], status=CuratedRecipe.Status.PUBLISHED,
        ingredients=[{'name': c, 'canonical': c, 'quantity': 100, 'unit': 'g'} for c in canonicals],
        instructions=[{'text': 'cook'}], base_nutrition={'calories': 500},
        source_url='https://example.com/r', source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


KW = dict(used_recipe_ids=set(), used_cuisines=[])


class DemandTermTests(TestCase):
    def test_blank_demand_scores_exactly_as_before(self):
        a = _recipe('a', ['onion'])
        self.assertEqual(score_recipe(a, **KW), score_recipe(a, **KW))
        self.assertEqual(score_recipe(a, **KW), 0.0)

    def test_demand_beats_maximal_ingredient_reuse(self):
        wanted = _recipe('gulas', ['beef'], demand_term='guláš', demand_score=100.0)
        overlap = _recipe('leco', ['onion', 'pepper', 'tomato', 'egg', 'sausage'] + [f'c{i}' for i in range(10)])
        kw = dict(KW, used_canonicals={'onion', 'pepper', 'tomato', 'egg', 'sausage'} | {f'c{i}' for i in range(10)})
        self.assertGreater(score_recipe(wanted, **kw), score_recipe(overlap, **kw))

    def test_wanted_hit_still_beats_top_demand(self):
        from diet_planner.models import CanonicalIngredient
        CanonicalIngredient.objects.update_or_create(slug='salmon', defaults=dict(name='salmon', name_cs='losos', category=CanonicalIngredient.Category.FISH))
        popular = _recipe('gulas', ['beef'], demand_term='guláš', demand_score=100.0)
        asked = _recipe('losos', ['salmon'])
        kw = dict(KW, facets=PromptFacets(wanted_ingredients={'losos'}))
        self.assertGreater(score_recipe(asked, **kw), score_recipe(popular, **kw))

    def test_demand_is_log_scaled(self):
        top = _recipe('a', [], demand_term='guláš', demand_score=100.0)
        mid = _recipe('b', [], demand_term='lečo', demand_score=20.0)
        low = _recipe('c', [], demand_term='x', demand_score=1.0)
        s_top, s_mid, s_low = (score_recipe(r, **KW) for r in (top, mid, low))
        self.assertAlmostEqual(s_top, _DEMAND_WEIGHT, places=6)
        self.assertGreater(s_mid, s_low)
        self.assertGreater(s_mid, _DEMAND_WEIGHT * 0.5)   # 20 of 100 still reads as "wanted"

    def test_season_bonus_only_inside_the_window(self):
        kapr = _recipe('kapr', [], demand_term='kapr', demand_score=50.0, demand_peak_month=12)
        with mock.patch('diet_planner.services.recipe_retrieval._current_month', return_value=12):
            in_peak = score_recipe(kapr, **KW)
        with mock.patch('diet_planner.services.recipe_retrieval._current_month', return_value=1):
            adjacent = score_recipe(kapr, **KW)
        with mock.patch('diet_planner.services.recipe_retrieval._current_month', return_value=6):
            off = score_recipe(kapr, **KW)
        self.assertAlmostEqual(in_peak - off, _SEASON_BONUS)
        self.assertAlmostEqual(adjacent - off, _SEASON_BONUS)   # ±1 month, wrapping Dec→Jan

    def test_owner_rating_moves_less_than_the_sampling_window(self):
        loved = _recipe('a', [], demand_term='guláš', demand_score=100.0, owner_rating=5)
        meh = _recipe('b', [], demand_term='guláš', demand_score=100.0, owner_rating=1)
        unrated = _recipe('c', [], demand_term='guláš', demand_score=100.0)
        s_loved, s_meh, s_unrated = (score_recipe(r, **KW) for r in (loved, meh, unrated))
        self.assertGreater(s_loved, s_unrated)
        self.assertGreater(s_unrated, s_meh)
        self.assertLessEqual(s_loved - s_meh, 2 * _SAMPLING_WINDOW)
        self.assertLessEqual(abs(s_loved - s_unrated), _SAMPLING_WINDOW)
```

- [ ] **Step 2: Run to verify they fail**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_demand_ranking`
Expected: `ImportError: cannot import name '_DEMAND_WEIGHT'`

- [ ] **Step 3: Add the constants and helper** (next to `_RECENT_SERVE_PENALTY`, around line 457)

```python
# Demand: what CZ/SK households search for (data/demand_map_cz.yaml, copied
# onto CuratedRecipe by attach_demand_terms). Log-scaled so guláš (100),
# svíčková (58) and lečo (20) all read as "wanted"; capped at the anchor.
# Sits BELOW _WANTED_HIT_WEIGHT (what the user asked for still wins) and
# ABOVE the ingredient-reuse cap (6.0): a wanted dish beats a cheap overlap,
# which reverses the mechanism that served lečo twice a day.
_DEMAND_WEIGHT = 8.0
# Peak month ±1: kapr in December, lečo in August.
_SEASON_BONUS = 2.0
# Owner's 1–5 rating, centred on 3: ±1 at most, i.e. inside _SAMPLING_WINDOW,
# so it only ever decides between near-tied recipes of the same dish.
_OWNER_RATING_STEP = 0.5


def _current_month() -> int:
    from django.utils import timezone
    return timezone.localdate().month


def _demand_terms(recipe: CuratedRecipe) -> float:
    score = 0.0
    demand = getattr(recipe, 'demand_score', None)
    if demand:
        score += _DEMAND_WEIGHT * math.log1p(min(demand, 100.0)) / math.log1p(100.0)
        peak = getattr(recipe, 'demand_peak_month', None)
        if peak:
            month = _current_month()
            if min(abs(month - peak), 12 - abs(month - peak)) <= 1:
                score += _SEASON_BONUS
    rating = getattr(recipe, 'owner_rating', None)
    if rating:
        score += _OWNER_RATING_STEP * (rating - 3)
    return score
```

Add `import math` to the module imports (after `import logging`).

- [ ] **Step 4: Call it from `score_recipe`**

Between the prompt-fit block (`if facets is not None: ...`) and the ingredient-reuse block (`if used_canonicals:`), insert:

```python
    # Demand, season and the owner's tiebreak — see _DEMAND_WEIGHT.
    score += _demand_terms(recipe)
```

Also update the comment above `_SAMPLING_WINDOW` (line ~468) to list `demand (up to 8, log)` among the deliberate orderings.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_demand_ranking diet_planner.tests.test_recipe_ranking diet_planner.tests.test_availability_ranking`
Expected: all OK. If `test_wanted_hit_still_beats_top_demand` fails, the wanted matcher did not resolve `losos`; check the canonical was created with category FISH.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_demand_ranking.py
git commit -m "feat(ranking): demand, season and owner-rating terms in score_recipe"
```

---

### Task 6: Attach on curation

**Files:**
- Modify: `diet_planner/management/commands/build_curated_recipes.py` (the success branch where `result.recipe` is saved, before the `Done.` summary)
- Test: `diet_planner/tests/test_attach_demand_terms.py`

- [ ] **Step 1: Write the failing test** (append)

```python
from diet_planner.services.demand_map import DemandTerm, match_demand_term, attach_demand_term


class AttachSingleRecipeTests(TestCase):
    def test_attach_demand_term_writes_the_fields_for_one_recipe(self):
        r = _recipe('svickova-na-smetane', 'Svíčková na smetaně')
        terms = {'svíčková': DemandTerm('svíčková', 58.1, 'dish', 'main', peak_month=12)}
        attach_demand_term(r, terms, {})
        r.refresh_from_db()
        self.assertEqual((r.demand_term, r.demand_score, r.demand_peak_month), ('svíčková', 58.1, 12))
```

- [ ] **Step 2: Run to verify it fails**

Expected: `ImportError: cannot import name 'attach_demand_term'`

- [ ] **Step 3: Add the service function** (append to `diet_planner/services/demand_map.py`)

```python
def attach_demand_term(recipe, terms: Dict[str, DemandTerm], overrides: Dict[str, str]) -> Optional[DemandTerm]:
    """Write the three demand fields for one saved recipe. Used by curation so
    a newly acquired dish is scored before promotion."""
    term, _ = match_demand_term(recipe, terms, overrides)
    recipe.demand_term = term.term if term else ''
    recipe.demand_score = term.demand if term else None
    recipe.demand_peak_month = term.peak_month if term else None
    recipe.save(update_fields=['demand_term', 'demand_score', 'demand_peak_month'])
    return term
```

- [ ] **Step 4: Call it from curation**

In `build_curated_recipes.py`, at the top of `handle` after the options are read:

```python
        from diet_planner.services.demand_map import attach_demand_term, load_demand_map, load_overrides
        demand_terms, demand_overrides = load_demand_map(), load_overrides()
```

and in the success branch, right after the recipe is persisted (where `curated += 1` is counted):

```python
                attach_demand_term(result.recipe, demand_terms, demand_overrides)
```

Read the surrounding code first: the success branch references `result.recipe`; if the attribute is named differently, use the saved instance the branch already has.

- [ ] **Step 5: Run the tests**

Run: `GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_attach_demand_terms diet_planner.tests.test_build_curated_recipes`
Expected: OK (the curation tests mock the LLM; if they construct `CuratedRecipe` rows directly, the attach is a no-op on names that match nothing).

- [ ] **Step 6: Commit**

```bash
git add diet_planner/services/demand_map.py diet_planner/management/commands/build_curated_recipes.py diet_planner/tests/test_attach_demand_terms.py
git commit -m "feat(curation): attach the demand term when a recipe is curated"
```

---

### Task 7: Runbook and full suite

**Files:**
- Create: `docs/demand-ranking-ops.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Demand ranking — operations

## What it is
`diet_planner/data/demand_map_cz.yaml` holds search demand per dish (Google Trends,
CZ + 0.5×SK, guláš = 100, 12 months). `attach_demand_terms` copies each recipe's
term, score and peak month onto `CuratedRecipe`; `score_recipe` adds up to +8
(log demand), +2 (peak month ±1) and ±1 (owner rating, same-dish tiebreak).

## Apply on prod (after deploy)
1. `python manage.py attach_demand_terms --dry-run` — read the by-name attaches.
2. Wrong attach? Add `slug: term` to `diet_planner/data/demand_overrides.yaml`,
   commit, deploy, repeat step 1.
3. `python manage.py attach_demand_terms` (add `--ratings ratings.json` with the
   export from the rating artifact: a list of `{slug, score}`).
4. `python manage.py selection_distribution_report` before and after.

## Refresh the map
Re-run the Trends batch (scripts in the 2026-09-09 session scratchpad, or
rebuild from `docs/superpowers/specs/2026-09-09-demand-ranking-design.md`),
regenerate the YAML, commit, deploy, run step 3. Quarterly is enough; the
peak months do not move.

## Kill switch
`attach_demand_terms --map /dev/null` is refused (no terms); instead set every
row blank with an empty map file containing `terms: []`, which scores exactly
as before the feature.
```

- [ ] **Step 2: Run the full backend suite**

Run: `GEMINI_API_KEY=dummy timeout 580 python3 manage.py test diet_planner --parallel 4 2>&1 | grep -E "^(OK|FAILED|Ran )"`
Expected: `Ran 9xx tests ... OK`

- [ ] **Step 3: Commit and open the PR**

```bash
git add docs/demand-ranking-ops.md
git commit -m "docs(demand): ranking runbook"
git push -u origin feat/demand-ranking
gh pr create --base develop --title "feat(ranking): demand-driven selection with seasonality and owner tiebreak"
```

---

## Self-review

- **Spec coverage:** YAML (T1), fields + migration (T3), attach command with overrides, dry-run, ratings, idempotence (T4), ranking constants and sizes (T5), curation hook (T6), testing list (T2/T4/T5), rollout (T7 runbook). The spec's `selection_distribution_report` check is a prod step in the runbook.
- **Placeholders:** none; every step has code or an exact command.
- **Type consistency:** `DemandTerm(term, demand, kind, slot, peak_month, aliases)` is used positionally in tests exactly in that order; `match_demand_term(recipe, terms, overrides) -> (DemandTerm | None, how)`; `attach_demand_term(recipe, terms, overrides)`; fields `demand_term`, `demand_score`, `demand_peak_month`, `owner_rating` everywhere.
