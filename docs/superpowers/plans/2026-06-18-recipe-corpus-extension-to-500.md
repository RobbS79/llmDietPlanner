# Recipe Corpus Extension to 500 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the published `CuratedRecipe` corpus from 30 to 500 in one push,
with even depth so every (meal slot × main dietary tag) cell has ≥15–20 options,
prioritizing the doc-flagged gap cells (breakfast, snacks, vegan, gluten-free).

**Architecture:** Build four small Django management commands (§8 follow-up
tooling from `docs/recipe-corpus-scaling.md`) and a DigitalOcean App Platform
one-off job spec. Dispatch a senior-PM subagent in parallel to produce five
matrix-balanced batch index files. Then execute the existing pipeline
(`build_curated_recipes`, `remap_curated_recipes`) in prod against each batch,
with a canonical-ingredient dictionary growth pass between batches, and final
promotion of the catalog-mapped subset.

**Tech Stack:** Django 5.x, Python 3, Django `TestCase` (not pytest),
PostgreSQL/Supabase in prod, Gemini + Claude APIs for curation/judge,
DigitalOcean App Platform.

**Spec:** `docs/superpowers/specs/2026-06-18-recipe-corpus-extension-to-500-design.md`.
**Playbook:** `docs/recipe-corpus-scaling.md`.

---

## File Structure

**New files (code):**
- `diet_planner/management/commands/promote_curated_recipes.py` — Task 1
- `diet_planner/management/commands/unmapped_ingredients_report.py` — Task 2
- `diet_planner/management/commands/coverage_matrix_report.py` — Task 3
- `diet_planner/tests/test_promote_curated_recipes.py` — Task 1
- `diet_planner/tests/test_unmapped_ingredients_report.py` — Task 2
- `diet_planner/tests/test_coverage_matrix_report.py` — Task 3

**Modified files:**
- `.do/app.yaml` — add `jobs:` section (Task 4)
- `docs/recipe-corpus-scaling.md` — mark §8 items as completed once shipped
  (Task 8)
- `diet_planner/data/canonical_ingredients.yaml` — grow during batch loop
  (Task 7)

**New files (data):**
- `docs/curated-recipe-index-batch01.json` … `batch05.json` — Task 5
- `docs/curated-recipe-coverage-matrix.md` — Task 5 (PM subagent deliverable)

**Conventions to follow (verified against existing code):**
- Tests use `django.test.TestCase` (see
  `diet_planner/tests/test_recipe_facets.py`).
- Commands invoked from tests via
  `django.core.management.call_command(...)` with `stdout=StringIO()`.
- Run a single test:
  `python manage.py test diet_planner.tests.test_X.ClassName.method_name`.
- Run the full diet_planner test suite: `python manage.py test diet_planner`.

---

## Task 1: `promote_curated_recipes` command (TDD)

**Files:**
- Create: `diet_planner/management/commands/promote_curated_recipes.py`
- Create: `diet_planner/tests/test_promote_curated_recipes.py`

Promotes `CuratedRecipe` rows from `draft` to `published` iff
`is_catalog_mapped()` is true. Idempotent (already-published recipes are
skipped). Optional `--min-judge-verdict` adds a quality-score gate.

- [ ] **Step 1.1: Create the test file with the first failing test (happy path)**

Create `diet_planner/tests/test_promote_curated_recipes.py`:

```python
"""Tests for the promote_curated_recipes management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(**kw):
    """CuratedRecipe factory for promotion tests."""
    defaults = dict(
        name_cs=kw.pop('name_cs', 'Test dish'),
        slug=kw.pop('slug', None),  # will autogenerate
        status=CuratedRecipe.Status.DRAFT,
        meal_types=['lunch'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[
            {'name': 'rice', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
        ],
        instructions=[{'text': 'cook'}],
        base_servings=1,
        base_nutrition={'calories': 500},
        source_url=kw.pop('source_url', 'https://example.test/r1'),
        source_name='Example',
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class PromoteCatalogMappedTest(TestCase):
    def test_catalog_mapped_draft_is_promoted(self):
        r = _recipe(source_url='https://example.test/r-mapped')
        # All ingredients have canonical set → is_catalog_mapped() is True.
        self.assertTrue(r.is_catalog_mapped())

        out = StringIO()
        call_command('promote_curated_recipes', stdout=out)

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)
        self.assertIn('promoted=1', out.getvalue())
```

- [ ] **Step 1.2: Run the test, verify it fails**

Run: `python manage.py test diet_planner.tests.test_promote_curated_recipes.PromoteCatalogMappedTest.test_catalog_mapped_draft_is_promoted -v 2`

Expected: FAIL with `CommandError: Unknown command: 'promote_curated_recipes'`.

- [ ] **Step 1.3: Create the minimal command implementation**

Create `diet_planner/management/commands/promote_curated_recipes.py`:

