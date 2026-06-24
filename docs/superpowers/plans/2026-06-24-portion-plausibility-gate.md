# Portion-Plausibility Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject recipes with physically implausible per-portion quantities (e.g. 680 g chicken/portion) at curation time, and provide a read-only audit to find existing offenders and calibrate thresholds.

**Architecture:** One pure detector function (`recipe_plausibility.py`) is the single source of truth. A read-only management command (`audit_portion_plausibility`) reports offenders + the per-portion mass distribution. The detector is wired into `curate_from_source` as a soft reject — the recipe simply never persists, consistent with curation's "never raises" contract.

**Tech Stack:** Django 5.1, Python, Django test runner (`manage.py test`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-24-portion-plausibility-gate-design.md`

**Commit convention:** every commit ends with the trailer
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
Work happens on branch `feat/portion-plausibility-gate` (already created).

---

## File Structure

- **Create** `diet_planner/services/recipe_plausibility.py` — pure detector: `check_portion_plausibility()`, `PlausibilityResult`, thresholds.
- **Create** `diet_planner/tests/test_recipe_plausibility.py` — detector unit tests (no DB).
- **Create** `diet_planner/management/commands/audit_portion_plausibility.py` — read-only audit report.
- **Create** `diet_planner/tests/test_audit_portion_plausibility.py` — command test (DB).
- **Modify** `diet_planner/services/recipe_curation.py` — add `enforce_plausibility` param to `curate_from_source` and the soft-reject check.
- **Create** `diet_planner/tests/test_curation_plausibility_gate.py` — gate integration test (mocks fetch + LLM).

Ingredient dict shape (from `map_ingredients`, `recipe_curation.py:152`): `{"name": str, "quantity": Any, "unit": str|None, "optional": bool, "canonical"?: str}`. The detector reads only `unit` and `quantity`.

---

## Task 1: Pure detector

**Files:**
- Create: `diet_planner/services/recipe_plausibility.py`
- Test: `diet_planner/tests/test_recipe_plausibility.py`

- [ ] **Step 1: Write the failing tests**

Create `diet_planner/tests/test_recipe_plausibility.py`:

```python
"""Tests for the pure portion-plausibility detector."""
from django.test import SimpleTestCase

from diet_planner.services.recipe_plausibility import (
    SINGLE_CAP_G,
    TOTAL_CEILING_G,
    check_portion_plausibility,
)


class CheckPortionPlausibilityTest(SimpleTestCase):
    def test_normal_dish_is_ok(self):
        ings = [
            {"name": "kuřecí prsa", "quantity": 600, "unit": "g"},   # 150 g/portion
            {"name": "rýže", "quantity": 320, "unit": "g"},          # 80 g/portion
            {"name": "sůl", "quantity": None, "unit": None},
        ]
        r = check_portion_plausibility(ings, base_servings=4)
        self.assertTrue(r.ok)
        self.assertEqual(r.reasons, [])
        self.assertEqual(r.per_portion_total_g, 230.0)

    def test_single_ingredient_over_cap_is_flagged(self):
        ings = [{"name": "kuřecí prsa", "quantity": 680, "unit": "g"}]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertFalse(r.ok)
        self.assertEqual(len(r.offenders), 1)
        self.assertEqual(r.offenders[0]["name"], "kuřecí prsa")
        self.assertTrue(any("kuřecí prsa" in reason for reason in r.reasons))

    def test_inflated_dish_trips_total_ceiling(self):
        # Six 300 g rows at base_servings=1 -> 1800 g/portion total, but no
        # single row exceeds the single cap. Total ceiling must catch it.
        ings = [{"name": f"i{n}", "quantity": 300, "unit": "g"} for n in range(6)]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertFalse(r.ok)
        self.assertEqual(r.offenders, [])
        self.assertTrue(any("total" in reason for reason in r.reasons))
        self.assertGreater(r.per_portion_total_g, TOTAL_CEILING_G)

    def test_ml_treated_as_grams(self):
        ings = [{"name": "vývar", "quantity": 500, "unit": "ml"}]  # 500 g/portion, under caps
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_total_g, 500.0)

    def test_pieces_and_to_taste_ignored(self):
        ings = [
            {"name": "vejce", "quantity": 12, "unit": "ks"},
            {"name": "pepř", "quantity": "dle chuti", "unit": None},
        ]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_total_g, 0.0)

    def test_czech_decimal_comma_quantity_parsed(self):
        ings = [{"name": "máslo", "quantity": "1,5", "unit": "g"}]
        r = check_portion_plausibility(ings, base_servings=1)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_total_g, 1.5)

    def test_zero_base_servings_treated_as_one(self):
        ings = [{"name": "kuře", "quantity": 680, "unit": "g"}]
        r = check_portion_plausibility(ings, base_servings=0)
        self.assertFalse(r.ok)
        self.assertEqual(r.per_portion_total_g, 680.0)

    def test_no_weighable_rows_is_ok(self):
        r = check_portion_plausibility([], base_servings=4)
        self.assertTrue(r.ok)
        self.assertEqual(r.per_portion_max_single_g, 0.0)

    def test_thresholds_are_numbers(self):
        self.assertIsInstance(SINGLE_CAP_G, float)
        self.assertIsInstance(TOTAL_CEILING_G, float)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python manage.py test diet_planner.tests.test_recipe_plausibility -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.recipe_plausibility'`.

