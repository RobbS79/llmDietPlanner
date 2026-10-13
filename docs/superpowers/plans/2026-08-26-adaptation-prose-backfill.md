# Adaptation Prose Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `backfill_adaptation_prose` management command that repairs the stale prose and stale optional ingredient lines left behind on the 67 already-adapted `CuratedRecipe` rows, which the existing rescue command cannot reach.

**Architecture:** A new management command whose queryset is the exact complement of `apply_availability_substitutions`'s (`.exclude(adaptation_note='')` rather than `.filter(adaptation_note='')`). It reconstructs each row's already-applied swaps by diffing `original_ingredients` against `ingredients` index-wise — ground truth, immune to substitution-table drift — wraps them in a `SubstitutionPlan`, and feeds that to the existing `rewrite_prose()`. Optional ingredient lines are repaired first, but only where the row already disclosed that swap.

**Tech Stack:** Django 5.1 management command, existing `diet_planner.services.ingredient_substitution` / `substitution_rewrite` / `ingredient_availability` services, Gemini via the injected `generate` callable, `unittest.mock` for tests.

**Spec:** `docs/superpowers/specs/2026-08-26-adaptation-prose-backfill-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `diet_planner/services/ingredient_substitution.py` (modify) | Gains `diff_applied_changes()` and `disclosed_swaps()` — pure functions, no DB, sitting next to `IngredientChange` and `apply_changes_to_ingredients` which they mirror. |
| `diet_planner/management/commands/backfill_adaptation_prose.py` (create) | The command: queryset, the two repair steps, judge gate, atomic write, summary. |
| `diet_planner/tests/test_ingredient_substitution.py` (modify) | Unit tests for the two new pure functions. |
| `diet_planner/tests/test_backfill_adaptation_prose.py` (create) | Command-level tests, mirroring `test_apply_substitutions.py`. |

Nothing else is touched. `rewrite_prose()`, `apply_changes_to_ingredients()`, `plan_substitutions()`, and `compute_shopping_difficulty()` are all reused unchanged.

### Test-running note

There is **no pytest** in this environment. Run tests with:

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose -v 1
```

Django prints its summary to **stderr**, which can be reordered ahead of buffered stdout. Grep rather than reading the tail:

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

---

## Task 1: `diff_applied_changes()` — reconstruct what a row already carries

**Files:**
- Modify: `diet_planner/services/ingredient_substitution.py` (append after `apply_changes_to_ingredients`, ~line 206)
- Test: `diet_planner/tests/test_ingredient_substitution.py`

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_ingredient_substitution.py`:

```python
class DiffAppliedChangesTests(TestCase):
    """Reconstructing the swaps a row already carries, from its own snapshot."""

    def test_reports_a_renamed_entry_with_its_index(self):
        original = [
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
        ]
        current = [
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
            {'name': 'med', 'canonical': 'honey', 'quantity': 2, 'unit': 'lžíce'},
        ]
        changes = diff_applied_changes(original, current)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].index, 1)
        self.assertEqual(changes[0].old_name, 'javorový sirup')
        self.assertEqual(changes[0].old_slug, 'maple-syrup')
        self.assertEqual(changes[0].new_name, 'med')
        self.assertEqual(changes[0].new_canonical, 'honey')

    def test_ignores_entries_whose_name_did_not_change(self):
        entries = [{'name': 'sůl', 'canonical': 'salt'}]
        self.assertEqual(diff_applied_changes(entries, entries), [])

    def test_length_mismatch_yields_nothing_rather_than_guessing(self):
        # Misaligned lists cannot be diffed positionally; refusing beats
        # inventing a swap between two unrelated ingredients.
        self.assertEqual(
            diff_applied_changes(
                [{'name': 'a'}, {'name': 'b'}], [{'name': 'a'}]),
            [])

    def test_missing_snapshot_yields_nothing(self):
        self.assertEqual(diff_applied_changes(None, [{'name': 'med'}]), [])
        self.assertEqual(diff_applied_changes([], [{'name': 'med'}]), [])

    def test_skips_non_dict_entries(self):
        # Generated (non-corpus) meals carry bare strings.
        changes = diff_applied_changes(
            ['javorový sirup', {'name': 'sůl', 'canonical': 'salt'}],
            ['med', {'name': 'sůl', 'canonical': 'salt'}])
        self.assertEqual(changes, [])

    def test_blank_name_on_either_side_is_not_a_swap(self):
        self.assertEqual(
            diff_applied_changes([{'name': ''}], [{'name': 'med'}]), [])
        self.assertEqual(
            diff_applied_changes([{'name': 'med'}], [{'name': ''}]), [])