```python
"""
Promote draft CuratedRecipe rows to status=published.

Only catalog-mapped drafts are promoted (is_catalog_mapped() == True);
others remain draft and are never served by retrieval. Idempotent —
already-published rows are untouched. See docs/recipe-corpus-scaling.md §5
and §8.

    python manage.py promote_curated_recipes
    python manage.py promote_curated_recipes --dry-run
    python manage.py promote_curated_recipes --min-judge-verdict minor_issues
"""
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


JUDGE_VERDICT_ORDER = {
    'incoherent': 0,
    'unknown': 1,
    'minor_issues': 2,
    'coherent': 3,
}


class Command(BaseCommand):
    help = "Promote catalog-mapped CuratedRecipe drafts to status=published."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Print what would promote; do not modify any rows.",
        )
        parser.add_argument(
            '--min-judge-verdict',
            choices=['incoherent', 'unknown', 'minor_issues', 'coherent'],
            default=None,
            help="If set, also require quality_score.verdict to be at least this level "
                 "(coherent > minor_issues > unknown > incoherent).",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        min_verdict = options['min_judge_verdict']
        min_rank = JUDGE_VERDICT_ORDER[min_verdict] if min_verdict else None

        drafts = CuratedRecipe.objects.filter(status=CuratedRecipe.Status.DRAFT).order_by('id')
        promoted = skipped_unmapped = skipped_judge = 0

        for r in drafts:
            if not r.is_catalog_mapped():
                skipped_unmapped += 1
                continue
            if min_rank is not None:
                v = (r.quality_score or {}).get('verdict', 'unknown')
                if JUDGE_VERDICT_ORDER.get(v, 0) < min_rank:
                    skipped_judge += 1
                    continue
            if not dry_run:
                r.status = CuratedRecipe.Status.PUBLISHED
                r.save(update_fields=['status', 'updated_at'])
            promoted += 1

        published_total = CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED,
        ).count()
        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}promoted={promoted} skipped_unmapped={skipped_unmapped} "
            f"skipped_judge={skipped_judge} published_total={published_total}"
        ))
```

- [ ] **Step 1.4: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_promote_curated_recipes.PromoteCatalogMappedTest.test_catalog_mapped_draft_is_promoted -v 2`

Expected: PASS.

- [ ] **Step 1.5: Add failing test — unmapped drafts stay draft**

Append to `diet_planner/tests/test_promote_curated_recipes.py`:

```python
class PromoteSkipsUnmappedTest(TestCase):
    def test_unmapped_draft_stays_draft(self):
        # Ingredient has no canonical and no catalog_id → not catalog-mapped.
        r = _recipe(
            source_url='https://example.test/r-unmapped',
            ingredients=[{'name': 'mystery-spice', 'quantity': 1, 'unit': 'tsp'}],
        )
        self.assertFalse(r.is_catalog_mapped())

        out = StringIO()
        call_command('promote_curated_recipes', stdout=out)

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)
        self.assertIn('skipped_unmapped=1', out.getvalue())
```

- [ ] **Step 1.6: Run the test, verify it passes (behavior already implemented)**

Run: `python manage.py test diet_planner.tests.test_promote_curated_recipes.PromoteSkipsUnmappedTest -v 2`

Expected: PASS. (We coded the gate up front; this test pins the behavior.)

- [ ] **Step 1.7: Add failing test — dry-run mutates nothing**

Append:

```python
class PromoteDryRunTest(TestCase):
    def test_dry_run_does_not_save(self):
        r = _recipe(source_url='https://example.test/r-dry')
        self.assertTrue(r.is_catalog_mapped())

        out = StringIO()
        call_command('promote_curated_recipes', '--dry-run', stdout=out)

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)  # unchanged
        self.assertIn('promoted=1', out.getvalue())
        self.assertIn('[dry-run]', out.getvalue())
```

- [ ] **Step 1.8: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_promote_curated_recipes.PromoteDryRunTest -v 2`

Expected: PASS.

- [ ] **Step 1.9: Add failing test — judge-verdict gate**

Append:

```python
class PromoteJudgeGateTest(TestCase):
    def test_below_min_verdict_is_skipped(self):
        r = _recipe(
            source_url='https://example.test/r-judge-low',
            quality_score={'ran': True, 'verdict': 'unknown'},
        )
        self.assertTrue(r.is_catalog_mapped())

        out = StringIO()
        call_command(
            'promote_curated_recipes',
            '--min-judge-verdict', 'minor_issues',
            stdout=out,
        )

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)
        self.assertIn('skipped_judge=1', out.getvalue())

    def test_at_or_above_min_verdict_is_promoted(self):
        r = _recipe(
            source_url='https://example.test/r-judge-ok',
            quality_score={'ran': True, 'verdict': 'coherent'},
        )

        out = StringIO()
        call_command(
            'promote_curated_recipes',
            '--min-judge-verdict', 'minor_issues',
            stdout=out,
        )

        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)
        self.assertIn('promoted=1', out.getvalue())
```

- [ ] **Step 1.10: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_promote_curated_recipes.PromoteJudgeGateTest -v 2`

Expected: PASS (both methods).

- [ ] **Step 1.11: Run the whole test module to confirm nothing regressed**

Run: `python manage.py test diet_planner.tests.test_promote_curated_recipes -v 2`

Expected: 4 tests run, all pass.

- [ ] **Step 1.12: Commit**

```bash
git add diet_planner/management/commands/promote_curated_recipes.py \
        diet_planner/tests/test_promote_curated_recipes.py
git commit -m "feat(corpus): promote_curated_recipes command (B2 §8)