- [ ] **Step 3: Write the detector**

Create `diet_planner/services/recipe_plausibility.py`:

```python
"""
Per-portion quantity plausibility detector for curated recipes.

Pure, no I/O, never raises. A recipe's ingredient quantities describe
`base_servings` portions; if `base_servings` is too low for the quantities
(the common curation error — it defaults to 1), every weighable ingredient is
inflated proportionally. We flag a recipe when the total weighable mass per
portion, or any single ingredient per portion, exceeds a plausibility ceiling.

`ml` is treated as `g` (food density ~1; adequate for a sanity gate). Pieces
(`ks`), to-taste rows, and non-numeric/non-positive quantities are ignored —
under-counting only makes the gate more conservative.

Thresholds are provisional constants, calibrated from
`manage.py audit_portion_plausibility` output before the gate is relied upon.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SINGLE_CAP_G = 500.0      # max weighable mass of one ingredient per portion
TOTAL_CEILING_G = 1200.0  # max total weighable mass per portion

_WEIGHABLE_UNITS = {"g", "ml"}


@dataclass
class PlausibilityResult:
    ok: bool
    reasons: List[str] = field(default_factory=list)
    per_portion_total_g: float = 0.0
    per_portion_max_single_g: float = 0.0
    offenders: List[Dict[str, Any]] = field(default_factory=list)


def _coerce_grams(quantity: Any) -> Optional[float]:
    """Parse a quantity into a positive float, tolerating Czech decimal commas.
    Returns None for missing / non-numeric / non-positive values."""
    if quantity is None or isinstance(quantity, bool):
        return None
    if isinstance(quantity, (int, float)):
        value = float(quantity)
    else:
        try:
            value = float(str(quantity).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None
    return value if value > 0 else None


def check_portion_plausibility(
    ingredients: List[Dict[str, Any]],
    base_servings: int,
) -> PlausibilityResult:
    servings = base_servings if isinstance(base_servings, int) and base_servings > 0 else 1

    total_g = 0.0
    max_single_g = 0.0
    offenders: List[Dict[str, Any]] = []

    for ing in ingredients or []:
        if not isinstance(ing, dict):
            continue
        unit = ing.get("unit")
        unit = unit.strip().lower() if isinstance(unit, str) else ""
        if unit not in _WEIGHABLE_UNITS:
            continue
        grams = _coerce_grams(ing.get("quantity"))
        if grams is None:
            continue
        total_g += grams
        per_portion = grams / servings
        if per_portion > max_single_g:
            max_single_g = per_portion
        if per_portion > SINGLE_CAP_G:
            offenders.append({
                "name": ing.get("name"),
                "grams_per_portion": round(per_portion, 1),
            })

    per_portion_total = total_g / servings

    reasons: List[str] = []
    if per_portion_total > TOTAL_CEILING_G:
        reasons.append(f"total {per_portion_total:.0f} g/portion > {TOTAL_CEILING_G:.0f}")
    for off in offenders:
        reasons.append(
            f"{off['name']}: {off['grams_per_portion']:.0f} g/portion > {SINGLE_CAP_G:.0f}"
        )

    return PlausibilityResult(
        ok=not reasons,
        reasons=reasons,
        per_portion_total_g=round(per_portion_total, 1),
        per_portion_max_single_g=round(max_single_g, 1),
        offenders=offenders,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python manage.py test diet_planner.tests.test_recipe_plausibility -v 2`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/recipe_plausibility.py diet_planner/tests/test_recipe_plausibility.py
