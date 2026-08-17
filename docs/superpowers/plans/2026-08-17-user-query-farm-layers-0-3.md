# User Query Farm — Layers 0-3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure how much of real Czech food demand the recipe corpus can actually serve, repeatably and off-prod.

**Architecture:** Four layers. Layer 0 mirrors the prod corpus locally. Layer 1 scrapes ranked dish demand from the two Czech recipe sites the corpus already credits into a committed YAML snapshot. Layer 2 reduces real user prompts to scrubbed phrasing templates. Layer 3 crosses demand × phrasing × persona into simulated queries, runs them through the real retrieval path with no DB writes, and reports per-cell pools, which gate killed each query, and demand-weighted coverage.

**Tech Stack:** Django 5.1 management commands, `requests` + `beautifulsoup4` + `lxml` (already in `requirements.txt`), PyYAML, pytest.

**Spec:** `docs/superpowers/specs/2026-08-17-user-query-farm-design.md`

**Deliberately deferred from the spec's Layer 1:** the pytrends `--with-trends`
weighting layer. The `trend_score` field stays in the snapshot schema as `null`.
Ranking position already orders demand; trend weighting only re-orders it, and
re-ordering a list whose base coverage numbers nobody has seen yet is premature.
Add it once the first report exists and the ordering is visibly wrong. The other
Layer 1 source, Search Console, contributes nothing until the domain is verified
and traffic accumulates — that is an ops task, not a code task.

**Test runner (every test step in this plan):**
```bash
docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest <target> -q"
```
`pytest` is NOT installed in the image; the `pip install` prefix is required every time.

**Scratch dir:** use `/tmp/claude-0/-opt-llmDietPlanner/<session>/scratchpad` or any path outside the repo for corpus dumps. The corpus dump must never be committed.

---

## File Structure

| File | Responsibility |
|---|---|
| `diet_planner/management/commands/dump_curated_corpus.py` | Read-only export of published recipes (run on prod) |
| `diet_planner/management/commands/load_curated_corpus.py` | Import that export into a local DB |
| `diet_planner/services/demand_index.py` | Pure parsing + enrichment of ranked dish lists. No network, no Django ORM writes |
| `diet_planner/management/commands/build_demand_index.py` | Fetches pages, calls the parsers, writes the committed snapshot |
| `diet_planner/data/demand_index_cz.yaml` | Committed demand snapshot the farm reads |
| `diet_planner/services/prompt_templates.py` | Scrub real prompts into safe templates. Pure |
| `diet_planner/management/commands/export_goal_prompts.py` | Reads `DietaryGoal.prompt`, writes templates YAML |
| `diet_planner/data/prompt_templates_cz.yaml` | Committed phrasing templates (never raw prompts) |
| `diet_planner/services/user_simulation.py` | Query generation + gate funnel + coverage scoring. Pure except for ORM reads |
| `diet_planner/management/commands/simulate_coverage.py` | Runs the farm, prints the report |
| `diet_planner/tests/fixtures/demand/*.html` | Saved ranking pages; parsers are tested against these, never the live sites |

---

### Task 1: Corpus mirror

**Files:**
- Create: `diet_planner/management/commands/dump_curated_corpus.py`
- Create: `diet_planner/management/commands/load_curated_corpus.py`
- Test: `diet_planner/tests/test_corpus_mirror.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_corpus_mirror.py`:

```python
"""Round-trip the published corpus so the farm can run off-prod."""
import json
import os
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, status=CuratedRecipe.Status.PUBLISHED, **kw):
    defaults = dict(
        slug=slug, name_cs=slug, meal_types=['dinner'], base_servings=2,
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=status,
        ingredients=[{'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'}],
        instructions=[{'text': 'Uvařte.'}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class CorpusMirrorTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, 'corpus.json')

    def test_dump_writes_only_published(self):
        _recipe('published-one')
        _recipe('draft-one', status=CuratedRecipe.Status.DRAFT)
        out = StringIO()
        call_command('dump_curated_corpus', '--output', self.path, stdout=out)
        payload = json.loads(open(self.path, encoding='utf-8').read())
        slugs = [row['fields']['slug'] for row in payload]
        self.assertEqual(slugs, ['published-one'])
        self.assertIn('dumped=1', out.getvalue())

    def test_load_restores_a_deleted_corpus(self):
        _recipe('published-one', name_cs='Svíčková')
        call_command('dump_curated_corpus', '--output', self.path, stdout=StringIO())
        CuratedRecipe.objects.all().delete()

        call_command('load_curated_corpus', '--input', self.path, stdout=StringIO())
        restored = CuratedRecipe.objects.get(slug='published-one')
        self.assertEqual(restored.name_cs, 'Svíčková')
        self.assertEqual(restored.status, CuratedRecipe.Status.PUBLISHED)

    def test_load_drops_the_chat_user_link(self):
        """chat_user points at a prod User row that does not exist locally;
        keeping the id would break the FK on load."""
        from django.contrib.auth import get_user_model
        user = get_user_model().objects.create_user(
            username='someone', email='someone@example.com', password='x')
        _recipe('published-one', chat_user=user)
        call_command('dump_curated_corpus', '--output', self.path, stdout=StringIO())
        CuratedRecipe.objects.all().delete()
        user.delete()

        call_command('load_curated_corpus', '--input', self.path, stdout=StringIO())
        self.assertIsNone(CuratedRecipe.objects.get(slug='published-one').chat_user_id)

    def test_load_flush_replaces_existing_rows(self):
        _recipe('published-one')
        call_command('dump_curated_corpus', '--output', self.path, stdout=StringIO())
        _recipe('stale-local-row')

        call_command('load_curated_corpus', '--input', self.path, '--flush',
                     stdout=StringIO())
        self.assertEqual(
            sorted(CuratedRecipe.objects.values_list('slug', flat=True)),
            ['published-one'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_corpus_mirror.py -q"`

Expected: FAIL — `CommandError: Unknown command: 'dump_curated_corpus'`

- [ ] **Step 3: Write the dump command**

Create `diet_planner/management/commands/dump_curated_corpus.py`:

```python
"""Export published curated recipes so the farm can run against a local mirror.

Read-only: this command never writes to the database it reads. Run it against
prod, load the file locally with `load_curated_corpus`. The output is NOT
committed — it is a few MB of third-party-derived recipe text and it is
regenerable at any time.
"""
from django.core import serializers
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = 'Dump published CuratedRecipe rows to JSON (read-only).'

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True, help='Destination .json path')
        parser.add_argument('--status', default=CuratedRecipe.Status.PUBLISHED)

    def handle(self, *args, **options):
        qs = CuratedRecipe.objects.filter(status=options['status']).order_by('id')
        count = qs.count()
        with open(options['output'], 'w', encoding='utf-8') as fh:
            fh.write(serializers.serialize('json', qs.iterator()))
        self.stdout.write(self.style.SUCCESS(
            f'dumped={count} -> {options["output"]}'))
```

- [ ] **Step 4: Write the load command**

Create `diet_planner/management/commands/load_curated_corpus.py`:

```python
"""Load a `dump_curated_corpus` export into the local database.

Drops `chat_user` on the way in: it points at a prod User row that does not
exist here, and the farm never needs it.
"""
from django.core import serializers
from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = 'Load curated recipes from a dump_curated_corpus JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('--input', required=True, help='Path to the .json export')
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete existing CuratedRecipe rows first (exact mirror)')

    def handle(self, *args, **options):
        with open(options['input'], encoding='utf-8') as fh:
            payload = fh.read()

        loaded = 0
        with transaction.atomic():
            if options['flush']:
                CuratedRecipe.objects.all().delete()
            for wrapper in serializers.deserialize('json', payload):
                wrapper.object.chat_user = None
                wrapper.save()
                loaded += 1

        self.stdout.write(self.style.SUCCESS(f'loaded={loaded}'))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_corpus_mirror.py -q"`

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/management/commands/dump_curated_corpus.py \
        diet_planner/management/commands/load_curated_corpus.py \
        diet_planner/tests/test_corpus_mirror.py