Promotes draft -> published iff is_catalog_mapped(), with optional
--dry-run and --min-judge-verdict gate. Replaces ad-hoc promote.py
shell scripts called out in docs/recipe-corpus-scaling.md §5/§8."
```

---

## Task 2: `unmapped_ingredients_report` command (TDD)

**Files:**
- Create: `diet_planner/management/commands/unmapped_ingredients_report.py`
- Create: `diet_planner/tests/test_unmapped_ingredients_report.py`

Wraps the inline shell query from `docs/recipe-corpus-scaling.md` §4 as a real
command. Iterates all `CuratedRecipe.ingredients` and prints a frequency-ranked
list of ingredient names where neither `canonical` nor `catalog_id` is set.

- [ ] **Step 2.1: Create the test file with the first failing test (basic ranking)**

Create `diet_planner/tests/test_unmapped_ingredients_report.py`:

```python
"""Tests for the unmapped_ingredients_report management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, ingredients, *, status=None):
    return CuratedRecipe.objects.create(
        name_cs=f"Recipe {slug}",
        slug=slug,
        status=status or CuratedRecipe.Status.DRAFT,
        meal_types=['lunch'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=ingredients,
        instructions=[{'text': 'cook'}],
        base_servings=1,
        base_nutrition={'calories': 500},
        source_url=f'https://example.test/{slug}',
        source_name='Example',
    )


class UnmappedReportRankingTest(TestCase):
    def test_ranks_unmapped_by_frequency(self):
        _recipe('a', [
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
            {'name': 'rice', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
        ])
        _recipe('b', [
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
            {'name': 'odd-herb', 'quantity': 1, 'unit': 'tsp'},
        ])
        _recipe('c', [
            {'name': 'rare-spice', 'quantity': 2, 'unit': 'tsp'},
        ])

        out = StringIO()
        call_command('unmapped_ingredients_report', stdout=out)

        output = out.getvalue()
        # rare-spice appears 3 times, odd-herb 1, rice is mapped (excluded).
        self.assertIn('rare-spice', output)
        self.assertIn('3', output)
        self.assertIn('odd-herb', output)
        self.assertNotIn('rice', output)
        # rare-spice should appear before odd-herb (higher frequency first).
        self.assertLess(output.index('rare-spice'), output.index('odd-herb'))
```

- [ ] **Step 2.2: Run the test, verify it fails**

Run: `python manage.py test diet_planner.tests.test_unmapped_ingredients_report.UnmappedReportRankingTest -v 2`

Expected: FAIL with `CommandError: Unknown command: 'unmapped_ingredients_report'`.

- [ ] **Step 2.3: Create the minimal command implementation**

Create `diet_planner/management/commands/unmapped_ingredients_report.py`:

```python
"""
Report unmapped ingredient names across the CuratedRecipe corpus.

An ingredient is "unmapped" if it has neither `canonical` nor `catalog_id`
set on the recipe's stored `ingredients` JSON. The report ranks names by
frequency so the human curator can grow `data/canonical_ingredients.yaml`
against the most-impactful misses. See docs/recipe-corpus-scaling.md §4.

    python manage.py unmapped_ingredients_report
    python manage.py unmapped_ingredients_report --top 100
    python manage.py unmapped_ingredients_report --csv
    python manage.py unmapped_ingredients_report --status published
"""
import collections
import csv
import sys

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = "Frequency-rank unmapped ingredient names across CuratedRecipe."

    def add_arguments(self, parser):
        parser.add_argument('--top', type=int, default=50,
                            help="Show this many top entries (default 50).")
        parser.add_argument('--csv', action='store_true',
                            help="Emit machine-readable CSV (name,count) on stdout.")
        parser.add_argument(
            '--status',
            choices=['all', 'draft', 'vetted', 'published'],
            default='all',
            help="Limit to recipes of a given status (default: all).",
        )

    def handle(self, *args, **options):
        top = options['top']
        as_csv = options['csv']
        status = options['status']

        qs = CuratedRecipe.objects.all()
        if status != 'all':
            qs = qs.filter(status=status)

        counter: collections.Counter[str] = collections.Counter()
        recipes_with_unmapped = 0
        for r in qs.only('ingredients'):
            had_unmapped = False
            for ing in (r.ingredients or []):
                if ing.get('canonical') or ing.get('catalog_id'):
                    continue
                name = (ing.get('name') or '').strip()
                if not name:
                    continue
                counter[name] += 1
                had_unmapped = True
            if had_unmapped:
                recipes_with_unmapped += 1

        ranked = counter.most_common(top)

        if as_csv:
            writer = csv.writer(sys.stdout)
            writer.writerow(['name', 'count'])
            for name, count in ranked:
                writer.writerow([name, count])
            return

        total_distinct = len(counter)
        total_occurrences = sum(counter.values())
        self.stdout.write(self.style.NOTICE(
            f"Unmapped ingredients: {total_distinct} distinct, "
            f"{total_occurrences} total occurrences, "
            f"{recipes_with_unmapped} recipes with ≥1 unmapped."
        ))
        for name, count in ranked:
            self.stdout.write(f"  {count:5d}  {name}")
```

- [ ] **Step 2.4: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_unmapped_ingredients_report.UnmappedReportRankingTest -v 2`

Expected: PASS.

- [ ] **Step 2.5: Add failing test — `--top` truncates**

Append:

```python
class UnmappedReportTopFlagTest(TestCase):
    def test_top_flag_truncates_output(self):
        for i in range(10):
            _recipe(f'r{i}', [{'name': f'ing-{i}', 'quantity': 1, 'unit': 'g'}])

        out = StringIO()
        call_command('unmapped_ingredients_report', '--top', '3', stdout=out)
        output = out.getvalue()

        # Exactly 3 ingredient lines should be present.
        ing_lines = [ln for ln in output.splitlines() if ln.strip().startswith('1  ing-')]
        self.assertEqual(len(ing_lines), 3)
```

- [ ] **Step 2.6: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_unmapped_ingredients_report.UnmappedReportTopFlagTest -v 2`

Expected: PASS.

- [ ] **Step 2.7: Add failing test — `--csv` emits header + rows**

Append:

```python
class UnmappedReportCsvTest(TestCase):
    def test_csv_format(self):
        _recipe('a', [
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
            {'name': 'rare-spice', 'quantity': 1, 'unit': 'tsp'},
        ])
        _recipe('b', [{'name': 'odd-herb', 'quantity': 1, 'unit': 'tsp'}])

        out = StringIO()
        call_command('unmapped_ingredients_report', '--csv', stdout=out)
        lines = [ln for ln in out.getvalue().splitlines() if ln.strip()]

        self.assertEqual(lines[0], 'name,count')
        self.assertIn('rare-spice,2', lines)
        self.assertIn('odd-herb,1', lines)
```

- [ ] **Step 2.8: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_unmapped_ingredients_report.UnmappedReportCsvTest -v 2`

Expected: PASS.

- [ ] **Step 2.9: Add failing test — `--status` filter**

Append:

```python
class UnmappedReportStatusFilterTest(TestCase):
    def test_status_filter_excludes_other_statuses(self):
        _recipe('draft', [{'name': 'draft-only-ing', 'quantity': 1, 'unit': 'g'}])
        _recipe('pub',   [{'name': 'pub-only-ing',   'quantity': 1, 'unit': 'g'}],
                status=CuratedRecipe.Status.PUBLISHED)

        out = StringIO()
        call_command('unmapped_ingredients_report', '--status', 'published',
                     stdout=out)
        output = out.getvalue()

        self.assertIn('pub-only-ing', output)
        self.assertNotIn('draft-only-ing', output)
```

- [ ] **Step 2.10: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_unmapped_ingredients_report.UnmappedReportStatusFilterTest -v 2`

Expected: PASS.

- [ ] **Step 2.11: Run the whole module**

Run: `python manage.py test diet_planner.tests.test_unmapped_ingredients_report -v 2`

Expected: 4 tests run, all pass.

- [ ] **Step 2.12: Commit**

```bash
git add diet_planner/management/commands/unmapped_ingredients_report.py \
        diet_planner/tests/test_unmapped_ingredients_report.py
git commit -m "feat(corpus): unmapped_ingredients_report command (B2 §8)

Frequency-ranked report of CuratedRecipe ingredient names that lack
both canonical and catalog_id. Drives canonical_ingredients.yaml
growth between batches per docs/recipe-corpus-scaling.md §4."
```

---

## Task 3: `coverage_matrix_report` command (TDD)

**Files:**
- Create: `diet_planner/management/commands/coverage_matrix_report.py`
- Create: `diet_planner/tests/test_coverage_matrix_report.py`

Reports the **eligible-published** recipe count per (meal slot × dietary tag)
cell. "Eligible" mirrors retrieval's hard gate: `status=published` + slot in
`meal_types` + `dietary_tags ⊇ {tag}` + `is_catalog_mapped()`.

- [ ] **Step 3.1: Create the test file with the first failing test (basic cell counts)**

Create `diet_planner/tests/test_coverage_matrix_report.py`:

```python
"""Tests for the coverage_matrix_report management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _published(slug, meal_types, dietary_tags, *, mapped=True):
    ing_canonical = 'rice-basmati' if mapped else None
    ingredient = {'name': 'rice', 'quantity': 100, 'unit': 'g'}
    if ing_canonical:
        ingredient['canonical'] = ing_canonical
    return CuratedRecipe.objects.create(
        name_cs=f"Recipe {slug}",
        slug=slug,
        status=CuratedRecipe.Status.PUBLISHED,
        meal_types=meal_types,
        dietary_tags=dietary_tags,
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=[ingredient],
        instructions=[{'text': 'cook'}],
        base_servings=1,
        base_nutrition={'calories': 500},
        source_url=f'https://example.test/{slug}',
        source_name='Example',
    )