git commit -m "feat(recipe): pure per-portion plausibility detector

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Read-only audit command

**Files:**
- Create: `diet_planner/management/commands/audit_portion_plausibility.py`
- Test: `diet_planner/tests/test_audit_portion_plausibility.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_audit_portion_plausibility.py`:

```python
"""Tests for the audit_portion_plausibility management command."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(slug, ingredients, *, base_servings=1, status=None):
    return CuratedRecipe.objects.create(
        name_cs=f"Recipe {slug}",
        slug=slug,
        status=status or CuratedRecipe.Status.PUBLISHED,
        meal_types=['lunch'],
        dietary_tags=[],
        cuisine='czech',
        difficulty=CuratedRecipe.Difficulty.EASY,
        ingredients=ingredients,
        instructions=[{'text': 'cook'}],
        base_servings=base_servings,
        base_nutrition={'calories': 500},
        source_url=f'https://example.test/{slug}',
        source_name='Example',
    )


class AuditPortionPlausibilityTest(TestCase):
    def test_flags_implausible_and_lists_offender(self):
        _recipe('good', [{'name': 'rýže', 'quantity': 320, 'unit': 'g'}], base_servings=4)
        _recipe('bad', [{'name': 'kuřecí prsa', 'quantity': 680, 'unit': 'g'}], base_servings=1)

        out = StringIO()
        call_command('audit_portion_plausibility', '--status', 'published', stdout=out)
        text = out.getvalue()

        self.assertIn('Scanned 2', text)
        self.assertIn('Flagged 1', text)
        self.assertIn('bad', text)
        self.assertNotIn('good:', text)  # 'good' is not listed as an offender row

    def test_status_filter_limits_scope(self):
        _recipe('draft-bad', [{'name': 'kuře', 'quantity': 680, 'unit': 'g'}],
                base_servings=1, status=CuratedRecipe.Status.DRAFT)

        out = StringIO()
        call_command('audit_portion_plausibility', '--status', 'published', stdout=out)
        self.assertIn('Scanned 0', out.getvalue())
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_audit_portion_plausibility -v 2`
Expected: FAIL — `Unknown command: 'audit_portion_plausibility'`.

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/audit_portion_plausibility.py`:

```python
"""
Audit per-portion quantity plausibility across the CuratedRecipe corpus.

Read-only. Flags recipes whose weighable mass per portion is implausibly high
(a base_servings mismatch inflates every ingredient). Use it to find offenders
and to calibrate the thresholds in
diet_planner/services/recipe_plausibility.py.

    python manage.py audit_portion_plausibility
    python manage.py audit_portion_plausibility --status all
    python manage.py audit_portion_plausibility --csv /tmp/audit.csv
"""
import csv

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services.recipe_plausibility import check_portion_plausibility

_FIELDS = [
    'slug', 'name_cs', 'base_servings', 'per_portion_total_g',
    'worst_ingredient', 'worst_g_per_portion', 'ok', 'reasons',
]


def _percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