git commit -m "feat(farm): mirror the published corpus off-prod"
```

**Ops note (not a code step):** getting the prod corpus locally needs prod DB read access, which this repo does not hold — `DATABASE_URL` is a DO secret. Two routes, in order of preference:
1. Run `dump_curated_corpus` locally with `DATABASE_URL` pointed at the Supabase **read-only** connection string, then `load_curated_corpus` against the local DB.
2. Run it on prod through the DO console harness (`/tmp/do_exec.py`, see the `prod-console-exec-harness` notes) writing to `/tmp`, then copy the file down.
Ask the owner for the Supabase read-only string before attempting route 2.

---

### Task 2: Ranking parsers

**Files:**
- Create: `diet_planner/services/demand_index.py`
- Create: `diet_planner/tests/fixtures/demand/toprecepty-top-star.html`
- Create: `diet_planner/tests/fixtures/demand/recepty-oblibene.html`
- Test: `diet_planner/tests/test_demand_index.py`

- [ ] **Step 1: Capture the fixtures**

The parsers are tested against saved HTML, never the live sites.

```bash
mkdir -p diet_planner/tests/fixtures/demand
curl -sL -A "Mozilla/5.0 (compatible; VartoResearch/1.0)" \
  https://www.toprecepty.cz/top-star.php \
  -o diet_planner/tests/fixtures/demand/toprecepty-top-star.html
curl -sL -A "Mozilla/5.0 (compatible; VartoResearch/1.0)" \
  https://www.recepty.cz/recept/oblibene \
  -o diet_planner/tests/fixtures/demand/recepty-oblibene.html
grep -c 'href="/recept/' diet_planner/tests/fixtures/demand/toprecepty-top-star.html
```

Expected: the `grep -c` prints a number well above 15. If it prints 0, the page shape changed — open the file and find the anchor pattern before continuing.

Both sites' `robots.txt` allow these paths (only form/print/`?do=` URLs are disallowed). Keep the descriptive User-Agent.

- [ ] **Step 2: Write the failing test**

Create `diet_planner/tests/test_demand_index.py`:

```python
"""Parsing ranked dish lists into demand terms. Fixtures only — no network."""
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from diet_planner.services.demand_index import DemandTerm, parse_ranking

FIXTURES = Path(settings.BASE_DIR) / 'diet_planner' / 'tests' / 'fixtures' / 'demand'


class ParseRankingTests(TestCase):
    def _html(self, name):
        return (FIXTURES / name).read_text(encoding='utf-8')

    def test_toprecepty_yields_ranked_terms(self):
        terms = parse_ranking(self._html('toprecepty-top-star.html'),
                              source='toprecepty.cz', category='global')
        self.assertGreaterEqual(len(terms), 15)
        self.assertEqual(terms[0].rank, 1)
        self.assertEqual(terms[1].rank, 2)
        self.assertTrue(all(isinstance(t, DemandTerm) for t in terms))
        self.assertTrue(all(t.source == 'toprecepty.cz' for t in terms))
        self.assertTrue(all(t.category == 'global' for t in terms))

    def test_terms_are_non_empty_dish_names(self):
        terms = parse_ranking(self._html('toprecepty-top-star.html'),
                              source='toprecepty.cz', category='global')
        for t in terms[:15]:
            self.assertGreater(len(t.term), 3)
            self.assertNotIn('\n', t.term)

    def test_recepty_cz_parses_with_the_same_function(self):
        terms = parse_ranking(self._html('recepty-oblibene.html'),
                              source='recepty.cz', category='global')
        self.assertGreaterEqual(len(terms), 10)

    def test_duplicate_links_collapse_and_ranks_stay_dense(self):
        html = '''
          <div><a href="/recept/1-gulas/">Guláš</a></div>
          <div><a href="/recept/1-gulas/">Guláš</a></div>
          <div><a href="/recept/2-svickova/">Svíčková</a></div>
        '''
        terms = parse_ranking(html, source='x', category='global')
        self.assertEqual([(t.term, t.rank) for t in terms],
                         [('Guláš', 1), ('Svíčková', 2)])

    def test_navigation_links_are_ignored(self):
        """Only /recept/<id>-<slug>/ links are dishes; category and paging
        links share the page and must not become demand terms."""
        html = '''
          <a href="/kategorie/46-maso/">Maso</a>
          <a href="/recept/9-kureci-rizek/">Kuřecí řízek</a>
          <a href="/vsechny_recepty.php">Všechny recepty</a>
        '''
        terms = parse_ranking(html, source='x', category='global')
        self.assertEqual([t.term for t in terms], ['Kuřecí řízek'])

    def test_empty_html_yields_nothing_rather_than_raising(self):
        self.assertEqual(parse_ranking('', source='x', category='global'), [])
```

- [ ] **Step 3: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_demand_index.py -q"`

Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.demand_index'`

- [ ] **Step 4: Write the parser**

Create `diet_planner/services/demand_index.py`:

```python
"""What Czechs actually cook, harvested from public recipe-site rankings.

Pure functions: parsing and enrichment only. Fetching lives in the
`build_demand_index` command so this module stays testable against fixtures.

Why rankings at all: the corpus has only ever been measured against itself
("458 published, 164 fail the shopping bar"). Demand data is what turns that
into "of the dishes people look for, we can serve N".
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup

#: Recipe detail links on both sites: /recept/<id>-<slug>/
_RECIPE_HREF = re.compile(r'^/recept/\d+[-/]')


@dataclass(frozen=True)
class DemandTerm:
    term: str
    rank: int
    source: str
    category: str
    rating: Optional[float] = None


def parse_ranking(html: str, *, source: str, category: str) -> List[DemandTerm]:
    """Ranked dish names from a listing page, best first.

    Rank is positional: these pages are already sorted, and the rank badges are
    images on only the first few items. Duplicate links (thumbnail + title
    anchor pointing at the same recipe) collapse to their first occurrence so
    ranks stay dense.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, 'lxml')
    seen_hrefs = set()
    terms: List[DemandTerm] = []

    for anchor in soup.find_all('a', href=True):
        href = anchor['href']
        if not _RECIPE_HREF.match(href):
            continue
        if href in seen_hrefs:
            continue
        name = ' '.join(anchor.get_text(' ', strip=True).split())
        if len(name) <= 3:
            continue  # image-only anchors carry no title
        seen_hrefs.add(href)
        terms.append(DemandTerm(
            term=name, rank=len(terms) + 1, source=source, category=category))

    return terms
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_demand_index.py -q"`

Expected: `6 passed`. If the two fixture-backed tests fail on count, open the fixture and adjust `_RECIPE_HREF` to the observed href shape — do not weaken the "navigation links are ignored" test to compensate.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/services/demand_index.py diet_planner/tests/test_demand_index.py \
        diet_planner/tests/fixtures/demand/
git commit -m "feat(farm): parse ranked dish demand from CZ recipe sites"
```

---

### Task 3: Enrich terms with slot scope and canonicals

Global rankings on both sites are dominated by sweet baking — the observed
toprecepty all-time top 15 is mostly perník, buchty, bublanina, langoše. A meal
planner has no dessert slot, so counting "we cannot serve perník" as a coverage
failure would be wrong. Every term therefore carries a scope, and the farm
scores only in-scope demand while reporting the rest separately.

**Files:**
- Modify: `diet_planner/services/demand_index.py`
- Test: `diet_planner/tests/test_demand_index.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_demand_index.py`:

```python
from diet_planner.services.demand_index import CATEGORY_SLOTS, enrich_term