class CoverageMatrixBasicTest(TestCase):
    def test_counts_published_eligible_per_cell(self):
        _published('a', ['lunch'], [])
        _published('b', ['lunch', 'dinner'], ['vegan'])
        _published('c', ['breakfast'], ['gluten_free', 'vegan'])

        out = StringIO()
        call_command('coverage_matrix_report', stdout=out)
        output = out.getvalue()

        # The header / row labels should at least mention the standard
        # slots and tags we report on.
        self.assertIn('breakfast', output)
        self.assertIn('lunch', output)
        self.assertIn('dinner', output)
        self.assertIn('vegan', output)
        self.assertIn('gluten_free', output)
        # And the totals row/column should reflect 3 distinct published recipes.
        self.assertIn('3', output)
```

- [ ] **Step 3.2: Run the test, verify it fails**

Run: `python manage.py test diet_planner.tests.test_coverage_matrix_report.CoverageMatrixBasicTest -v 2`

Expected: FAIL with `CommandError: Unknown command: 'coverage_matrix_report'`.

- [ ] **Step 3.3: Create the minimal command implementation**

Create `diet_planner/management/commands/coverage_matrix_report.py`:

```python
"""
Report the eligible-published CuratedRecipe count per (meal slot x dietary tag)
cell. Eligibility mirrors the retrieval hard gate in
`select_recipes_for_plan`: status=published, slot in meal_types,
dietary_tags ⊇ {tag}, and is_catalog_mapped().

The intent: verify a balanced corpus before/after each curation batch.
The B2 push target is ≥15–20 recipes per cell — see
docs/recipe-corpus-scaling.md §1.

    python manage.py coverage_matrix_report
    python manage.py coverage_matrix_report --csv
    python manage.py coverage_matrix_report --include-drafts
"""
import csv
import sys

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


SLOTS = ['breakfast', 'lunch', 'dinner', 'small_meal', 'snack']
DIETARY_TAGS = [
    'none',  # synthetic — no dietary restriction
    'vegetarian',
    'vegan',
    'gluten_free',
    'dairy_free',
    'low_carb',
    'high_protein',
]