```

Add `diff_applied_changes` to the existing import from
`diet_planner.services.ingredient_substitution` at the top of that test file.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_ingredient_substitution.DiffAppliedChangesTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` — `ImportError: cannot import name 'diff_applied_changes'`.

- [ ] **Step 3: Write the implementation**

Append to `diet_planner/services/ingredient_substitution.py`:

```python
def diff_applied_changes(original, current) -> List[IngredientChange]:
    """The swaps a row already carries: entries renamed since the snapshot.

    Ground truth for what THIS row contains. Re-planning from
    `original_ingredients` would instead report what the swap *would be today*,
    and the table has drifted since these rows were adapted (the PR #72
    oat-flour/tamari re-rating, the PR #75 tapioca swap) — so a re-plan can name
    an ingredient the list does not hold. Prose has to describe the actual food.

    `apply_changes_to_ingredients` edits entries positionally and preserves
    length, so the two lists align by index. A length mismatch means that
    invariant was broken by something else, and diffing on would pair unrelated
    ingredients into a fictional swap: return nothing and let the caller report
    the row instead.
    """
    changes: List[IngredientChange] = []
    original = original or []
    current = current or []
    if not original or len(original) != len(current):
        return changes

    for position, (old, new) in enumerate(zip(original, current)):
        if not isinstance(old, dict) or not isinstance(new, dict):
            continue
        old_name = (old.get('name') or '').strip()
        new_name = (new.get('name') or '').strip()
        if not old_name or not new_name or old_name == new_name:
            continue
        changes.append(IngredientChange(
            index=position,
            old_name=old_name,
            old_slug=(old.get('canonical') or '').strip(),
            new_name=new_name,
            new_canonical=(new.get('canonical') or '').strip(),
            new_quantity=new.get('quantity'),
            new_unit=(new.get('unit') or '').strip(),
        ))
    return changes
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_ingredient_substitution.DiffAppliedChangesTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK`, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/ingredient_substitution.py diet_planner/tests/test_ingredient_substitution.py
git commit -m "feat(substitution): reconstruct a row's applied swaps from its own snapshot"
```

---

## Task 2: `disclosed_swaps()` — what the row already told the reader

**Files:**
- Modify: `diet_planner/services/ingredient_substitution.py`
- Test: `diet_planner/tests/test_ingredient_substitution.py`

This is the guard that earns the right to bypass `saveable` in Task 4. An
optional swap is applied only if the row has already disclosed it.

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_ingredient_substitution.py`:

```python
class DisclosedSwapsTests(TestCase):
    """Which (old -> new) pairs a row has already published."""

    def test_reads_pairs_out_of_the_note(self):
        note = ('Upraveno pro dostupnost v českých obchodech: '
                'javorový sirup → med, avokádový olej → řepkový olej')
        self.assertEqual(
            disclosed_swaps(note, []),
            {('javorový sirup', 'med'), ('avokádový olej', 'řepkový olej')})

    def test_reads_pairs_out_of_the_applied_diff(self):
        changes = [IngredientChange(
            index=0, old_name='javorový sirup', old_slug='maple-syrup',
            new_name='med', new_canonical='honey',
            new_quantity=2, new_unit='lžíce')]
        self.assertEqual(
            disclosed_swaps('', changes), {('javorový sirup', 'med')})

    def test_comparison_is_case_insensitive(self):
        # The note preserves whatever case the rule carried: prod holds
        # 'avokádový olej → Řepkový olej' with a capitalised replacement.
        note = 'Upraveno pro dostupnost v českých obchodech: Javorový Sirup → Med'
        self.assertIn(('javorový sirup', 'med'), disclosed_swaps(note, []))

    def test_empty_note_and_no_changes_disclose_nothing(self):
        self.assertEqual(disclosed_swaps('', []), set())

    def test_note_without_the_prefix_is_still_parsed(self):
        self.assertEqual(
            disclosed_swaps('javorový sirup → med', []),
            {('javorový sirup', 'med')})

    def test_chunk_without_an_arrow_is_skipped(self):
        self.assertEqual(disclosed_swaps('nějaká poznámka', []), set())
```