class EnrichTermTests(TestCase):
    def setUp(self):
        from io import StringIO

        from django.core.management import call_command
        call_command('seed_canonical_ingredients', stdout=StringIO())

    def test_meat_category_maps_to_a_main_slot_and_is_in_scope(self):
        term = DemandTerm(term='Kuřecí řízek', rank=1,
                          source='toprecepty.cz', category='maso')
        row = enrich_term(term)
        self.assertEqual(row['slot_hint'], 'dinner')
        self.assertTrue(row['in_scope'])

    def test_dessert_category_is_out_of_scope(self):
        """No dessert slot exists, so this demand is reported, not scored."""
        term = DemandTerm(term='Bublanina', rank=1,
                          source='toprecepty.cz', category='moucniky')
        self.assertFalse(enrich_term(term)['in_scope'])

    def test_canonicals_are_resolved_from_the_dish_name(self):
        term = DemandTerm(term='Kuřecí řízek s bramborem', rank=1,
                          source='x', category='maso')
        self.assertIn('potato', enrich_term(term)['canonicals'])

    def test_unknown_words_do_not_break_resolution(self):
        term = DemandTerm(term='Dobětický guláš', rank=1, source='x', category='maso')
        row = enrich_term(term)
        self.assertIsInstance(row['canonicals'], list)

    def test_every_known_category_declares_a_slot(self):
        for category, slot in CATEGORY_SLOTS.items():
            self.assertTrue(slot is None or slot in
                            ('breakfast', 'lunch', 'dinner', 'snack'),
                            f'{category} declares slot {slot!r}')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_demand_index.py::EnrichTermTests -q"`

Expected: FAIL — `ImportError: cannot import name 'CATEGORY_SLOTS'`

- [ ] **Step 3: Write the enrichment**

Append to `diet_planner/services/demand_index.py`:

```python
from diet_planner.services.canonical_lookup import fold_diacritics, resolve_canonical

#: Source category -> the meal slot that demand belongs to. `None` means the
#: category has no slot in a meal plan (desserts, drinks, preserves): real
#: demand, deliberately out of scope, reported but never scored.
CATEGORY_SLOTS = {
    'global': 'dinner',
    'maso': 'dinner',
    'testoviny': 'dinner',
    'polevky': 'lunch',
    'salaty': 'lunch',
    'snidane': 'breakfast',
    'omacky': 'dinner',
    'moucniky': None,
    'dezerty': None,
    'napoje': None,
    'zavarovani': None,
}

_WORD = re.compile(r'[^\wáčďéěíňóřšťúůýž]+', re.IGNORECASE)


def _words(text: str) -> List[str]:
    return [w for w in _WORD.split(text.lower()) if len(w) > 2]


def enrich_term(term: DemandTerm) -> dict:
    """Add slot scope and resolved canonicals to a parsed demand term."""
    slot = CATEGORY_SLOTS.get(term.category, 'dinner')
    canonicals = []
    for word in _words(term.term):
        canonical = resolve_canonical(word)
        if canonical is not None and canonical.slug not in canonicals:
            canonicals.append(canonical.slug)

    return {
        'term': term.term,
        'rank': term.rank,
        'source': term.source,
        'category': term.category,
        'slot_hint': slot,
        'in_scope': slot is not None,
        'canonicals': canonicals,
        'folded': fold_diacritics(term.term).lower(),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_demand_index.py -q"`

Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/demand_index.py diet_planner/tests/test_demand_index.py
git commit -m "feat(farm): scope demand terms to meal slots, resolve canonicals"
```

---

### Task 4: `build_demand_index`

**Files:**
- Create: `diet_planner/management/commands/build_demand_index.py`
- Create: `diet_planner/data/demand_index_cz.yaml` (generated in step 5)
- Test: `diet_planner/tests/test_build_demand_index.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_build_demand_index.py`:

```python
"""The snapshot builder: fetch behind a flag, never write an empty index."""
import os
import tempfile
from io import StringIO
from unittest import mock

import yaml
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

_PAGE = '''
  <div><a href="/recept/1-gulas/">Hovězí guláš</a></div>
  <div><a href="/recept/2-rizek/">Kuřecí řízek</a></div>
'''


class BuildDemandIndexTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        self.path = os.path.join(tempfile.mkdtemp(), 'demand.yaml')

    def _patched_fetch(self, pages=None):
        return mock.patch(
            'diet_planner.management.commands.build_demand_index.Command._fetch',
            side_effect=lambda url: (pages or {}).get(url, _PAGE))

    def test_refresh_writes_a_snapshot(self):
        with self._patched_fetch():
            call_command('build_demand_index', '--refresh', '--output', self.path,
                         stdout=StringIO())
        payload = yaml.safe_load(open(self.path, encoding='utf-8'))
        self.assertGreaterEqual(len(payload['terms']), 2)
        self.assertIn('generated_from', payload)
        first = payload['terms'][0]
        self.assertIn('term', first)
        self.assertIn('rank', first)
        self.assertIn('in_scope', first)

    def test_without_refresh_nothing_is_fetched(self):
        """The committed snapshot is the farm's input; a plain run is a no-op
        report so CI never touches the network."""
        with self._patched_fetch() as fetch:
            call_command('build_demand_index', '--output', self.path, stdout=StringIO())
        fetch.assert_not_called()

    def test_a_dead_source_never_produces_an_empty_index(self):
        """An empty demand list would make corpus coverage look perfect."""
        with mock.patch(
                'diet_planner.management.commands.build_demand_index.Command._fetch',
                return_value='<html><body>no recipes here</body></html>'):
            with self.assertRaises(CommandError):
                call_command('build_demand_index', '--refresh', '--output', self.path,
                             stdout=StringIO())
        self.assertFalse(os.path.exists(self.path))

    def test_fetch_failure_keeps_the_previous_snapshot(self):
        with open(self.path, 'w', encoding='utf-8') as fh:
            yaml.safe_dump({'terms': [{'term': 'old', 'rank': 1}]}, fh)
        with mock.patch(
                'diet_planner.management.commands.build_demand_index.Command._fetch',
                side_effect=OSError('network down')):
            with self.assertRaises(CommandError):
                call_command('build_demand_index', '--refresh', '--output', self.path,
                             stdout=StringIO())
        kept = yaml.safe_load(open(self.path, encoding='utf-8'))
        self.assertEqual(kept['terms'][0]['term'], 'old')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_build_demand_index.py -q"`

Expected: FAIL — `CommandError: Unknown command: 'build_demand_index'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/build_demand_index.py`:

```python
"""Build the committed demand snapshot from public CZ recipe-site rankings.

Sampling is per-category on purpose. The all-time global rankings on both sites
are dominated by sweet baking (perník, buchty, bublanina), which a meal planner
has no slot for; per-category sampling is what makes lunch/dinner demand
visible at all.

The live fetch only happens under --refresh. A plain run reports what the
committed snapshot holds, so tests and CI never touch the network.
"""
from pathlib import Path
from typing import List

import requests
import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from diet_planner.services.demand_index import enrich_term, parse_ranking

DEFAULT_PATH = Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'demand_index_cz.yaml'

USER_AGENT = 'Mozilla/5.0 (compatible; VartoResearch/1.0; +https://eatalnicek.eu)'

#: (url, source, category). Categories map to meal slots in
#: demand_index.CATEGORY_SLOTS; 'moucniky' is harvested deliberately so the
#: report can show how much demand is out of scope rather than hiding it.
SOURCES = [
    ('https://www.toprecepty.cz/top-star.php', 'toprecepty.cz', 'global'),
    ('https://www.toprecepty.cz/kategorie/46-maso/', 'toprecepty.cz', 'maso'),
    ('https://www.toprecepty.cz/kategorie/16-polevky/', 'toprecepty.cz', 'polevky'),
    ('https://www.toprecepty.cz/kategorie/17-testoviny/', 'toprecepty.cz', 'testoviny'),
    ('https://www.toprecepty.cz/kategorie/27-moucniky/', 'toprecepty.cz', 'moucniky'),
    ('https://www.recepty.cz/recept/oblibene', 'recepty.cz', 'global'),
    ('https://www.recepty.cz/polevky-kucharka', 'recepty.cz', 'polevky'),
    ('https://www.recepty.cz/salaty-kucharka', 'recepty.cz', 'salaty'),
]


class Command(BaseCommand):
    help = 'Build diet_planner/data/demand_index_cz.yaml from CZ recipe rankings.'

    def add_arguments(self, parser):
        parser.add_argument('--refresh', action='store_true',
                            help='Fetch the live rankings (otherwise report only)')
        parser.add_argument('--output', default=str(DEFAULT_PATH))
        parser.add_argument('--per-source', type=int, default=40,
                            help='Keep at most this many terms per source page')

    def _fetch(self, url: str) -> str:
        response = requests.get(url, timeout=30, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        return response.text

    def handle(self, *args, **options):
        path = Path(options['output'])

        if not options['refresh']:
            if not path.exists():
                self.stdout.write(self.style.WARNING(
                    f'no snapshot at {path}; run with --refresh to build one'))
                return
            payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            terms = payload.get('terms', [])
            in_scope = sum(1 for t in terms if t.get('in_scope'))
            self.stdout.write(f'snapshot terms={len(terms)} in_scope={in_scope}')
            return

        rows: List[dict] = []
        for url, source, category in SOURCES:
            try:
                html = self._fetch(url)
            except Exception as exc:  # noqa: BLE001 - any fetch failure is fatal
                raise CommandError(
                    f'fetch failed for {url}: {exc}. Previous snapshot left untouched.')
            parsed = parse_ranking(html, source=source, category=category)
            kept = parsed[:options['per_source']]
            self.stdout.write(f'  {source} {category}: {len(kept)} terms')
            rows.extend(enrich_term(term) for term in kept)

        if not rows:
            raise CommandError(
                'every source parsed to zero terms — refusing to write an empty '
                'index, which would make corpus coverage look perfect. '
                'Check the site markup against the parser fixtures.')

        payload = {
            'generated_from': [url for url, _, _ in SOURCES],
            'note': ('Positional ranks from public listing pages. Recipe-site '
                     'demand is dish-first; a meal planner is week-first. This '
                     'is a proxy, not demand truth.'),
            'terms': rows,
        }
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
            encoding='utf-8')

        in_scope = sum(1 for r in rows if r['in_scope'])
        self.stdout.write(self.style.SUCCESS(
            f'terms={len(rows)} in_scope={in_scope} -> {path}'))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_build_demand_index.py -q"`

Expected: `4 passed`

- [ ] **Step 5: Build the real snapshot**

```bash
docker-compose run --rm web python manage.py build_demand_index --refresh
docker-compose run --rm web python manage.py build_demand_index
head -30 diet_planner/data/demand_index_cz.yaml
```

Expected: a per-source term count for all 8 sources, then `terms=<N> in_scope=<M>`.
**Read the head output.** If a source reports 0 terms its markup changed; fix
`_RECIPE_HREF` in `demand_index.py` and re-capture that fixture rather than
shipping a snapshot with a silently missing source.

- [ ] **Step 6: Commit**

```bash
git add diet_planner/management/commands/build_demand_index.py \
        diet_planner/tests/test_build_demand_index.py \
        diet_planner/data/demand_index_cz.yaml
git commit -m "feat(farm): build the committed CZ demand snapshot"
```

---

### Task 5: Prompt templates from real goals

**Files:**
- Create: `diet_planner/services/prompt_templates.py`
- Create: `diet_planner/management/commands/export_goal_prompts.py`
- Test: `diet_planner/tests/test_prompt_templates.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_prompt_templates.py`:

```python
"""Reducing real prompts to shareable templates. Nothing personal reaches git."""
from io import StringIO

import yaml
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import DietaryGoal
from diet_planner.services.prompt_templates import reduce_prompt


class ReducePromptTests(TestCase):
    def test_day_counts_become_a_placeholder(self):
        self.assertEqual(reduce_prompt('jídelníček na 5 dní'),
                         'jídelníček na {n} dní')

    def test_have_x_phrasing_is_preserved_as_a_shape(self):
        """This shape broke facet extraction in prod; the farm must keep it."""
        self.assertEqual(reduce_prompt('Mám kuřecí maso, co uvařit?'),
                         'Mám {ingredient}, co uvařit?')

    def test_an_email_makes_the_prompt_undroppable_into_a_template(self):
        self.assertIsNone(reduce_prompt('napiš mi to na rob@example.com'))

    def test_a_long_free_text_prompt_is_dropped_not_exported(self):
        self.assertIsNone(reduce_prompt(
            'ahoj jmenuji se Petr a bydlím v Brně na Kounicově 12 a chci jíst lépe'))

    def test_empty_prompt_is_dropped(self):
        self.assertIsNone(reduce_prompt(''))


class ExportGoalPromptsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='u', email='u@example.com', password='x')
        self.path = '/tmp/prompt_templates_test.yaml'

    def _goal(self, prompt):
        return DietaryGoal.objects.create(user=self.user, prompt=prompt, num_days=5)

    def test_export_writes_templates_with_counts(self):
        self._goal('jídelníček na 5 dní')
        self._goal('jídelníček na 7 dní')
        self._goal('Mám kuřecí maso, co uvařit?')

        call_command('export_goal_prompts', '--output', self.path, stdout=StringIO())
        payload = yaml.safe_load(open(self.path, encoding='utf-8'))
        by_template = {row['template']: row['observed'] for row in payload['templates']}
        self.assertEqual(by_template['jídelníček na {n} dní'], 2)
        self.assertEqual(by_template['Mám {ingredient}, co uvařit?'], 1)

    def test_unreducible_prompts_never_reach_the_file(self):
        self._goal('ahoj jmenuji se Petr a bydlím v Brně na Kounicově 12')
        call_command('export_goal_prompts', '--output', self.path, stdout=StringIO())
        raw = open(self.path, encoding='utf-8').read()
        self.assertNotIn('Petr', raw)
        self.assertNotIn('Kounicova', raw)
        self.assertNotIn('Kounicově', raw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_prompt_templates.py -q"`

Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.prompt_templates'`

- [ ] **Step 3: Write the reducer**

Create `diet_planner/services/prompt_templates.py`:

```python
"""Reduce real user prompts to reusable phrasing templates.

`DietaryGoal.prompt` is an EncryptedTextField because it is user data. Only
shapes leave this module: a prompt that does not reduce cleanly to a known
template is DROPPED, never exported. Anything else risks a name, an address or
an email landing in git.

Phrasing is the half of query realism we cannot invent. The `Mám X` shape is
the standing example: it broke facet extraction on prod precisely because no
test author wrote prompts that way.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

_EMAIL = re.compile(r'\S+@\S+')
_URL = re.compile(r'https?://\S+')

#: (pattern, template). Ordered; first match wins.
_SHAPES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'^jídelníček na \d+ dní$', re.IGNORECASE), 'jídelníček na {n} dní'),
    (re.compile(r'^jidelnicek na \d+ dni$', re.IGNORECASE), 'jídelníček na {n} dní'),
    (re.compile(r'^mám .{2,30}, co uvařit\?$', re.IGNORECASE),
     'Mám {ingredient}, co uvařit?'),
    (re.compile(r'^mám .{2,30}$', re.IGNORECASE), 'Mám {ingredient}'),
    (re.compile(r'^něco (rychlého|levného|zdravého)( na .{3,20})?$', re.IGNORECASE),
     'něco {quality}'),
    (re.compile(r'^chci (zhubnout|nabrat|jíst zdravěji)$', re.IGNORECASE),
     'chci {objective}'),
    (re.compile(r'^\w[\w\s]{2,40}$', re.IGNORECASE), '{free_short}'),
]

#: Longer than this and a free-text prompt is assumed to carry personal detail.
_MAX_FREE_TEXT = 40


def reduce_prompt(prompt: str) -> Optional[str]:
    """The template a prompt reduces to, or None when it must be dropped."""
    if not prompt:
        return None
    text = ' '.join(prompt.split())
    if _EMAIL.search(text) or _URL.search(text):
        return None

    for pattern, template in _SHAPES:
        if pattern.match(text):
            if template == '{free_short}' and len(text) > _MAX_FREE_TEXT:
                return None
            return template
    return None
```