class Command(BaseCommand):
    help = "Eligible-published CuratedRecipe count per (slot x dietary tag)."

    def add_arguments(self, parser):
        parser.add_argument('--csv', action='store_true',
                            help="Emit machine-readable CSV on stdout.")
        parser.add_argument(
            '--include-drafts', action='store_true',
            help="Count drafts and vetted too (debug aid; default published-only).",
        )

    def handle(self, *args, **options):
        as_csv = options['csv']
        include_drafts = options['include_drafts']

        qs = CuratedRecipe.objects.all()
        if not include_drafts:
            qs = qs.filter(status=CuratedRecipe.Status.PUBLISHED)

        # Pre-filter on is_catalog_mapped() in Python (it walks the JSON).
        eligible = [r for r in qs if r.is_catalog_mapped()]

        # Build the 2-D count grid.
        grid = {slot: {tag: 0 for tag in DIETARY_TAGS} for slot in SLOTS}
        for r in eligible:
            slots = r.meal_types or []
            tags = set(r.dietary_tags or [])
            for slot in slots:
                if slot not in grid:
                    continue
                # The synthetic 'none' column counts recipes with no dietary tag.
                if not tags:
                    grid[slot]['none'] += 1
                for tag in DIETARY_TAGS:
                    if tag == 'none':
                        continue
                    if tag in tags:
                        grid[slot][tag] += 1

        if as_csv:
            writer = csv.writer(sys.stdout)
            writer.writerow(['slot'] + DIETARY_TAGS + ['total'])
            for slot in SLOTS:
                row = [grid[slot][tag] for tag in DIETARY_TAGS]
                writer.writerow([slot] + row + [sum(row)])
            return

        # Human-readable text grid.
        col_w = 11
        header = f"{'slot':<12}" + "".join(f"{tag[:col_w-1]:>{col_w}}" for tag in DIETARY_TAGS) \
                 + f"{'total':>{col_w}}"
        self.stdout.write(self.style.NOTICE(header))
        self.stdout.write('-' * len(header))
        for slot in SLOTS:
            row = [grid[slot][tag] for tag in DIETARY_TAGS]
            line = f"{slot:<12}" + "".join(f"{v:>{col_w}}" for v in row) \
                   + f"{sum(row):>{col_w}}"
            self.stdout.write(line)
        self.stdout.write('')
        self.stdout.write(
            f"Total eligible recipes: {len(eligible)}"
        )
```

- [ ] **Step 3.4: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_coverage_matrix_report.CoverageMatrixBasicTest -v 2`

Expected: PASS.

- [ ] **Step 3.5: Add failing test — unmapped recipes are excluded**

Append:

```python
class CoverageMatrixUnmappedExcludedTest(TestCase):
    def test_unmapped_published_recipe_not_counted(self):
        _published('a', ['lunch'], [], mapped=False)  # not catalog-mapped
        out = StringIO()
        call_command('coverage_matrix_report', '--csv', stdout=out)
        # Sum of all cells in the lunch row should be 0.
        for ln in out.getvalue().splitlines():
            if ln.startswith('lunch,'):
                # Last column is total.
                self.assertEqual(int(ln.rsplit(',', 1)[-1]), 0)
                return
        self.fail('lunch row not present in CSV')
```

- [ ] **Step 3.6: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_coverage_matrix_report.CoverageMatrixUnmappedExcludedTest -v 2`

Expected: PASS.

- [ ] **Step 3.7: Add failing test — drafts excluded by default**

Append:

```python
class CoverageMatrixDraftsExcludedTest(TestCase):
    def test_drafts_not_counted_unless_flag_set(self):
        # Create a catalog-mapped DRAFT.
        CuratedRecipe.objects.create(
            name_cs='Draft Lunch',
            slug='draft-lunch',
            status=CuratedRecipe.Status.DRAFT,
            meal_types=['lunch'],
            dietary_tags=[],
            cuisine='czech',
            difficulty=CuratedRecipe.Difficulty.EASY,
            ingredients=[
                {'name': 'rice', 'quantity': 100, 'unit': 'g', 'canonical': 'rice-basmati'},
            ],
            instructions=[{'text': 'cook'}],
            base_servings=1,
            base_nutrition={'calories': 500},
            source_url='https://example.test/draft',
            source_name='Example',
        )

        out_default = StringIO()
        call_command('coverage_matrix_report', '--csv', stdout=out_default)
        out_with_drafts = StringIO()
        call_command('coverage_matrix_report', '--csv', '--include-drafts',
                     stdout=out_with_drafts)

        def lunch_total(csv_text):
            for ln in csv_text.splitlines():
                if ln.startswith('lunch,'):
                    return int(ln.rsplit(',', 1)[-1])
            return None

        self.assertEqual(lunch_total(out_default.getvalue()), 0)
        self.assertEqual(lunch_total(out_with_drafts.getvalue()), 1)
```

- [ ] **Step 3.8: Run the test, verify it passes**

Run: `python manage.py test diet_planner.tests.test_coverage_matrix_report.CoverageMatrixDraftsExcludedTest -v 2`

Expected: PASS.

- [ ] **Step 3.9: Run the whole module**

Run: `python manage.py test diet_planner.tests.test_coverage_matrix_report -v 2`

Expected: 3 tests run, all pass.

- [ ] **Step 3.10: Commit**

```bash
git add diet_planner/management/commands/coverage_matrix_report.py \
        diet_planner/tests/test_coverage_matrix_report.py
git commit -m "feat(corpus): coverage_matrix_report command (B2 §8)