class Command(BaseCommand):
    help = "Report recipes with implausible per-portion weighable mass (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            choices=['all', 'draft', 'vetted', 'published'],
            default='published',
            help="Limit to recipes of a given status (default: published).",
        )
        parser.add_argument('--csv', dest='csv_path', default=None,
                            help="Write per-recipe rows to this CSV path.")

    def handle(self, *args, **options):
        status = options['status']
        csv_path = options['csv_path']

        qs = CuratedRecipe.objects.all()
        if status != 'all':
            qs = qs.filter(status=status)

        rows = []
        totals = []
        flagged = []
        skipped = []
        for recipe in qs.iterator():
            try:
                r = check_portion_plausibility(recipe.ingredients or [], recipe.base_servings)
            except Exception as exc:  # never let one bad row abort the report
                skipped.append((recipe.slug, str(exc)))
                continue
            worst = max(r.offenders, key=lambda o: o['grams_per_portion'], default=None)
            row = {
                'slug': recipe.slug,
                'name_cs': recipe.name_cs,
                'base_servings': recipe.base_servings,
                'per_portion_total_g': r.per_portion_total_g,
                'worst_ingredient': worst['name'] if worst else '',
                'worst_g_per_portion': worst['grams_per_portion'] if worst else 0,
                'ok': r.ok,
                'reasons': '; '.join(r.reasons),
            }
            rows.append(row)
            totals.append(r.per_portion_total_g)
            if not r.ok:
                flagged.append(row)

        scanned = len(rows)
        self.stdout.write(f"Scanned {scanned} recipe(s) (status={status}).")
        if scanned:
            self.stdout.write(
                "per_portion_total_g  p50={:.0f}  p75={:.0f}  p90={:.0f}  "
                "p95={:.0f}  max={:.0f}".format(
                    _percentile(totals, 50), _percentile(totals, 75),
                    _percentile(totals, 90), _percentile(totals, 95), max(totals)))
            self.stdout.write(f"Flagged {len(flagged)} ({100 * len(flagged) / scanned:.0f}%).")
        else:
            self.stdout.write("Flagged 0.")

        for row in sorted(flagged, key=lambda r: r['per_portion_total_g'], reverse=True):
            self.stdout.write(
                "  [{base_servings}] {slug}: total {per_portion_total_g:.0f} g/p"
                " — {reasons}".format(**row))

        if skipped:
            self.stdout.write(f"Skipped {len(skipped)} row(s) with errors:")
            for slug, err in skipped:
                self.stdout.write(f"  {slug}: {err}")

        if csv_path:
            with open(csv_path, 'w', newline='') as fh:
                writer = csv.DictWriter(fh, fieldnames=_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(f"Wrote {len(rows)} row(s) to {csv_path}.")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_audit_portion_plausibility -v 2`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/audit_portion_plausibility.py diet_planner/tests/test_audit_portion_plausibility.py
git commit -m "feat(recipe): read-only portion-plausibility audit command

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Wire the gate into curation

**Files:**
- Modify: `diet_planner/services/recipe_curation.py` (`curate_from_source`, ~line 284 signature and ~line 348 reject block)
- Test: `diet_planner/tests/test_curation_plausibility_gate.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_curation_plausibility_gate.py`:

```python
"""Integration test: the plausibility gate rejects implausible recipes."""
from unittest.mock import patch

from django.test import TestCase

from diet_planner.models import CuratedRecipe
from diet_planner.services import recipe_curation

_CURATED_IMPLAUSIBLE = {
    "name_cs": "Pečené kuře",
    "name_en": "Roast chicken",
    "description": "Jednoduché pečené kuře.",
    "meal_types": ["lunch"],
    "cuisine": "czech",
    "difficulty": "easy",
    "dietary_tags": [],
    "ingredients": [{"name": "kuřecí prsa", "quantity": 680, "unit": "g"}],
    "instructions": [{"text": "Upeč kuře v troubě, dokud není propečené."}],
    "base_servings": 1,
    "base_nutrition": {"calories": 600},
    "prep_time": 10,
    "cook_time": 40,
}


class CurationPlausibilityGateTest(TestCase):
    def _run(self, enforce):
        with patch.object(recipe_curation, 'fetch_source', return_value='<html></html>'), \
             patch.object(recipe_curation, 'extract_jsonld_recipe', return_value=None), \
             patch.object(recipe_curation, 'cleaned_page_text', return_value='source text'), \
             patch.object(recipe_curation, 'GeminiService') as gem:
            gem.return_value.curate_recipe_to_czech.return_value = _CURATED_IMPLAUSIBLE
            return recipe_curation.curate_from_source(
                {"source_url": "https://example.test/kure", "source_name": "Example"},
                run_judge=False,
                enforce_plausibility=enforce,
            )

    def test_rejects_implausible_recipe(self):
        result = self._run(enforce=True)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertTrue(result.error.startswith("implausible portion:"))
        self.assertEqual(CuratedRecipe.objects.count(), 0)

    def test_allows_when_enforcement_disabled(self):
        result = self._run(enforce=False)
        self.assertTrue(result.ok)
        self.assertEqual(CuratedRecipe.objects.count(), 1)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_curation_plausibility_gate -v 2`
Expected: FAIL — `TypeError: curate_from_source() got an unexpected keyword argument 'enforce_plausibility'`.

- [ ] **Step 3: Add the import**

In `diet_planner/services/recipe_curation.py`, after the existing
`from diet_planner.services.canonical_lookup import resolve_canonical` import line, add:

```python
from diet_planner.services.recipe_plausibility import check_portion_plausibility
```

- [ ] **Step 4: Add the parameter**

In `diet_planner/services/recipe_curation.py`, change the `curate_from_source` signature (~line 284) from:

```python
def curate_from_source(
    entry: Dict[str, str],
    *,
    gemini: Optional[GeminiService] = None,
    run_judge: bool = True,
    persist: bool = True,
) -> CurationResult:
```

to:

```python
def curate_from_source(
    entry: Dict[str, str],
    *,
    gemini: Optional[GeminiService] = None,
    run_judge: bool = True,
    persist: bool = True,
    enforce_plausibility: bool = True,
) -> CurationResult:
```

- [ ] **Step 5: Add the soft-reject check**

In `diet_planner/services/recipe_curation.py`, find this existing block (~line 348):

```python
    if not fields["instructions"]:
        result.error = "no instructions after curation"
        return result

    recipe = CuratedRecipe(**fields)
```

Insert the plausibility check between the instructions guard and the `recipe = CuratedRecipe(**fields)` line so it reads:

```python
    if not fields["instructions"]:
        result.error = "no instructions after curation"
        return result

    if enforce_plausibility:
        plausibility = check_portion_plausibility(
            fields["ingredients"], fields["base_servings"]
        )
        if not plausibility.ok:
            result.error = "implausible portion: " + "; ".join(plausibility.reasons)
            return result

    recipe = CuratedRecipe(**fields)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_curation_plausibility_gate -v 2`
Expected: PASS (2 tests).

- [ ] **Step 7: Run the full recipe test group to check for regressions**

Run: `python manage.py test diet_planner.tests.test_recipe_plausibility diet_planner.tests.test_audit_portion_plausibility diet_planner.tests.test_curation_plausibility_gate -v 2`
Expected: PASS (13 tests total).

- [ ] **Step 8: Commit**

```bash
git add diet_planner/services/recipe_curation.py diet_planner/tests/test_curation_plausibility_gate.py
git commit -m "feat(recipe): gate curation on per-portion plausibility

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Post-Implementation (manual, not part of the coding tasks)

These are operational follow-ups, tracked here so they aren't lost:

1. **Calibrate** — run `python manage.py audit_portion_plausibility --status published`
   against prod (372 recipes) via the DO Console harness (`[[recipe-curation-trigger]]`).
   Read the p90/p95/max distribution; adjust `SINGLE_CAP_G` / `TOTAL_CEILING_G`
   in `recipe_plausibility.py` if the defaults misfire; commit.
2. **Triage** — fix the flagged existing recipes by hand (correct `base_servings`
   or unpublish). The gate only protects *new* curation; existing offenders are
   not auto-repaired (out of scope by design).
3. **Follow-up spec** — the "1,5 vejce" fractional-discrete-unit rounding is a
   separate frontend issue (`frontend/src/lib/portions.ts`); brainstorm it on its own.

---

## Notes for the implementer

- Run tests with the Django test runner: `python manage.py test <dotted.path> -v 2`.
  Tests use `SimpleTestCase` (no DB) for the detector and `TestCase` (DB) for the
  command and gate.
- The detector reads only `unit` and `quantity` from each ingredient dict; it
  never touches the network or the DB. Keep it that way.
- `curate_from_source` must never raise — the gate sets `result.error` and
  returns, exactly like the existing `"no instructions after curation"` path.