Add `disclosed_swaps` and `IngredientChange` to the imports in that test file.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_ingredient_substitution.DisclosedSwapsTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` — `ImportError: cannot import name 'disclosed_swaps'`.

- [ ] **Step 3: Write the implementation**

Append to `diet_planner/services/ingredient_substitution.py`:

```python
#: The `adaptation_note` body's separators. Duplicated from the command that
#: writes it rather than imported, because a service importing a management
#: command inverts the dependency.
_NOTE_ARROW = '→'
_NOTE_JOIN = ', '


def disclosed_swaps(note: str, applied: List[IngredientChange]) -> set:
    """The (old_name, new_name) pairs this row has already published, lowered.

    Two sources, unioned: the `adaptation_note` — what the reader was told —
    and the diff of what was actually applied. A swap present in either is one
    the recipe already claims, so finishing it in an unreached optional entry
    completes a disclosure rather than making a new editorial change.
    """
    pairs = {(c.old_name.strip().lower(), c.new_name.strip().lower())
             for c in applied}

    body = note or ''
    if ': ' in body:
        body = body.split(': ', 1)[1]
    for chunk in body.split(_NOTE_JOIN):
        if _NOTE_ARROW not in chunk:
            continue
        old, new = chunk.split(_NOTE_ARROW, 1)
        old, new = old.strip().lower(), new.strip().lower()
        if old and new:
            pairs.add((old, new))
    return pairs
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_ingredient_substitution.DisclosedSwapsTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK`, 6 tests.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/ingredient_substitution.py diet_planner/tests/test_ingredient_substitution.py
git commit -m "feat(substitution): read back the swaps a row has already disclosed"
```

---

## Task 3: Command skeleton — queryset, options, summary

**Files:**
- Create: `diet_planner/management/commands/backfill_adaptation_prose.py`
- Test: `diet_planner/tests/test_backfill_adaptation_prose.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_backfill_adaptation_prose.py`:

```python
"""The backfill command: reach, disclosure guard, prose repair, judge gate."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe

CMD = 'diet_planner.management.commands.backfill_adaptation_prose'
NOTE = ('Upraveno pro dostupnost v českých obchodech: '
        'javorový sirup → med')


def _adapted(**kw):
    """A row the rescue already touched: ingredients swapped, prose stale."""
    defaults = dict(
        slug='javorove-muffiny', name_cs='Javorové muffiny',
        description='Muffiny slazené javorovým sirupem.',
        meal_types=['snack'], base_servings=4,
        source_url='https://example.com/r', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        adaptation_note=NOTE,
        original_ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ],
        ingredients=[
            {'name': 'med', 'canonical': 'honey', 'quantity': 2, 'unit': 'lžíce'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ],
        instructions=[{'text': 'Přidejte med.', 'time_min': 1}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class ReachTests(TestCase):
    """The command's whole reason to exist: it sees rows the rescue cannot."""

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())

    def test_reaches_an_already_adapted_row(self):
        _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny',
                                      'Muffiny slazené medem.')), \
             mock.patch(f'{CMD}.judge_curated_recipe',
                        return_value={'ran': True, 'verdict': 'coherent',
                                      'high_severity_count': 0}):
            call_command('backfill_adaptation_prose', stdout=out)
        self.assertIn('repaired=1', out.getvalue())

    def test_ignores_a_row_that_was_never_adapted(self):
        _adapted(slug='netknuty', adaptation_note='', original_ingredients=[])
        out = StringIO()
        call_command('backfill_adaptation_prose', stdout=out)
        self.assertIn('repaired=0', out.getvalue())
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.ReachTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` — `CommandError: Unknown command: 'backfill_adaptation_prose'`.

- [ ] **Step 3: Write the minimal implementation**

Create `diet_planner/management/commands/backfill_adaptation_prose.py`:

```python
"""Repair the prose the availability rescue left stale.

`apply_availability_substitutions` filters `.filter(adaptation_note='')`, so
every row it has already touched is beyond its reach — and until PR #80 it
rewrote neither the prose nor the `optional` ingredient entries. This command is
the complement: it finishes rewrites the corpus has already disclosed, and it
introduces no swap the recipe does not already claim.

Nothing here rescues a recipe. The gating was settled when the row was adapted.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.services.ingredient_availability import (
    availability_index, compute_shopping_difficulty,
)
from diet_planner.services.ingredient_substitution import (
    SubstitutionPlan, apply_changes_to_ingredients, diff_applied_changes,
    disclosed_swaps, plan_substitutions, substitution_table,
)
from diet_planner.services.recipe_curation import judge_curated_recipe
from diet_planner.services.substitution_rewrite import (
    RewriteError, reset_usage, rewrite_prose, usage_snapshot,
)

_NOTE_PREFIX = 'Upraveno pro dostupnost v českých obchodech: '
_NOTE_MAX = CuratedRecipe._meta.get_field('adaptation_note').max_length


def _judge_rejected(verdict: dict) -> bool:
    """Did the judge actively reject this rewrite?

    `judge_curated_recipe` returns `JudgeVerdict.as_stats()`, which has no
    'passed' key — the same shape the rescue command reads.
    """
    if not verdict.get('ran'):
        return False
    return (verdict.get('verdict') != 'coherent'
            or bool(verdict.get('high_severity_count')))


class Command(BaseCommand):
    help = 'Repair stale prose and optional ingredient lines on adapted recipes'

    def add_arguments(self, parser):
        parser.add_argument('--slug', help='Restrict to one recipe')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--skip-judge', action='store_true',
            help='Skip the coherence judge (for offline reruns; not for prod)')

    def handle(self, *args, **options):
        reset_usage()
        repaired = skipped = failed = unjudged = 0

        qs = CuratedRecipe.objects.exclude(adaptation_note='').order_by('id')
        if options['slug']:
            qs = qs.filter(slug=options['slug'])

        for recipe in qs.iterator():
            if options['limit'] is not None and repaired >= options['limit']:
                break
            skipped += 1

        summary = f'repaired={repaired} skipped={skipped} failed={failed}'
        if unjudged:
            summary += f' unjudged={unjudged}'
        self.stdout.write(self.style.SUCCESS(summary))
```

- [ ] **Step 4: Run the test — the second passes, the first still fails**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.ReachTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` (1 of 2) — `repaired=1` is not yet produced. This is correct; Task 5 makes it pass.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/backfill_adaptation_prose.py diet_planner/tests/test_backfill_adaptation_prose.py
git commit -m "feat(backfill): command skeleton reaching the rows the rescue cannot"
```

---

## Task 4: Step 1 — repair disclosed optional ingredient lines