Eligible-published CuratedRecipe count per (slot x dietary tag).
Mirrors retrieval's hard gate (is_catalog_mapped + status=published +
slot + dietary_tags superset). Drives B2 target verification
(≥15–20 per cell) per docs/recipe-corpus-scaling.md §1/§8."
```

---

## Task 4: DigitalOcean App Platform one-off job spec

**Files:**
- Modify: `.do/app.yaml` — add a `jobs:` section.

A ~94-URL batch run is ~20–30 min wall-clock; the full 5-batch push is
~95 min. Console pastes are fragile at that length, so we run each batch as a
DO App Platform one-off **job** that inherits the prod env.

Notes:
- DigitalOcean App Platform `jobs:` of kind `POST_DEPLOY` or kind unspecified
  run on demand. We use a job that takes a `BATCH_FILE` env var so the same
  job spec runs against any of the five batch files.
- The job inherits the same image as the `web` service via
  `dockerfile_path: Dockerfile.prod`. No new container is built.

- [ ] **Step 4.1: Read the current app.yaml to confirm structure**

Run: `cat /app/.do/app.yaml`
Expected: a `services:` block with the `web` service. No existing `jobs:` key.

- [ ] **Step 4.2: Add the `jobs:` section**

Edit `/app/.do/app.yaml` — append after the `services:` block, before
`domains:`:

```yaml
jobs:
  - name: curate-batch
    kind: PRE_DEPLOY  # runs on-demand (DO requires a kind; PRE_DEPLOY is
                     # the most appropriate for an idempotent one-off curation
                     # job; trigger via 'doctl apps create-deployment' or
                     # the DO Console "Run Job" button).
    github:
      repo: YOUR_GITHUB_USERNAME/llmDietPlanner
      branch: prod
    dockerfile_path: Dockerfile.prod
    instance_count: 1
    instance_size_slug: basic-xxs
    run_command: >-
      python manage.py build_curated_recipes
      --index ${BATCH_FILE:-docs/curated-recipe-index-batch01.json}
      --sleep 1
    envs:
      # The batch file to curate. Override per run via the DO Console's
      # "Run Job" form or by deploying with a different value.
      - key: BATCH_FILE
        value: "docs/curated-recipe-index-batch01.json"
      # Inherit the prod secrets the curation pipeline needs.
      - key: DATABASE_URL
        scope: RUN_TIME
        type: SECRET
      - key: GEMINI_API_KEY
        scope: RUN_TIME
        type: SECRET
      - key: GEMINI_MODEL
        value: "gemini-2.5-flash"
      - key: ANTHROPIC_API_KEY
        scope: RUN_TIME
        type: SECRET
      - key: SECRET_KEY
        scope: RUN_TIME
        type: SECRET
      - key: FIELD_ENCRYPTION_KEY
        scope: RUN_TIME
        type: SECRET
      - key: DEBUG
        value: "False"
```

- [ ] **Step 4.3: Validate the YAML parses cleanly**

Run: `python -c "import yaml; yaml.safe_load(open('.do/app.yaml')); print('OK')"`
Expected: `OK`.

- [ ] **Step 4.4: Add an operator runbook section to `docs/recipe-corpus-scaling.md`**

In `docs/recipe-corpus-scaling.md`, at the end of §3 (the pipeline section),
append:

```markdown
### Running a batch as a DigitalOcean one-off job

Use `.do/app.yaml`'s `curate-batch` job rather than the prod console for any
run longer than ~10 minutes. To run a batch:

1. In the DO App Platform dashboard for `llm-diet-planner`, open the
   `curate-batch` job.
2. Click **Run Job**. In the form, override the `BATCH_FILE` env var with
   the batch you want (e.g. `docs/curated-recipe-index-batch02.json`).
3. Stream logs from the job's run page. The run is idempotent — already-
   curated `source_url`s are skipped, so re-running picks up from a drop.

Equivalent CLI: `doctl apps create-deployment <app-id> --force-rebuild` after
editing `BATCH_FILE` in `.do/app.yaml`. Prefer the dashboard for ad-hoc batch
selection.
```

- [ ] **Step 4.5: Commit**

```bash
git add .do/app.yaml docs/recipe-corpus-scaling.md
git commit -m "feat(ops): DO one-off job for build_curated_recipes (B2 §8)

Adds a curate-batch job to .do/app.yaml that runs the curation
pipeline against a BATCH_FILE env var, inheriting prod secrets.
Frees curation runs from the interactive console (~95 min for the
full push). Docs runbook appended to recipe-corpus-scaling.md §3."
```

---

## Task 5: PM subagent dispatch — produce 5 batch index files

**Files:**
- Create: `docs/curated-recipe-index-batch01.json` … `batch05.json`
- Create: `docs/curated-recipe-coverage-matrix.md`

Dispatch a senior-PM subagent to produce the source URLs. This task is a
**single dispatch**; the subagent does the multi-day research work and
returns artifacts to commit. Do not write code in this task.

- [ ] **Step 5.1: Dispatch the senior-PM subagent**

Dispatch a `general-purpose` subagent with this prompt (verbatim — paste it
into the Agent tool, `subagent_type: "general-purpose"`):

> **Role:** You are a senior product manager responsible for curating the
> sourcing strategy for a 470-URL expansion of the `CuratedRecipe` corpus
> from 30 → 500 in a Czech-first diet-planner app. Read
> `docs/recipe-corpus-scaling.md`,
> `docs/curated-recipe-index.json`, and
> `docs/curated-recipe-index.example.json` first to understand the schema and
> playbook. Then read the spec at
> `docs/superpowers/specs/2026-06-18-recipe-corpus-extension-to-500-design.md`
> §3 for your brief.
>
> **Deliverables (commit each as you go):**
>
> 1. `docs/curated-recipe-coverage-matrix.md` — a Markdown table showing your
>    planned distribution across (meal slot × dietary tag × cuisine), with
>    counts per cell summing to ~470. Justify the gap-cell prioritization
>    (breakfast, snacks, vegan, gluten_free) and the ~40% CZ-traditional /
>    ~60% international split.
> 2. Five batch index files, ~94 URLs each:
>    - `docs/curated-recipe-index-batch01.json`
>    - `docs/curated-recipe-index-batch02.json`
>    - `docs/curated-recipe-index-batch03.json`
>    - `docs/curated-recipe-index-batch04.json`
>    - `docs/curated-recipe-index-batch05.json`
>
>    Each file follows the existing schema:
>    `[{ "dish_name": str, "source_url": str, "source_name": str,
>       "source_author": str (optional) }]`.
>
> 3. A short report at the end of your run summarizing: total URLs by source
>    site, total URLs by (slot, dietary tag), and any cells where you couldn't
>    find enough high-quality JSON-LD sources (so the human reviewer knows
>    which gaps may need a follow-up mini-batch).
>
> **Hard sourcing rules:**
> - Prefer sites that publish `schema.org/Recipe` JSON-LD. Seed sites: Budget
>   Bytes, Cookie and Kate, Love and Lemons, NatashasKitchen, toprecepty.cz,
>   recepty.cz. You may add more if they're JSON-LD-friendly and reputable.
> - Recipes must be CZ-catalog-buyable: built from buyable staples; avoid
>   exotic single-source ingredients that would fail `is_catalog_mapped()`.
> - Attribution mandatory: every entry must carry `source_url` +
>   `source_name`; `source_author` when the site names one.
> - **Dedupe by dish slug**, not just URL. Same dish from two URLs is a dupe.
> - Distribute URLs across the 5 batches so each batch is matrix-balanced
>   (not all lunches in batch01, etc.).
>
> **Coverage matrix axes (from `recipe-corpus-scaling.md` §2):**
> - Meal slot: breakfast, lunch, dinner, small_meal, snack.
>   **Over-source breakfast and snack** (doc-flagged gaps).
> - Dietary tag: (none), vegetarian, vegan, gluten_free, dairy_free, low_carb,
>   high_protein. **Over-source vegan and gluten_free.**
> - Cuisine: czech, italian, asian, mediterranean, mexican, american, etc.
>   **~40% CZ-traditional / ~60% international.**
>
> Commit your work to the current branch as you go (one commit per file is
> fine). When done, post a short summary back to me.

Expected: subagent commits 5 JSON files + 1 coverage table Markdown +
optionally a final report.

- [ ] **Step 5.2: Verify the deliverables landed**

Run:
```bash
ls -la /app/docs/curated-recipe-index-batch0*.json /app/docs/curated-recipe-coverage-matrix.md
python -c "import json; [print(f, len(json.load(open(f)))) for f in [
  'docs/curated-recipe-index-batch01.json',
  'docs/curated-recipe-index-batch02.json',
  'docs/curated-recipe-index-batch03.json',
  'docs/curated-recipe-index-batch04.json',
  'docs/curated-recipe-index-batch05.json',
]]"
```
Expected: 5 JSON files present, each with ~94 entries (total ~470).

- [ ] **Step 5.3: Human review of the coverage matrix**

Read `docs/curated-recipe-coverage-matrix.md`. Verify:
- Per-cell counts roll up to ≥15–20 across the 5 batches for every
  (slot × main dietary tag) cell, with extra weight on breakfast/snack/vegan/
  gluten_free.
- CZ/international split is in the 35–45 / 55–65 ballpark.
- No obvious dupes across the 5 batch files (eyeball-spot 10 dish names
  per batch).

If the PM subagent's distribution is off, send it back with concrete
correction notes (do not silently fix the JSON files by hand — the matrix is
the auditable record).

- [ ] **Step 5.4: Commit (if the subagent didn't already commit)**

```bash
git add docs/curated-recipe-index-batch0*.json docs/curated-recipe-coverage-matrix.md
git commit -m "data(corpus): batch 01-05 index files + coverage matrix