Note the capitalisation: `Mám ...` templates are emitted capitalised regardless
of how the user typed them, which is why the patterns carry `re.IGNORECASE`
while the template strings are fixed.

- [ ] **Step 4: Write the export command**

Create `diet_planner/management/commands/export_goal_prompts.py`:

```python
"""Export real goal prompts as scrubbed phrasing templates.

Writes shapes and counts only — see services/prompt_templates for why.
"""
from collections import Counter
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.models import DietaryGoal
from diet_planner.services.prompt_templates import reduce_prompt

DEFAULT_PATH = (Path(settings.BASE_DIR) / 'diet_planner' / 'data'
                / 'prompt_templates_cz.yaml')


class Command(BaseCommand):
    help = 'Reduce real DietaryGoal prompts to committed phrasing templates.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default=str(DEFAULT_PATH))

    def handle(self, *args, **options):
        counts = Counter()
        seen = dropped = 0
        for goal in DietaryGoal.objects.all().iterator():
            seen += 1
            template = reduce_prompt(goal.prompt or '')
            if template is None:
                dropped += 1
                continue
            counts[template] += 1

        payload = {
            'note': ('Shapes only. Prompts that do not reduce to a known '
                     'template are dropped, never exported.'),
            'templates': [
                {'template': template, 'observed': n}
                for template, n in counts.most_common()
            ],
        }
        Path(options['output']).write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
            encoding='utf-8')

        self.stdout.write(self.style.SUCCESS(
            f'goals={seen} templates={len(counts)} dropped={dropped}'))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_prompt_templates.py -q"`

Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/services/prompt_templates.py \
        diet_planner/management/commands/export_goal_prompts.py \
        diet_planner/tests/test_prompt_templates.py
git commit -m "feat(farm): scrub real prompts into phrasing templates"
```

**Ops note:** running this against prod needs the same read access as Task 1.
The committed `prompt_templates_cz.yaml` is produced from prod goals; until
that access exists, the farm falls back to the persona-only phrasing in Task 6.

---

### Task 6: Query generation

**Files:**
- Create: `diet_planner/services/user_simulation.py`
- Test: `diet_planner/tests/test_user_simulation.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_user_simulation.py`:

```python
"""Crossing demand x phrasing x persona into reproducible simulated queries."""
from django.test import TestCase

from diet_planner.services.user_simulation import PERSONAS, SimulatedQuery, generate_queries

DEMAND = [
    {'term': 'Hovězí guláš', 'rank': 1, 'source': 'toprecepty.cz', 'category': 'maso',
     'slot_hint': 'dinner', 'in_scope': True, 'canonicals': ['beef'],
     'folded': 'hovezi gulas'},
    {'term': 'Bublanina', 'rank': 2, 'source': 'toprecepty.cz', 'category': 'moucniky',
     'slot_hint': None, 'in_scope': False, 'canonicals': [], 'folded': 'bublanina'},
    {'term': 'Kuřecí řízek', 'rank': 3, 'source': 'toprecepty.cz', 'category': 'maso',
     'slot_hint': 'dinner', 'in_scope': True, 'canonicals': ['chicken'],
     'folded': 'kureci rizek'},
]
TEMPLATES = [
    {'template': 'Mám {ingredient}, co uvařit?', 'observed': 4},
    {'template': 'jídelníček na {n} dní', 'observed': 11},
]