**Files:**
- Modify: `diet_planner/management/commands/backfill_adaptation_prose.py`
- Test: `diet_planner/tests/test_backfill_adaptation_prose.py`

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_backfill_adaptation_prose.py`:

```python
class OptionalLineTests(TestCase):
    """Optional entries the rescue skipped, finished only where disclosed."""

    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        # These tests are about the ingredient line, not the prose.
        prose = mock.patch(
            f'{CMD}.rewrite_prose',
            side_effect=lambda name, description, plan: (name, description))
        prose.start()
        self.addCleanup(prose.stop)
        judge = mock.patch(
            f'{CMD}.judge_curated_recipe',
            return_value={'ran': True, 'verdict': 'coherent',
                          'high_severity_count': 0})
        judge.start()
        self.addCleanup(judge.stop)

    def test_applies_an_optional_swap_the_row_already_disclosed(self):
        recipe = _adapted(ingredients=[
            {'name': 'med', 'canonical': 'honey',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 1, 'unit': 'lžíce', 'optional': True},
        ], original_ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 1, 'unit': 'lžíce', 'optional': True},
        ])
        call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.ingredients[1]['name'], 'med')
        self.assertEqual(recipe.ingredients[1]['canonical'], 'honey')
        # Still optional: repairing the name must not change its standing.
        self.assertTrue(recipe.ingredients[1]['optional'])

    def test_refuses_an_optional_swap_the_row_never_disclosed(self):
        # The note says nothing about vanilla, and no required entry swapped
        # it. Swapping it here would be a fresh editorial change to someone
        # else's credited recipe.
        recipe = _adapted(ingredients=[
            {'name': 'med', 'canonical': 'honey',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička', 'optional': True},
        ], original_ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 2, 'unit': 'lžíce'},
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička', 'optional': True},
        ])
        out = StringIO()
        call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.ingredients[1]['name'], 'vanilkový extrakt')
        self.assertIn('undisclosed', out.getvalue())
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.OptionalLineTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` — the optional entry is left as `javorový sirup`.

- [ ] **Step 3: Write the implementation**

In `handle()`, replace the `skipped += 1` loop body with:

```python
        table = substitution_table()
        if not table:
            self.stdout.write(self.style.WARNING(
                'no availability substitutions loaded — '
                'run load_availability_substitutions first'))
            return
        index = availability_index()

        for recipe in qs.iterator():
            if options['limit'] is not None and repaired >= options['limit']:
                break

            applied = diff_applied_changes(
                recipe.original_ingredients, recipe.ingredients)
            if not applied:
                # No usable snapshot, or nothing was ever swapped: there is no
                # disclosure to finish and no change list to describe.
                skipped += 1
                continue

            disclosed = disclosed_swaps(recipe.adaptation_note, applied)

            # Step 1 — optional entries the rescue skipped. `saveable` is
            # deliberately ignored: it guards against *introducing* a change,
            # and the disclosure filter below means we introduce none.
            plan = plan_substitutions(recipe, table, index=index)
            optional = [
                c for c in plan.optional_changes
                if (c.old_name.strip().lower(),
                    c.new_name.strip().lower()) in disclosed
            ]
            for change in plan.optional_changes:
                if change not in optional:
                    self.stdout.write(
                        f'  {recipe.slug}: leaving undisclosed optional swap '
                        f'{change.old_name} → {change.new_name}')

            new_ingredients = recipe.ingredients
            if optional:
                new_ingredients = apply_changes_to_ingredients(
                    recipe.ingredients,
                    SubstitutionPlan(changes=[], optional_changes=optional))
                # The prose must describe the list as it now stands.
                applied = diff_applied_changes(
                    recipe.original_ingredients, new_ingredients)

            if new_ingredients == recipe.ingredients:
                skipped += 1
                continue

            with transaction.atomic():
                recipe.ingredients = new_ingredients
                tier, blockers = compute_shopping_difficulty(recipe, index=index)
                recipe.shopping_difficulty = tier
                recipe.shopping_blockers = blockers
                recipe.save(update_fields=[
                    'ingredients', 'shopping_difficulty', 'shopping_blockers',
                    'updated_at',
                ])
            repaired += 1
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.OptionalLineTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK`, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/backfill_adaptation_prose.py diet_planner/tests/test_backfill_adaptation_prose.py
git commit -m "feat(backfill): finish disclosed optional swaps the rescue skipped"
```

---

## Task 5: Step 2 — rewrite the stale prose, fail-closed

**Files:**
- Modify: `diet_planner/management/commands/backfill_adaptation_prose.py`
- Test: `diet_planner/tests/test_backfill_adaptation_prose.py`

`rewrite_prose()` carries its own gate — it returns the fields untouched unless
`_drops()` says a field leans on a removed stem — so the command calls it
unconditionally and lets it decide whether to spend a call.

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_backfill_adaptation_prose.py`:

```python
class ProseRepairTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        judge = mock.patch(
            f'{CMD}.judge_curated_recipe',
            return_value={'ran': True, 'verdict': 'coherent',
                          'high_severity_count': 0})
        judge.start()
        self.addCleanup(judge.stop)

    def test_rewrites_a_title_and_description_the_swap_made_false(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny',
                                      'Muffiny slazené medem.')) as prose:
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Medové muffiny')
        self.assertEqual(recipe.description, 'Muffiny slazené medem.')
        # The reconstructed plan is what the rewriter was handed.
        plan = prose.call_args.args[2]
        self.assertEqual(
            [(c.old_name, c.new_name) for c in plan.changes],
            [('javorový sirup', 'med')])

    def test_leaves_the_slug_alone_even_when_the_name_changes(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.slug, 'javorove-muffiny')

    def test_a_clean_row_is_left_completely_alone(self):
        recipe = _adapted(name_cs='Medové muffiny',
                          description='Muffiny slazené medem.')
        before = recipe.updated_at
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        side_effect=lambda n, d, p: (n, d)):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.updated_at, before)
        self.assertIn('repaired=0', out.getvalue())

    def test_a_rewrite_error_leaves_the_row_untouched(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        side_effect=RewriteError('bad shape')):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Javorové muffiny')
        self.assertIn('failed=1', out.getvalue())

    def test_dry_run_writes_nothing(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', '--dry-run', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Javorové muffiny')
        self.assertIn('[dry-run]', out.getvalue())
        self.assertIn('repaired=1', out.getvalue())