PM-subagent-produced source URL index for the 30 -> 500 push.
~94 URLs per batch, matrix-balanced across (slot x dietary tag x
cuisine) with over-sourcing of breakfast/snack/vegan/gluten_free
gap cells. See docs/curated-recipe-coverage-matrix.md."
```

---

## Task 6: Smoke test — validate sources before committing to the full push

**Type:** Operational checklist. Run in **prod environment** (DO Console for
the `web` service, OR the new `curate-batch` job with a custom `--limit`
override).

A bad source family would burn cost across 470 URLs. Smoke-test batch01 at
`--limit 20 --no-judge` first.

- [ ] **Step 6.1: Re-seed the canonical dictionary in prod**

In the DO Console for the `web` service (Console tab):
```bash
python manage.py seed_canonical_ingredients
```
Expected: "created=N updated=M aliases=K" summary, no errors.

- [ ] **Step 6.2: Run a 20-URL smoke pass against batch01**

In the same console:
```bash
python manage.py build_curated_recipes \
  --index docs/curated-recipe-index-batch01.json \
  --limit 20 \
  --no-judge \
  --sleep 1
```
Expected: "Done. curated=20 skipped=0 errors=0" or similar; errors must be 0
or very near 0.

- [ ] **Step 6.3: Inspect the 20 drafts in admin**

Open prod admin → Curated Recipes → filter by `status=draft`, sort by
`created_at desc`. Spot-check 5 of the 20:
- Steps read as clear Czech and look novice-friendly.
- Ingredients list looks like a real shopping basket (no "leftover from
  yesterday" type items).
- Attribution (`source_url`, `source_name`) is populated.
- ≥80% of ingredients have `canonical` populated.

- [ ] **Step 6.4: Decision gate**

- If smoke pass clean (errors≈0, drafts look good): proceed to Task 7.
- If a source domain is failing systematically or the rewrite quality is
  poor for a source: send the PM subagent back with concrete notes to
  swap out that source, then re-run Task 5 → Task 6.
- If mapping is below 80% on the drafts: do the dictionary growth loop
  (Task 7's Step 7.3) now on the 20-recipe smoke set, then continue.

---

## Task 7: Full curation loop — batches 01 through 05

**Type:** Operational checklist. Run in **prod environment** via the DO
`curate-batch` job (Task 4).

The loop repeats five times, once per batch. Between batches we grow the
canonical-ingredient dictionary so mapping stays ≥95% as the corpus grows.

- [ ] **Step 7.1: Pre-flight per batch — set the BATCH_FILE env var**

In the DO Console, open the `curate-batch` job, click **Run Job**, set
`BATCH_FILE=docs/curated-recipe-index-batchNN.json` for the current batch
(NN = 01..05), and start the run. Stream logs.

Expected: ~20–30 min wall-clock per batch, final line
`Done. curated=~94 skipped=~0 errors=≈0 judge_flagged=N`.

- [ ] **Step 7.2: Verify the batch landed**

In the prod `web` console:
```bash
python manage.py shell -c "from diet_planner.models import CuratedRecipe; \
print('drafts:', CuratedRecipe.objects.filter(status='draft').count(), \
      'published:', CuratedRecipe.objects.filter(status='published').count())"