class GenerateQueriesTests(TestCase):
    def test_same_seed_gives_identical_queries(self):
        a = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=7, n=12)
        b = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=7, n=12)
        self.assertEqual([q.prompt_cs for q in a], [q.prompt_cs for q in b])
        self.assertEqual([q.persona for q in a], [q.persona for q in b])

    def test_different_seeds_diverge(self):
        a = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=1, n=12)
        b = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=2, n=12)
        self.assertNotEqual([q.prompt_cs for q in a], [q.prompt_cs for q in b])

    def test_out_of_scope_demand_is_never_queried(self):
        """Bublanina is real demand with no meal slot; querying it would score
        a coverage failure for a dish the planner is not meant to serve."""
        queries = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=3, n=30)
        self.assertTrue(all('Bublanina' not in q.demand_term for q in queries))

    def test_queries_carry_facets_and_demand_rank(self):
        queries = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=5, n=6)
        self.assertTrue(queries)
        for q in queries:
            self.assertIsInstance(q, SimulatedQuery)
            self.assertIsNotNone(q.facets)
            self.assertGreaterEqual(q.demand_rank, 1)
            self.assertIn(q.slot, ('breakfast', 'lunch', 'dinner', 'snack'))

    def test_persona_restrictions_reach_the_query(self):
        queries = generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=9, n=40)
        vegetarian = [q for q in queries if q.persona == 'vegetarian']
        self.assertTrue(vegetarian)
        self.assertTrue(all('vegetari' in q.dietary_restrictions for q in vegetarian))

    def test_n_is_respected(self):
        self.assertEqual(len(generate_queries(DEMAND, TEMPLATES, PERSONAS, seed=1, n=5)), 5)

    def test_empty_demand_yields_no_queries(self):
        self.assertEqual(generate_queries([], TEMPLATES, PERSONAS, seed=1, n=5), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_user_simulation.py -q"`

Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.user_simulation'`

- [ ] **Step 3: Write the generator**

Create `diet_planner/services/user_simulation.py`:

```python
"""Simulated user queries: demand x phrasing x persona.

Three independent axes, deliberately kept apart. WHAT people want comes from
recipe-site rankings, HOW they phrase it from real prod prompts, and the
CONSTRAINTS (diet, slots, days) from the persona set. A hand-written prompt
list would encode our guesses on all three at once, which is how the corpus
came to be measured only against itself.

Generation is seeded and pure: same seed, same queries, so two runs are
comparable across a corpus change.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from diet_planner.services.prompt_facets import PromptFacets

#: (name, dietary_restrictions free text, extra PromptFacets kwargs). Mirrors
#: the personas in selection_distribution_report so the two harnesses describe
#: the same users.
PERSONAS = [
    ('no-preferences', '', {}),
    ('budget-family', '', {}),
    ('time-pressed', '', {'max_time_minutes': 30}),
    ('fitness', '', {'emphases': {'high_protein'}}),
    ('vegetarian', 'vegetariánská strava', {}),
    ('vegan', 'veganská strava', {}),
    ('gluten-free', 'bez lepku', {}),
]

_FALLBACK_TEMPLATES = [{'template': 'Mám {ingredient}, co uvařit?', 'observed': 1}]


@dataclass
class SimulatedQuery:
    persona: str
    prompt_cs: str
    demand_term: str
    demand_rank: int
    slot: str
    dietary_restrictions: str
    facets: PromptFacets
    num_days: int = 5
    canonicals: List[str] = field(default_factory=list)


def _render(template: str, term: str, num_days: int) -> str:
    return (template
            .replace('{ingredient}', term.lower())
            .replace('{n}', str(num_days))
            .replace('{quality}', 'rychlého')
            .replace('{objective}', 'jíst zdravěji')
            .replace('{free_short}', term.lower()))


def generate_queries(demand, templates, personas, *, seed: int, n: int
                     ) -> List[SimulatedQuery]:
    """`n` reproducible queries drawn from in-scope demand.

    Out-of-scope demand (desserts, drinks) is excluded: it is real demand with
    no meal slot, so serving it was never the promise.
    """
    in_scope = [row for row in demand if row.get('in_scope')]
    if not in_scope:
        return []
    templates = templates or _FALLBACK_TEMPLATES

    rng = random.Random(seed)
    queries: List[SimulatedQuery] = []
    for _ in range(n):
        row = rng.choice(in_scope)
        template = rng.choice(templates)['template']
        persona, restrictions, facet_kwargs = rng.choice(personas)
        num_days = rng.choice((3, 5, 7))

        kwargs = dict(facet_kwargs)
        wanted = set(kwargs.pop('wanted_ingredients', set()))
        wanted.add(row['term'].split()[-1].lower())
        facets = PromptFacets(wanted_ingredients=wanted, **kwargs)

        queries.append(SimulatedQuery(
            persona=persona,
            prompt_cs=_render(template, row['term'], num_days),
            demand_term=row['term'],
            demand_rank=int(row['rank']),
            slot=row.get('slot_hint') or 'dinner',
            dietary_restrictions=restrictions,
            facets=facets,
            num_days=num_days,
            canonicals=list(row.get('canonicals') or []),
        ))
    return queries
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_user_simulation.py -q"`

Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/user_simulation.py diet_planner/tests/test_user_simulation.py
git commit -m "feat(farm): seeded query generation from demand, phrasing, personas"
```

---

### Task 7: The gate funnel

A thin cell must name its cause. This measures pool size after each successive
gate by calling the REAL `eligible_recipes_for_slot` with progressively more
constraints — never by reimplementing the gate order, which would drift from
retrieval the first time someone edits it.

**Files:**
- Modify: `diet_planner/services/user_simulation.py`
- Test: `diet_planner/tests/test_user_simulation.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_user_simulation.py`:

```python
from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services.user_simulation import gate_funnel


def _recipe(slug, **kw):
    defaults = dict(
        slug=slug, name_cs=slug, meal_types=['dinner'], base_servings=2,
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        shopping_difficulty=Availability.COMMON, shopping_blockers=[],
        ingredients=[{'name': 'sůl', 'canonical': 'salt', 'quantity': 5,
                      'unit': 'g', 'catalog_id': 1}],
        instructions=[{'text': 'Uvařte.'}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class GateFunnelTests(TestCase):
    def test_counts_shrink_monotonically_through_the_gates(self):
        _recipe('a')
        _recipe('b', dietary_tags=['vegan'])
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        counts = [funnel[k] for k in ('pool', 'slot', 'dietary', 'mapped', 'facets')]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_dietary_gate_is_attributed(self):
        _recipe('omnivore')
        _recipe('vegan-dish', dietary_tags=['vegan'])
        funnel = gate_funnel(slot='dinner', required_tags={'vegan'}, facets=None)
        self.assertEqual(funnel['slot'], 2)
        self.assertEqual(funnel['dietary'], 1)
        self.assertEqual(funnel['killer'], 'dietary')

    def test_specialty_cost_is_reported_separately(self):
        """The specialty gate is unconditional inside eligible_recipes_for_slot,
        so its cost is measured directly rather than by toggling it."""
        _recipe('easy')
        _recipe('hard', shopping_difficulty=Availability.SPECIALTY,
                shopping_blockers=['tahini'])
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        self.assertEqual(funnel['specialty_cost'], 1)

    def test_wide_open_query_has_no_killer(self):
        _recipe('a')
        self.assertIsNone(gate_funnel(slot='dinner', required_tags=set(),
                                      facets=None)['killer'])

    def test_empty_slot_names_the_slot_as_killer(self):
        _recipe('a', meal_types=['breakfast'])
        funnel = gate_funnel(slot='dinner', required_tags=set(), facets=None)
        self.assertEqual(funnel['slot'], 0)
        self.assertEqual(funnel['killer'], 'slot')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_user_simulation.py::GateFunnelTests -q"`

Expected: FAIL — `ImportError: cannot import name 'gate_funnel'`

- [ ] **Step 3: Write the funnel**

Append to `diet_planner/services/user_simulation.py`:

```python
from typing import Dict, Set

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability
from diet_planner.services import recipe_retrieval as rr

#: Funnel stages in the order retrieval applies them.
_STAGES = ('slot', 'dietary', 'mapped', 'facets')


def gate_funnel(*, slot: str, required_tags: Set[str],
                facets: Optional[PromptFacets]) -> Dict[str, object]:
    """Pool size after each successive gate, plus which gate did the damage.

    Calls the real `eligible_recipes_for_slot` with progressively more
    constraints instead of reimplementing its order — the gate list has already
    changed once (the specialty gate) and will change again.
    """
    pool = rr.published_pool(CuratedRecipe.Status.PUBLISHED)

    counts = {'pool': len(pool)}
    counts['slot'] = len(rr.eligible_recipes_for_slot(
        slot, set(), pool=pool, enforce_mapping=False))
    counts['dietary'] = len(rr.eligible_recipes_for_slot(
        slot, required_tags, pool=pool, enforce_mapping=False))
    counts['mapped'] = len(rr.eligible_recipes_for_slot(
        slot, required_tags, pool=pool, enforce_mapping=True))
    counts['facets'] = len(rr.eligible_recipes_for_slot(
        slot, required_tags, pool=pool, enforce_mapping=True, facets=facets))

    # The specialty gate is unconditional inside eligible_recipes_for_slot, so
    # it cannot be toggled off to price it. Count it directly on the slot-and-
    # diet-eligible subset instead.
    specialty_cost = sum(
        1 for r in pool
        if r.shopping_difficulty == Availability.SPECIALTY
        and slot in (r.meal_types or [])
        and required_tags.issubset(set(r.dietary_tags or []))
    )

    killer = None
    previous = counts['pool']
    for stage in _STAGES:
        if counts[stage] == 0 and previous > 0:
            killer = stage
            break
        previous = counts[stage]

    return {**counts, 'specialty_cost': specialty_cost, 'killer': killer}
```

Add `Optional` to the module's existing `typing` import if it is not already there.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_user_simulation.py -q"`

Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/user_simulation.py diet_planner/tests/test_user_simulation.py
git commit -m "feat(farm): attribute thin pools to the gate that caused them"
```

---

### Task 8: Demand-weighted coverage

Two numbers, because they are two different promises. **Strict**: we have that
dish. **Loose**: we have something built from the same ingredients.

**Files:**
- Modify: `diet_planner/services/user_simulation.py`
- Test: `diet_planner/tests/test_user_simulation.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_user_simulation.py`:

```python
from diet_planner.services.user_simulation import demand_coverage


class DemandCoverageTests(TestCase):
    def test_strict_match_needs_the_dish_itself(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertEqual(result['strict_hits'], 1)

    def test_diacritics_do_not_defeat_the_strict_match(self):
        _recipe('gulas', name_cs='Hovezi gulas')
        self.assertEqual(demand_coverage([DEMAND[0]], top_n=1)['strict_hits'], 1)

    def test_a_different_dish_is_not_a_strict_hit(self):
        _recipe('rizek', name_cs='Kuřecí řízek')
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertEqual(result['strict_hits'], 0)

    def test_loose_match_accepts_a_canonical_overlap(self):
        """'we have something beefy' is a weaker promise than 'we have guláš',
        so it is reported as its own number."""
        _recipe('hovezi-pecene', name_cs='Hovězí pečeně',
                ingredients=[{'name': 'hovězí maso', 'canonical': 'beef',
                              'quantity': 500, 'unit': 'g', 'catalog_id': 1}])
        result = demand_coverage([DEMAND[0]], top_n=1)
        self.assertEqual(result['strict_hits'], 0)
        self.assertEqual(result['loose_hits'], 1)

    def test_out_of_scope_terms_are_excluded_from_the_denominator(self):
        result = demand_coverage(DEMAND, top_n=3)
        self.assertEqual(result['scored'], 2)
        self.assertEqual(result['out_of_scope'], 1)

    def test_top_n_limits_the_denominator(self):
        self.assertEqual(demand_coverage(DEMAND, top_n=1)['scored'], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_user_simulation.py::DemandCoverageTests -q"`

Expected: FAIL — `ImportError: cannot import name 'demand_coverage'`

- [ ] **Step 3: Write the scorer**

Append to `diet_planner/services/user_simulation.py`:

```python
import re as _re

from diet_planner.services.canonical_lookup import fold_diacritics

#: Share of a demand term's significant words that must appear in a recipe
#: name for a STRICT hit. 0.6 keeps "Hovězí guláš" ~ "Guláš hovězí" while
#: rejecting "Kuřecí guláš"-style near misses on a single shared word.
_STRICT_OVERLAP = 0.6

_WORD_SPLIT = _re.compile(r'[^0-9a-z]+')


def _significant_words(text: str) -> Set[str]:
    folded = fold_diacritics(text or '').lower()
    return {w for w in _WORD_SPLIT.split(folded) if len(w) > 2}


def _strict_hit(term_words: Set[str], recipe) -> bool:
    if not term_words:
        return False
    recipe_words = _significant_words(recipe.name_cs)
    return len(term_words & recipe_words) / len(term_words) >= _STRICT_OVERLAP


def _loose_hit(canonicals: Set[str], recipe) -> bool:
    if not canonicals:
        return False
    recipe_canonicals = {
        (i.get('canonical') or '') for i in (recipe.ingredients or [])
    }
    return bool(canonicals & recipe_canonicals)


def demand_coverage(demand, *, top_n: int) -> Dict[str, object]:
    """How much of the top-N demand the published corpus can serve.

    Returns strict and loose hit counts over IN-SCOPE terms only; out-of-scope
    demand (desserts, drinks) is counted separately and never scored, because
    the planner has no slot for it and failing it would be a false alarm.
    """
    considered = list(demand)[:top_n]
    scored = [row for row in considered if row.get('in_scope')]
    out_of_scope = len(considered) - len(scored)

    pool = list(rr.published_pool(CuratedRecipe.Status.PUBLISHED))
    strict_hits = loose_hits = 0
    misses = []

    for row in scored:
        term_words = _significant_words(row['term'])
        canonicals = set(row.get('canonicals') or [])
        strict = any(_strict_hit(term_words, r) for r in pool)
        loose = strict or any(_loose_hit(canonicals, r) for r in pool)
        strict_hits += int(strict)
        loose_hits += int(loose)
        if not loose:
            misses.append(row['term'])

    return {
        'scored': len(scored),
        'out_of_scope': out_of_scope,
        'strict_hits': strict_hits,
        'loose_hits': loose_hits,
        'misses': misses,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_user_simulation.py -q"`

Expected: `18 passed`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/user_simulation.py diet_planner/tests/test_user_simulation.py
git commit -m "feat(farm): demand-weighted coverage, strict and loose"
```

---

### Task 9: `simulate_coverage`

**Files:**
- Create: `diet_planner/management/commands/simulate_coverage.py`
- Test: `diet_planner/tests/test_simulate_coverage.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_simulate_coverage.py`:

```python
"""The farm command: no LLM in the default mode, no DB writes, ever."""
from io import StringIO
from unittest import mock

import yaml
from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability

DEMAND_YAML = {
    'terms': [
        {'term': 'Hovězí guláš', 'rank': 1, 'source': 'toprecepty.cz',
         'category': 'maso', 'slot_hint': 'dinner', 'in_scope': True,
         'canonicals': ['beef'], 'folded': 'hovezi gulas'},
        {'term': 'Bublanina', 'rank': 2, 'source': 'toprecepty.cz',
         'category': 'moucniky', 'slot_hint': None, 'in_scope': False,
         'canonicals': [], 'folded': 'bublanina'},
    ],
}
TEMPLATES_YAML = {'templates': [{'template': 'Mám {ingredient}, co uvařit?',
                                 'observed': 3}]}


def _recipe(slug, **kw):
    defaults = dict(
        slug=slug, name_cs=slug, meal_types=['dinner'], base_servings=2,
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        shopping_difficulty=Availability.COMMON, shopping_blockers=[],
        ingredients=[{'name': 'sůl', 'canonical': 'salt', 'quantity': 5,
                      'unit': 'g', 'catalog_id': 1}],
        instructions=[{'text': 'Uvařte.'}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class SimulateCoverageTests(TestCase):
    def setUp(self):
        self.demand = '/tmp/farm_demand.yaml'
        self.templates = '/tmp/farm_templates.yaml'
        with open(self.demand, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(DEMAND_YAML, fh, allow_unicode=True)
        with open(self.templates, 'w', encoding='utf-8') as fh:
            yaml.safe_dump(TEMPLATES_YAML, fh, allow_unicode=True)

    def _run(self, *extra):
        out = StringIO()
        call_command('simulate_coverage', '--demand', self.demand,
                     '--templates', self.templates, '--queries', '6',
                     '--seed', '42', *extra, stdout=out)
        return out.getvalue()

    def test_report_states_the_seed_so_runs_are_comparable(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        self.assertIn('seed=42', self._run())

    def test_report_carries_demand_coverage_and_slot_fill(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        report = self._run()
        self.assertIn('demand coverage', report)
        self.assertIn('strict', report)
        self.assertIn('loose', report)
        self.assertIn('slots filled', report)

    def test_default_mode_makes_no_llm_call(self):
        """`direct` facets exist so the corpus can be measured for free."""
        _recipe('gulas', name_cs='Hovězí guláš')
        with mock.patch(
                'diet_planner.services.prompt_facets.extract_prompt_facets') as extract:
            self._run()
        extract.assert_not_called()

    def test_extract_facets_mode_reports_extraction_reliability(self):
        from diet_planner.services.prompt_facets import PromptFacets
        _recipe('gulas', name_cs='Hovězí guláš')
        with mock.patch(
                'diet_planner.management.commands.simulate_coverage'
                '.extract_prompt_facets',
                side_effect=[PromptFacets(), PromptFacets(wanted_ingredients={'guláš'})]
                            * 3) as extract:
            report = self._run('--extract-facets')
        self.assertTrue(extract.called)
        self.assertIn('empty-facet rate', report)

    def test_the_farm_writes_nothing_to_the_database(self):
        _recipe('gulas', name_cs='Hovězí guláš')
        before = CuratedRecipe.objects.count()
        self._run()
        self.assertEqual(CuratedRecipe.objects.count(), before)

    def test_a_query_that_no_recipe_can_serve_is_reported_with_its_killer(self):
        _recipe('breakfast-only', meal_types=['breakfast'])
        self.assertIn('killer', self._run())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_simulate_coverage.py -q"`

Expected: FAIL — `CommandError: Unknown command: 'simulate_coverage'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/simulate_coverage.py`:

```python
"""Run simulated user queries against the corpus and report what it can serve.

Default mode makes NO LLM calls and NO database writes: facets are built
directly from the query, exactly as selection_distribution_report does. Pass
--extract-facets to run the real Gemini extractor instead and measure how often
extraction silently returns nothing — a known live defect on "Mám X" prompts.
"""
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from diet_planner.services import recipe_retrieval as rr
from diet_planner.services.prompt_facets import extract_prompt_facets
from diet_planner.services.user_simulation import (
    PERSONAS, demand_coverage, gate_funnel, generate_queries,
)

DEMAND_PATH = Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'demand_index_cz.yaml'
TEMPLATES_PATH = (Path(settings.BASE_DIR) / 'diet_planner' / 'data'
                  / 'prompt_templates_cz.yaml')


class Command(BaseCommand):
    help = 'Measure corpus coverage against simulated real-demand queries.'

    def add_arguments(self, parser):
        parser.add_argument('--demand', default=str(DEMAND_PATH))
        parser.add_argument('--templates', default=str(TEMPLATES_PATH))
        parser.add_argument('--queries', type=int, default=200)
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--top-n', type=int, default=200,
                            help='Demand terms scored for coverage')
        parser.add_argument('--extract-facets', action='store_true',
                            help='Use the real (LLM) facet extractor and report '
                                 'its empty rate')

    def _load(self, path, key):
        file_path = Path(path)
        if not file_path.exists():
            return []
        payload = yaml.safe_load(file_path.read_text(encoding='utf-8')) or {}
        return payload.get(key, [])

    def handle(self, *args, **options):
        demand = self._load(options['demand'], 'terms')
        templates = self._load(options['templates'], 'templates')
        if not demand:
            self.stdout.write(self.style.WARNING(
                f'no demand snapshot at {options["demand"]} — '
                'run build_demand_index --refresh first'))
            return

        queries = generate_queries(demand, templates, PERSONAS,
                                   seed=options['seed'], n=options['queries'])

        w = self.stdout.write
        w(f'seed={options["seed"]} queries={len(queries)} '
          f'mode={"extract" if options["extract_facets"] else "direct"}')

        empty_facets = 0
        killers = Counter()
        filled = total = 0

        for index, query in enumerate(queries):
            facets = query.facets
            if options['extract_facets']:
                facets = extract_prompt_facets(query.prompt_cs)
                if facets is None or facets.is_empty():
                    empty_facets += 1

            goal = SimpleNamespace(
                pk=index + 1, num_days=query.num_days,
                small_meals_per_day=0, snacks_per_day=0,
                breakfast=True, lunch=True, dinner=True,
                dietary_restrictions=query.dietary_restrictions,
            )
            result = rr.select_recipes_for_plan(goal, facets=facets)
            filled += result['coverage']['filled']
            total += result['coverage']['total']

            funnel = gate_funnel(
                slot=query.slot,
                required_tags=rr.required_tags_for_goal(goal),
                facets=facets)
            if funnel['killer']:
                killers[funnel['killer']] += 1

        coverage = demand_coverage(demand, top_n=options['top_n'])

        w('')
        w('-- slot fill --')
        pct = (100.0 * filled / total) if total else 0.0
        w(f'slots filled by curated recipes: {filled}/{total} ({pct:.1f}%)')

        w('')
        w('-- demand coverage --')
        scored = coverage['scored']
        strict_pct = (100.0 * coverage['strict_hits'] / scored) if scored else 0.0
        loose_pct = (100.0 * coverage['loose_hits'] / scored) if scored else 0.0
        w(f'in-scope demand terms scored: {scored} '
          f'(out of scope, not scored: {coverage["out_of_scope"]})')
        w(f'strict (we have that dish):        {coverage["strict_hits"]}/{scored} '
          f'({strict_pct:.1f}%)')
        w(f'loose  (same ingredients at least): {coverage["loose_hits"]}/{scored} '
          f'({loose_pct:.1f}%)')

        w('')
        w('-- queries killed, by gate --')
        if killers:
            for gate, count in killers.most_common():
                w(f'  killer={gate}: {count}')
        else:
            w('  none')

        if options['extract_facets']:
            rate = (100.0 * empty_facets / len(queries)) if queries else 0.0
            w('')
            w(f'empty-facet rate: {empty_facets}/{len(queries)} ({rate:.1f}%)')

        w('')
        w('-- top demand we cannot serve at all --')
        for term in coverage['misses'][:25]:
            w(f'  {term}')
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest diet_planner/tests/test_simulate_coverage.py -q"`

Expected: `6 passed`

- [ ] **Step 5: Run the whole backend suite for regressions**

Run: `docker-compose run --rm web sh -c "pip install -q -r requirements-dev.txt >/dev/null 2>&1; python -m pytest -q"`

Expected: `850 passed` — the 800 that pass today plus the 50 added by this plan
(4 corpus mirror + 11 demand index + 4 snapshot builder + 7 prompt templates +
18 user simulation + 6 simulate_coverage).

- [ ] **Step 6: Commit**

```bash
git add diet_planner/management/commands/simulate_coverage.py \
        diet_planner/tests/test_simulate_coverage.py
git commit -m "feat(farm): simulate_coverage — demand-weighted corpus report"
```

---

### Task 10: Run the farm and record the baseline

Code is done; this task produces the measurement.

- [ ] **Step 1: Mirror the prod corpus**

Follow the ops note in Task 1 to obtain prod read access, then:

```bash
docker-compose run --rm web python manage.py load_curated_corpus \
  --input /path/to/corpus.json --flush
docker-compose run --rm web python manage.py shell -c "
from diet_planner.models import CuratedRecipe
print('published', CuratedRecipe.objects.filter(status='published').count())
"
```

Expected: a published count in the same range as the prod report (~458 minus
whatever `unpublish_unshoppable` has demoted by then).

- [ ] **Step 2: Refresh demand and prompts**

```bash
docker-compose run --rm web python manage.py build_demand_index --refresh
docker-compose run --rm web python manage.py export_goal_prompts
```

- [ ] **Step 3: Run the farm**

```bash
docker-compose run --rm web python manage.py simulate_coverage \
  > docs/farm-coverage-2026-08-17.txt
cat docs/farm-coverage-2026-08-17.txt
```

- [ ] **Step 4: Read the report before believing it**

Three checks, in order:
1. `in-scope demand terms scored` should be a substantial fraction of the
   snapshot. If nearly everything is out of scope, `CATEGORY_SLOTS` is
   mis-mapped, not the corpus.
2. A `strict` figure of 0% with a healthy `loose` figure means the corpus is
   built from the right ingredients but almost none of the actual dishes
   Czechs search for — that is a real and important finding, not a bug.
3. `killer=` counts point at the gate to fix first. `killer=dietary`
   concentrated on vegan/gluten-free means curation, not substitution.

- [ ] **Step 5: Run the extraction-reliability pass**

This one costs Gemini calls; keep the sample small.

```bash
docker-compose run --rm web python manage.py simulate_coverage \
  --queries 40 --extract-facets \
  > docs/farm-extraction-2026-08-17.txt
grep 'empty-facet rate' docs/farm-extraction-2026-08-17.txt
```

Expected: a stated percentage. Anything near 50% confirms the known `Mám X`
extraction defect and should become its own bug, not a farm change.

- [ ] **Step 6: Commit the reports**

```bash
git add docs/farm-coverage-2026-08-17.txt docs/farm-extraction-2026-08-17.txt
git commit -m "docs: baseline demand coverage of the corpus"
```

---

## Notes for the implementer

- **Never weaken a test to make a scraper pass.** If `parse_ranking` stops
  finding terms, the site changed: re-capture the fixture and fix the pattern.
  A parser that silently returns `[]` makes the corpus look perfectly covered,
  which is the single most dangerous failure mode in this plan.
- **The corpus dump is never committed.** It is regenerable third-party-derived
  text. Only the demand snapshot, the prompt templates and the reports go in git.
- **`export_goal_prompts` touches real user data.** If you change
  `reduce_prompt`, re-check that `test_unreducible_prompts_never_reach_the_file`
  still holds; that test is the only thing standing between a user's free text
  and a public repository.