```

Add to that file's imports:

```python
from diet_planner.services.substitution_rewrite import RewriteError
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.ProseRepairTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` — the name is never rewritten.

- [ ] **Step 3: Write the implementation**

Replace the tail of the loop (from `if new_ingredients == recipe.ingredients:`
onward) with:

```python
            # Step 2 — the prose. The change list is the diff, so the rewrite
            # describes the list as it actually stands, not as today's table
            # would have swapped it.
            plan_for_prose = SubstitutionPlan(changes=applied)
            try:
                new_name, new_description = rewrite_prose(
                    recipe.name_cs, recipe.description, plan_for_prose)
            except RewriteError as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(
                    f'  {recipe.slug}: prose rewrite failed: {exc}'))
                continue

            prose_changed = (new_name != recipe.name_cs
                             or new_description != recipe.description)
            if new_ingredients == recipe.ingredients and not prose_changed:
                skipped += 1
                continue

            self.stdout.write(f'{recipe.slug}: {plan_for_prose.summary()}')
            if prose_changed:
                self.stdout.write(f'    {recipe.name_cs!r} -> {new_name!r}')

            if options['dry_run']:
                repaired += 1
                continue

            with transaction.atomic():
                recipe.ingredients = new_ingredients
                # slug is deliberately NOT regenerated: the URL is public.
                recipe.name_cs = new_name
                recipe.description = new_description
                tier, blockers = compute_shopping_difficulty(recipe, index=index)
                recipe.shopping_difficulty = tier
                recipe.shopping_blockers = blockers
                recipe.save(update_fields=[
                    'ingredients', 'name_cs', 'description',
                    'shopping_difficulty', 'shopping_blockers', 'updated_at',
                ])
            repaired += 1
```

And change the summary line to carry the dry-run marker:

```python
        prefix = '[dry-run] ' if options['dry_run'] else ''
        summary = f'{prefix}repaired={repaired} skipped={skipped} failed={failed}'
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK` — `ReachTests` now passes too.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/backfill_adaptation_prose.py diet_planner/tests/test_backfill_adaptation_prose.py
git commit -m "feat(backfill): rewrite the prose a completed swap made false"
```

---

## Task 6: The judge gate