```
Expected: draft count grew by ~94 since the previous batch.

- [ ] **Step 7.3: Dictionary growth pass**

In the prod `web` console:

```bash
# Look at the top 50 unmapped ingredient names from THIS batch's draft set.
python manage.py unmapped_ingredients_report --top 50 --status draft
```

For each frequent miss in the head of that list, decide locally (on your
dev machine):
- New `CanonicalIngredient` (a real new ingredient) — add a top-level entry
  in `diet_planner/data/canonical_ingredients.yaml`.
- Alias on an existing canonical (synonym / plural / variant) — add to that
  canonical's `aliases:` list.

Commit the YAML diff to git, push, and DO will redeploy `web`. Then in
prod console:

```bash
python manage.py seed_canonical_ingredients
python manage.py remap_curated_recipes
python manage.py unmapped_ingredients_report --top 20 --status draft
```

Expected: mapping rate on the report visibly improved (fewer total
occurrences in the unmapped tail).

Target per batch: ≥95% ingredient mapping rate on the draft set before
moving on.

- [ ] **Step 7.4: Repeat 7.1–7.3 for the next batch**

Repeat for batches 02, 03, 04, 05. The loop is the same each time.

- [ ] **Step 7.5: Confirm corpus size after all 5 batches**

In prod console:
```bash
python manage.py shell -c "from diet_planner.models import CuratedRecipe; \
print('total:', CuratedRecipe.objects.count(), \
      'drafts:', CuratedRecipe.objects.filter(status='draft').count(), \
      'published:', CuratedRecipe.objects.filter(status='published').count())"
```
Expected: total ≈ 500 (30 existing + ~470 new). Drafts ≈ 470 (we haven't
promoted yet); published is still ≈ 30.

---

## Task 8: Promotion + coverage verification + close-out

**Type:** Operational + small docs update.

- [ ] **Step 8.1: Pre-promotion coverage check**

In prod `web` console:
```bash
python manage.py coverage_matrix_report --include-drafts
```
Expected: each (slot × main dietary tag) cell shows ≥15 catalog-mapped
candidates including drafts. If a cell is below 15, schedule a follow-up
mini-batch (≤50 URLs) before promoting; cell coverage is the whole point.

- [ ] **Step 8.2: Dry-run promotion**

```bash
python manage.py promote_curated_recipes --dry-run
```
Expected: `[dry-run] promoted=N skipped_unmapped=M skipped_judge=0 ...`
where N is the catalog-mapped draft subset (typically 90–95% of drafts).

- [ ] **Step 8.3: Spot-check 10 to-be-promoted drafts in admin**

Pick 10 of the soon-to-be-promoted drafts at random across the 5 batches
(via admin → Curated Recipes filter by `status=draft`). For each verify:
- Step clarity / cultural fit / shopping coherence.
- `source_url`, `source_name` present.
- `ingredients[]` is the real shopping basket (no klizka-style "leftovers").

If 1–2 are problematic, fix in place (admin edit) or mark them
`status=vetted` to hold them back. If a systematic issue surfaces (e.g.
many recipes from one source are unclear), pause and re-curate that source
slice.

- [ ] **Step 8.4: Live promotion**

```bash
python manage.py promote_curated_recipes
```
Expected: `promoted=~440 skipped_unmapped=~30 published_total=~470`.

- [ ] **Step 8.5: Final coverage check**

```bash
python manage.py coverage_matrix_report
python manage.py coverage_matrix_report --csv > /tmp/coverage_final.csv
```
Expected: every cell ≥15, target 20+ for the over-sourced cells
(breakfast, snack, vegan, gluten_free). Save the CSV as the after-snapshot
of the push (paste into the PR description or close-out note).

- [ ] **Step 8.6: Mark §8 tooling items as completed in the playbook**

Edit `docs/recipe-corpus-scaling.md` §8 to strike through the four
completed items:

```markdown
## 8. Suggested follow-up tooling (~~not yet built~~ shipped 2026-06-18)

- ~~`promote_curated_recipes` command (gate on `is_catalog_mapped`, optional
  judge threshold).~~ Shipped.
- ~~An "unmapped ingredients report" command (wraps the §4 query) to drive
  dictionary growth each batch.~~ Shipped as `unmapped_ingredients_report`.
- ~~A coverage-matrix report (eligible count per slot × dietary tag) to
  target sourcing.~~ Shipped as `coverage_matrix_report`.
- ~~A one-off DO App Platform **job** spec for large batch runs, so curation
  isn't tied to an interactive console.~~ Shipped as the `curate-batch`
  job in `.do/app.yaml`.
```

- [ ] **Step 8.7: Final commit**

```bash
git add docs/recipe-corpus-scaling.md
git commit -m "docs(corpus): mark §8 tooling shipped; B2 push complete

500-recipe corpus push complete. Final coverage attached in
/tmp/coverage_final.csv (paste into close-out note)."
```

- [ ] **Step 8.8: Close-out checklist (success criteria from spec §8)**

Verify and check off (in the PR or close-out note):

- [ ] Total `status=published` `CuratedRecipe` count ≥ **500**.
- [ ] Every (meal slot × main dietary tag) cell ≥ **15** (target 20).
- [ ] Per-batch pipeline `errors` ≈ 0 across all five batches.
- [ ] Final ingredient mapping rate ≥ **95%** across published recipes
      (re-run `unmapped_ingredients_report --status published` to confirm
      the tail is short and exotic).
- [ ] All four §8 tooling commands shipped with tests and noted in
      `docs/recipe-corpus-scaling.md` §8.
- [ ] DO `curate-batch` job spec committed and demonstrably runs a batch.

If any item is unchecked, file a follow-up issue but the B2 push itself is
shipped.