**Files:**
- Modify: `diet_planner/management/commands/backfill_adaptation_prose.py`
- Test: `diet_planner/tests/test_backfill_adaptation_prose.py`

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_backfill_adaptation_prose.py`:

```python
class JudgeGateTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        prose = mock.patch(
            f'{CMD}.rewrite_prose',
            return_value=('Medové muffiny', 'Muffiny slazené medem.'))
        prose.start()
        self.addCleanup(prose.stop)

    def test_a_rejected_rewrite_is_discarded(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.judge_curated_recipe',
                        return_value={'ran': True, 'verdict': 'incoherent',
                                      'high_severity_count': 2}):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Javorové muffiny')
        self.assertIn('failed=1', out.getvalue())

    def test_an_unavailable_judge_applies_and_says_so(self):
        recipe = _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.judge_curated_recipe',
                        return_value={'ran': False, 'error': 'no credit'}):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.name_cs, 'Medové muffiny')
        self.assertIn('unjudged=1', out.getvalue())
        self.assertIn('applying unjudged', out.getvalue())

    def test_skip_judge_never_calls_the_judge(self):
        _adapted()
        with mock.patch(f'{CMD}.judge_curated_recipe') as judge:
            call_command('backfill_adaptation_prose', '--skip-judge',
                         stdout=StringIO())
        judge.assert_not_called()

    def test_the_judge_sees_the_candidate_not_the_stored_row(self):
        recipe = _adapted()
        seen = {}

        def _judge(candidate):
            # Captured DURING the call: the stored row must still hold the old
            # prose at this point, or we are judging something already written.
            seen['candidate_name'] = candidate.name_cs
            seen['stored_name'] = CuratedRecipe.objects.get(
                pk=recipe.pk).name_cs
            return {'ran': True, 'verdict': 'coherent',
                    'high_severity_count': 0}

        with mock.patch(f'{CMD}.judge_curated_recipe', side_effect=_judge):
            call_command('backfill_adaptation_prose', stdout=StringIO())

        self.assertEqual(seen['candidate_name'], 'Medové muffiny')
        self.assertEqual(seen['stored_name'], 'Javorové muffiny')
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.JudgeGateTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` — the rejected rewrite is applied anyway.

- [ ] **Step 3: Write the implementation**

Insert immediately after the `if options['dry_run']:` block and before the
`with transaction.atomic():`:

```python
            # Judge the CANDIDATE, not the stored row: build an unsaved copy.
            candidate = CuratedRecipe(
                id=recipe.id, slug=recipe.slug, name_cs=new_name,
                description=new_description,
                ingredients=new_ingredients, instructions=recipe.instructions,
                base_servings=recipe.base_servings,
            )
            if not options['skip_judge']:
                verdict = judge_curated_recipe(candidate)
                if _judge_rejected(verdict):
                    failed += 1
                    self.stdout.write(self.style.WARNING(
                        f"  judge rejected the rewrite — discarded "
                        f"(verdict={verdict.get('verdict')}, "
                        f"high={verdict.get('high_severity_count')})"))
                    continue
                if not verdict.get('ran'):
                    # Applying unjudged is a decision, not a detail: say it.
                    unjudged += 1
                    self.stdout.write(self.style.WARNING(
                        f"  judge did not run ({verdict.get('error') or 'disabled'})"
                        f" — applying unjudged"))
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/backfill_adaptation_prose.py diet_planner/tests/test_backfill_adaptation_prose.py
git commit -m "feat(backfill): judge the candidate, disclose when the judge cannot run"
```

---

## Task 7: The note guard and idempotence

**Files:**
- Modify: `diet_planner/management/commands/backfill_adaptation_prose.py`
- Test: `diet_planner/tests/test_backfill_adaptation_prose.py`

Within the disclosure restriction, every applied swap is by construction
already named in the note, so this guard should never fire. It exists so that
if the restriction is ever loosened, the note cannot silently fall out of step
with the food.

- [ ] **Step 1: Write the failing tests**

Append to `diet_planner/tests/test_backfill_adaptation_prose.py`:

```python
class NoteAndIdempotenceTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        judge = mock.patch(
            f'{CMD}.judge_curated_recipe',
            return_value={'ran': True, 'verdict': 'coherent',
                          'high_severity_count': 0})
        judge.start()
        self.addCleanup(judge.stop)

    def test_the_note_is_left_alone_when_it_already_names_every_swap(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        self.assertEqual(recipe.adaptation_note, NOTE)

    def test_a_second_run_writes_nothing(self):
        recipe = _adapted()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')):
            call_command('backfill_adaptation_prose', stdout=StringIO())
        recipe.refresh_from_db()
        after_first = recipe.updated_at

        out = StringIO()
        # Second run: the prose no longer leans on anything removed, so the
        # real rewrite_prose returns it untouched without an LLM call.
        with mock.patch(f'{CMD}.rewrite_prose',
                        side_effect=lambda n, d, p: (n, d)):
            call_command('backfill_adaptation_prose', stdout=out)
        recipe.refresh_from_db()
        self.assertEqual(recipe.updated_at, after_first)
        self.assertIn('repaired=0', out.getvalue())

    def test_an_unusable_snapshot_is_skipped_not_crashed_on(self):
        _adapted(slug='rozbity', original_ingredients=[{'name': 'jen jedna'}])
        out = StringIO()
        call_command('backfill_adaptation_prose', stdout=out)
        self.assertIn('repaired=0', out.getvalue())
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.NoteAndIdempotenceTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` on the note test — `adaptation_note` is not in `update_fields`
yet, so the assertion about it passing through needs the guard in place.

- [ ] **Step 3: Write the implementation**

Add, just before the `with transaction.atomic():` block:

```python
            # Every applied swap should already be named in the note — the
            # disclosure filter guarantees it. Kept as a guard so that if that
            # filter is ever loosened, the note cannot fall out of step with
            # the food it describes.
            note = recipe.adaptation_note
            named = disclosed_swaps(note, [])
            missing = [c for c in applied
                       if (c.old_name.strip().lower(),
                           c.new_name.strip().lower()) not in named]
            if missing:
                extra = ', '.join(f'{c.old_name} → {c.new_name}'
                                  for c in missing)
                note = (f'{note}, {extra}' if note else _NOTE_PREFIX + extra)
                note = note[:_NOTE_MAX]
                self.stdout.write(f'    note extended: {extra}')
```

Then add `'adaptation_note'` to the save, and assign it:

```python
                recipe.adaptation_note = note
```

with `'adaptation_note'` added to the `update_fields` list.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/backfill_adaptation_prose.py diet_planner/tests/test_backfill_adaptation_prose.py
git commit -m "feat(backfill): keep the note in step with the food, and stay idempotent"
```

---

## Task 8: Report the bill, then verify the whole suite

**Files:**
- Modify: `diet_planner/management/commands/backfill_adaptation_prose.py`

The rescue command prints its token usage because a run costs real money and a
silent cost is an understated one. This command does the same.

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_backfill_adaptation_prose.py`:

```python
class UsageReportTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())

    def test_the_summary_reports_the_llm_bill(self):
        _adapted()
        out = StringIO()
        with mock.patch(f'{CMD}.rewrite_prose',
                        return_value=('Medové muffiny', 'Muffiny s medem.')), \
             mock.patch(f'{CMD}.judge_curated_recipe',
                        return_value={'ran': True, 'verdict': 'coherent',
                                      'high_severity_count': 0}):
            call_command('backfill_adaptation_prose', stdout=out)
        self.assertIn('calls=', out.getvalue())
```

- [ ] **Step 2: Run it to verify it fails**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose.UsageReportTests 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `FAILED` — no `calls=` in the output.

- [ ] **Step 3: Write the implementation**

Append after the summary write in `handle()`:

```python
        usage = usage_snapshot()
        self.stdout.write(
            f"  llm: calls={usage['calls']} "
            f"unmetered={usage['unmetered_calls']} "
            f"tokens={usage['total_tokens']}")
```

- [ ] **Step 4: Run the whole affected suite**

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner.tests.test_backfill_adaptation_prose diet_planner.tests.test_ingredient_substitution diet_planner.tests.test_apply_substitutions diet_planner.tests.test_substitution_rewrite 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK`. Then the full backend suite, which must stay at its current
count with no new failures (~4.5 minutes):

```bash
GEMINI_API_KEY=dummy python3 manage.py test diet_planner 2>&1 | grep -E "^(OK|FAILED|Ran |ERROR)"
```

Expected: `OK`, `Ran 8xx tests`.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/backfill_adaptation_prose.py diet_planner/tests/test_backfill_adaptation_prose.py
git commit -m "feat(backfill): report the token bill the run actually spent"
```

---

## Task 9: Prod dry-run, then the real repair

**Not code.** Do not start until Tasks 1–8 are green and the PR is merged and
deployed, because the command does not exist on prod until then.

- [ ] **Step 1: Dry-run on prod**

Via the scratchpad harness (`prod_run.py` pattern, or `do_exec` for a
management command). Note that `--dry-run` **spends the same Gemini tokens as a
real run** — `rewrite_prose` is called before the dry-run branch, by design in
the existing code. It is a preview of the write, not of the cost.

Expected: `repaired=` around 8–10, and the named slugs matching the audit:
`ovesna-kase-s-javorovym-sirupem-a-skorici`, `zdravy-bananovy-chleb`,
`javorove-bananove-muffiny`, `zdrave-bananove-muffiny`, `snidanove-tacos`,
`mexicke-kureci-nudle-z-cukety`, `taco-salat`, plus the optional-line rows
`ovesne-livance` and `bezlepkove-livance`.

- [ ] **Step 2: Stop and compare**

If the affected set does not match the audit, stop and investigate before
writing. An unexpected slug means the diff reconstruction is finding a swap the
audit did not — worth understanding, not worth applying blind.

- [ ] **Step 3: Real run**

Same invocation without `--dry-run`. Expect `unjudged=N` if the Anthropic
balance is still dry; that is the agreed policy, not a failure.

- [ ] **Step 4: Verify with the audit**

Re-run the read-only audit (scratchpad `audit_adaptations2.py`) via
`prod_run.py`.

Expected: **stale PROSE 0**, **stale INGREDIENT lines 0**, steps and required
ingredients still 0.

- [ ] **Step 5: Record the outcome**

Update the `adaptation-audit-2026-08-26` memory and the `resume-here`
breadcrumb with the final counts.
