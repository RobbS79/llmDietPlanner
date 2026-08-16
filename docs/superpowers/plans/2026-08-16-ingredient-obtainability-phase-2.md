# Ingredient Obtainability — Phase 2 (Substitute, Unpublish, Rank) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the 164 published recipes that fail the one-stop-shop bar into Czech-shoppable versions using an owner-reviewed substitution table, demote the residue that cannot be saved, and teach the ranker to prefer easy-to-shop recipes.

**Architecture:** A git-tracked YAML substitution table (`ingredient_substitutions_cz.yaml`) loads into the existing `IngredientSubstitute` model with a new `purpose='availability'`. A pure planner decides, per recipe, whether *every* blocker is covered by the table — partial coverage is never applied, because a recipe with one remaining unbuyable item is still an unbuyable recipe. Covered recipes get their ingredient rows rewritten mechanically, their affected instruction steps rewritten by a bounded LLM pass, and the whole rewrite is discarded if the existing coherence judge rejects it. What survives as `specialty` afterwards is demoted to `draft`, never deleted. Finally the ranker excludes `specialty` and applies a small per-blocker penalty behind its own flag.

**Tech Stack:** Django 5.1 management commands, PostgreSQL (Supabase), Gemini via `google.generativeai`, `manage.py test` (Django TestCase — this repo has no pytest).

**Predecessor:** `docs/superpowers/plans/2026-08-11-ingredient-obtainability-phase-1.md` (complete, merged as `ed7ead6`). Spec: `docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md` §6, §7, §8.

**Measured starting point** (`docs/shopping-difficulty-report-2026-08-11.txt`): 458 published, 294 common / 85 findable / 79 specialty. Top blockers by recipe cost: `vanilla-extract` 37, `maple-syrup` 26, `coriander` 25, `kale` 14, `tahini` 13, `almond-butter` 9, `avocado-oil` 8, `tofu` 7, `mint` 7.

---

## File Structure

| File | Responsibility |
|---|---|
| `diet_planner/models/catalog.py` (modify, ~line 187) | `IngredientSubstitute.Purpose` choices + `purpose` + `substitute_unit` fields |
| `diet_planner/migrations/0037_substitute_purpose.py` (create) | The two new columns |
| `diet_planner/data/canonical_ingredients.yaml` (modify, ~line 2031) | Split `vanilla-aroma` out of `vanilla` |
| `diet_planner/data/ingredient_availability.yaml` (modify) | Rate the new `vanilla-aroma` canonical |
| `diet_planner/data/ingredient_substitutions_cz.yaml` (create) | The owner-reviewed swap table |
| `diet_planner/management/commands/load_availability_substitutions.py` (create) | YAML → `IngredientSubstitute` rows, idempotent |
| `diet_planner/services/ingredient_substitution.py` (create) | Pure planner: `substitution_table()`, `plan_substitutions()` — no LLM, no DB writes |
| `diet_planner/services/substitution_rewrite.py` (create) | The bounded LLM instruction-step rewrite |
| `diet_planner/management/commands/apply_availability_substitutions.py` (create) | Orchestrates: plan → rewrite → judge → snapshot → recompute |
| `diet_planner/management/commands/unpublish_unshoppable.py` (create) | `specialty` + published → draft |
| `diet_planner/services/recipe_retrieval.py` (modify, ~425 and ~515) | Exclude `specialty`; blocker penalty |
| `llm_diet_planner_project/settings.py` (modify, ~line 389) | `AVAILABILITY_RANKING_ENABLED` |
| `diet_planner/tests/test_ingredient_substitution.py` (create) | Planner unit tests |
| `diet_planner/tests/test_substitution_rewrite.py` (create) | LLM rewrite tests (injected fake `generate`) |
| `diet_planner/tests/test_apply_substitutions.py` (create) | Command tests incl. judge-rejection and dry-run |
| `diet_planner/tests/test_availability_ranking.py` (create) | Ranking gate + penalty tests |

**Two services, not one.** `ingredient_substitution.py` is pure and fully testable without mocking an LLM; `substitution_rewrite.py` is the only file that talks to Gemini. Keeping them apart is what lets Task 4's tests run offline and fast.

**Test command for this repo:** `docker-compose run --rm web python manage.py test <dotted.path> -v 1`. There is no pytest in the container — `python -m pytest` fails with "No module named pytest".

---

### Task 1: `IngredientSubstitute.purpose` + `substitute_unit`

**Files:**
- Modify: `diet_planner/models/catalog.py:187-219`
- Create: `diet_planner/migrations/0037_substitute_purpose.py` (generated)
- Test: `diet_planner/tests/test_ingredient_substitution.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_ingredient_substitution.py`:

```python
"""Availability substitution: model fields and the pure planner."""
from django.test import TestCase

from diet_planner.models import CanonicalIngredient
from diet_planner.models.catalog import IngredientSubstitute


class SubstitutePurposeFieldTests(TestCase):
    def setUp(self):
        self.a = CanonicalIngredient.objects.create(name='tamari', slug='tamari')
        self.b = CanonicalIngredient.objects.create(
            name='soy sauce', slug='soy-sauce', name_cs='sójová omáčka')

    def test_purpose_defaults_to_preference(self):
        """Existing rows must keep behaving exactly as before the migration."""
        sub = IngredientSubstitute.objects.create(ingredient=self.a, substitute=self.b)
        self.assertEqual(sub.purpose, IngredientSubstitute.Purpose.PREFERENCE)

    def test_substitute_unit_defaults_blank(self):
        sub = IngredientSubstitute.objects.create(ingredient=self.a, substitute=self.b)
        self.assertEqual(sub.substitute_unit, '')

    def test_availability_purpose_is_settable(self):
        sub = IngredientSubstitute.objects.create(
            ingredient=self.a, substitute=self.b,
            purpose=IngredientSubstitute.Purpose.AVAILABILITY,
            substitute_unit='ml',
        )
        sub.refresh_from_db()
        self.assertEqual(sub.purpose, 'availability')
        self.assertEqual(sub.substitute_unit, 'ml')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution -v 1`

Expected: FAIL — `AttributeError: type object 'IngredientSubstitute' has no attribute 'Purpose'`

- [ ] **Step 3: Add the choices class and fields**

In `diet_planner/models/catalog.py`, inside `class IngredientSubstitute`, directly after the docstring on line 188:

```python
class IngredientSubstitute(models.Model):
    """Substitutability between canonical ingredients."""

    class Purpose(models.TextChoices):
        PREFERENCE = 'preference', 'General preference'
        DIETARY = 'dietary', 'Dietary restriction'
        AVAILABILITY = 'availability', 'Czech shop availability'

    ingredient = models.ForeignKey(
```

Then after the `conversion_factor` field (line 210), before `class Meta`:

```python
    purpose = models.CharField(
        max_length=12,
        choices=Purpose.choices,
        default=Purpose.PREFERENCE,
        db_index=True,
        help_text="Why this swap exists; 'availability' rows drive the CZ rewrite",
    )
    # conversion_factor is a scalar, but "1 lžička vanilkového extraktu ->
    # 1 sáček vanilkového cukru" changes the unit, not just the number.
    substitute_unit = models.CharField(
        max_length=20, blank=True,
        help_text="Unit after substitution; blank keeps the original",
    )
```

- [ ] **Step 4: Generate the migration**

```bash
docker-compose run --rm web python manage.py makemigrations diet_planner --name substitute_purpose
```

Expected: `Migrations for 'diet_planner': 0037_substitute_purpose.py — Add field purpose to ingredientsubstitute, Add field substitute_unit to ingredientsubstitute`

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution -v 1`

Expected: `Ran 3 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/models/catalog.py diet_planner/migrations/0037_substitute_purpose.py diet_planner/tests/test_ingredient_substitution.py
git commit -m "feat(catalog): purpose + substitute_unit on IngredientSubstitute"
```

---

### Task 2: Split `vanilla-aroma` out of `vanilla`

**Why this task exists:** the corpus's single largest blocker is `vanilla-extract` (37 recipes) and the owner-settled swap is *vanilkové aroma*. But `vanilkové aroma` is currently an **alias** of the `vanilla` canonical (`canonical_ingredients.yaml:2039`), whose `name_cs` is "vanilka". Rewriting through it would print "vanilka" on the ingredient line instead of "vanilkové aroma". Per `[[ingredient-mapping-normalizer]]`, distinct products must be distinct canonicals, not aliases.

**Files:**
- Modify: `diet_planner/data/canonical_ingredients.yaml:2031-2041`
- Modify: `diet_planner/data/ingredient_availability.yaml`
- Test: `diet_planner/tests/test_ingredient_substitution.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_ingredient_substitution.py`:

```python
from django.core.management import call_command
from io import StringIO


class VanillaAromaCanonicalTests(TestCase):
    """vanilkové aroma is a product you buy, not a synonym for vanilka."""

    def test_seed_creates_distinct_vanilla_aroma(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        aroma = CanonicalIngredient.objects.filter(slug='vanilla-aroma').first()
        self.assertIsNotNone(aroma, "vanilla-aroma canonical missing")
        self.assertEqual(aroma.name_cs, 'vanilkové aroma')

    def test_vanilla_no_longer_aliases_aroma(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        from diet_planner.services.canonical_lookup import resolve_canonical
        resolved = resolve_canonical('vanilkové aroma')
        self.assertIsNotNone(resolved)
        self.assertEqual(
            resolved.slug, 'vanilla-aroma',
            "vanilkové aroma must resolve to its own canonical, not vanilka")

    def test_vanilla_aroma_is_rated_common(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        aroma = CanonicalIngredient.objects.get(slug='vanilla-aroma')
        self.assertEqual(aroma.availability, 'common')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution.VanillaAromaCanonicalTests -v 1`

Expected: FAIL — `vanilla-aroma canonical missing`

- [ ] **Step 3: Edit the canonical YAML**

In `diet_planner/data/canonical_ingredients.yaml`, replace lines 2031-2041 (the `vanilla` entry) with:

```yaml
- name: vanilla
  name_cs: vanilka
  category: baking
  default_unit: g
  is_pantry_staple: true
  estimated_price_czk: 40.0
  estimated_price_eur: 1.60
  aliases:
    - { alias: "vanilkový lusk", language_code: cs }

# Split out of `vanilla` 2026-08-16: this is the swap target for vanilkový
# extrakt (37 recipes), so it must carry its own name_cs — rewriting through
# `vanilla` would print "vanilka" on the ingredient line. 20-40 ml lahvička,
# every Czech supermarket's baking aisle.
- name: vanilla aroma
  name_cs: vanilkové aroma
  category: baking
  default_unit: ml
  estimated_price_czk: 15.0
  estimated_price_eur: 0.60
  aliases:
    - { alias: "vanilkové aroma", language_code: cs }
    - { alias: "vanilková esence", language_code: cs }
    - { alias: "vanilkova esence", language_code: cs }
```

- [ ] **Step 4: Rate the new canonical**

`rate_ingredient_availability` fails loudly on a canonical missing from the YAML (Phase 1, Task 5), so this edit is mandatory, not optional. Add to `diet_planner/data/ingredient_availability.yaml`, keeping the file's existing alphabetical-by-slug ordering (insert next to the other `vanilla-*` slugs near line 1107):

```yaml
- slug: vanilla-aroma
  availability: common
  confidence: owner
  note: 'SETTLED by owner 2026-08-11: the CZ equivalent of vanilla extract.
    Small bottle, every supermarket baking aisle. Swap target for
    vanilla-extract (37 recipes).'
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution -v 1`

Expected: `Ran 6 tests ... OK`

- [ ] **Step 6: Verify no existing canonical regressed**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_availability diet_planner.tests.test_rate_ingredient_availability -v 1`

Expected: `Ran 37 tests ... OK` (the Phase 1 suite; `rate_ingredient_availability` must not report an unrated canonical)

- [ ] **Step 7: Commit**

```bash
git add diet_planner/data/canonical_ingredients.yaml diet_planner/data/ingredient_availability.yaml diet_planner/tests/test_ingredient_substitution.py
git commit -m "feat(catalog): vanilkové aroma becomes its own canonical"
```

---

### Task 3: The substitution seed table

**Files:**
- Create: `diet_planner/data/ingredient_substitutions_cz.yaml`
- Create: `diet_planner/management/commands/load_availability_substitutions.py`
- Test: `diet_planner/tests/test_ingredient_substitution.py`

The spec's saveable/not-saveable split (§6) is the authority. **Only saveable swaps go in this file.** An ingredient that *is* the dish (tahini in a tahini dressing, nori in a sushi miska) gets no row, which routes its recipes to Task 7's unpublish instead.

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_ingredient_substitution.py`:

```python
class LoadSubstitutionsTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())

    def test_load_creates_availability_rows(self):
        out = StringIO()
        call_command('load_availability_substitutions', stdout=out)
        row = IngredientSubstitute.objects.filter(
            ingredient__slug='vanilla-extract', substitute__slug='vanilla-aroma',
        ).first()
        self.assertIsNotNone(row, "vanilla-extract -> vanilla-aroma row missing")
        self.assertEqual(row.purpose, IngredientSubstitute.Purpose.AVAILABILITY)
        self.assertIn('loaded=', out.getvalue())

    def test_load_is_idempotent(self):
        call_command('load_availability_substitutions', stdout=StringIO())
        first = IngredientSubstitute.objects.count()
        out = StringIO()
        call_command('load_availability_substitutions', stdout=out)
        self.assertEqual(IngredientSubstitute.objects.count(), first)
        self.assertIn('created=0', out.getvalue())

    def test_load_does_not_touch_preference_rows(self):
        """A hand-made preference row for the same pair must survive untouched."""
        a = CanonicalIngredient.objects.get(slug='vanilla-extract')
        b = CanonicalIngredient.objects.get(slug='vanilla-sugar')
        IngredientSubstitute.objects.create(ingredient=a, substitute=b)
        call_command('load_availability_substitutions', stdout=StringIO())
        row = IngredientSubstitute.objects.get(ingredient=a, substitute=b)
        self.assertEqual(row.purpose, IngredientSubstitute.Purpose.PREFERENCE)

    def test_unknown_slug_fails_loudly(self):
        """A typo in the table must not silently skip a swap."""
        from django.core.management.base import CommandError
        import tempfile, os
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as fh:
            fh.write("- ingredient: no-such-slug\n  substitute: vanilla-aroma\n")
            path = fh.name
        try:
            with self.assertRaises(CommandError) as ctx:
                call_command('load_availability_substitutions', f'--path={path}',
                             stdout=StringIO())
            self.assertIn('no-such-slug', str(ctx.exception))
        finally:
            os.unlink(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution.LoadSubstitutionsTests -v 1`

Expected: FAIL — `CommandError: Unknown command: 'load_availability_substitutions'`

- [ ] **Step 3: Write the seed table**

Create `diet_planner/data/ingredient_substitutions_cz.yaml`:

```yaml
# Czech-availability substitutions. Loaded into IngredientSubstitute with
# purpose='availability' by `manage.py load_availability_substitutions`.
#
# Schema per entry:
#   ingredient:        Required. Canonical slug of the hard-to-buy item.
#   substitute:        Required. Canonical slug of the CZ-shoppable swap.
#   quality_score:     0-1, default 0.80. 1.0 = indistinguishable in the dish.
#   conversion_factor: Multiply the quantity by this. Default 1.0.
#   substitute_unit:   Unit AFTER the swap; omit to keep the original unit.
#   note:              Why this swap is faithful. Read by the owner, not code.
#
# ONLY faithful swaps belong here. If the ingredient IS the dish (tahini in a
# tahini dressing, nori in a sushi miska, zelená kari pasta in thajské kari),
# leave it out — those recipes are meant to fall through to unpublish.

- ingredient: vanilla-extract
  substitute: vanilla-aroma
  quality_score: 0.95
  conversion_factor: 1.0
  substitute_unit: ml
  note: 'OWNER-SETTLED 2026-08-11. Extract is not sold in CZ; aroma is the
    local equivalent and used 1:1 in the same volumes. 37 recipes.'

- ingredient: maple-syrup
  substitute: honey
  quality_score: 0.85
  conversion_factor: 1.0
  note: 'OWNER: "med is the swap". Sweetness and viscosity are close enough
    for bakes, porridges and dressings. 26 recipes.'

- ingredient: tamari
  substitute: soy-sauce
  quality_score: 0.95
  conversion_factor: 1.0
  note: 'Same product minus the gluten-free guarantee. NOTE: recipes tagged
    gluten_free are excluded from this swap by the planner (Task 4).'

- ingredient: avocado-oil
  substitute: rapeseed-oil
  quality_score: 0.90
  conversion_factor: 1.0
  note: 'Neutral high-smoke-point oil; interchangeable for frying and roasting.'

- ingredient: almond-butter
  substitute: peanut-butter
  quality_score: 0.75
  conversion_factor: 1.0
  note: 'Both are nut butters used the same way. Flavour differs, dish holds.'

- ingredient: oat-flour
  substitute: oats
  quality_score: 0.90
  conversion_factor: 1.0
  note: 'Oat flour IS ground oats — the instruction rewrite adds the grinding
    step, which is exactly what the LLM pass is for.'

- ingredient: rice-vinegar
  substitute: white-wine-vinegar
  quality_score: 0.80
  conversion_factor: 1.0
  note: 'Mild acid; closest ordinary-supermarket vinegar by sharpness.'

- ingredient: sesame-oil
  substitute: rapeseed-oil
  quality_score: 0.60
  conversion_factor: 1.0
  note: 'Weakest swap in the table — sesame oil is a finishing aroma. Kept
    because the alternative is dropping the recipe; the judge is the backstop.'

- ingredient: coconut-sugar
  substitute: brown-sugar
  quality_score: 0.90
  conversion_factor: 1.0
  note: 'Same role, same quantity, ordinary supermarket shelf.'

- ingredient: almond-flour
  substitute: ground-almonds
  quality_score: 0.95
  conversion_factor: 1.0
  note: 'Mletá mandle is the same product under the CZ name.'
```

**Do not invent the swap target's slug.** Before committing, confirm each `substitute` slug exists:

```bash
docker-compose run --rm web python manage.py shell -c "
import yaml
from diet_planner.models import CanonicalIngredient
rows = yaml.safe_load(open('diet_planner/data/ingredient_substitutions_cz.yaml'))
have = set(CanonicalIngredient.objects.values_list('slug', flat=True))
missing = sorted({s for r in rows for s in (r['ingredient'], r['substitute'])} - have)
print('MISSING:', missing or 'none')
"
```

Expected: `MISSING: none`. If a slug is missing, add that canonical to `canonical_ingredients.yaml` **and** rate it in `ingredient_availability.yaml` (the rating command fails loudly otherwise) before continuing.

- [ ] **Step 4: Write the loader command**

Create `diet_planner/management/commands/load_availability_substitutions.py`:

```python
"""Load the Czech-availability substitution table into IngredientSubstitute.

Idempotent: re-running updates the swap's numbers but never duplicates a row,
and never touches rows whose purpose is not 'availability' (those are
hand-made preference/dietary swaps that predate this table).
"""
from decimal import Decimal
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import CanonicalIngredient
from diet_planner.models.catalog import IngredientSubstitute

DEFAULT_PATH = Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'ingredient_substitutions_cz.yaml'


class Command(BaseCommand):
    help = 'Load ingredient_substitutions_cz.yaml into IngredientSubstitute.'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=str(DEFAULT_PATH))
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')

    def handle(self, *args, **options):
        rows = yaml.safe_load(Path(options['path']).read_text(encoding='utf-8')) or []
        by_slug = {c.slug: c for c in CanonicalIngredient.objects.all()}

        # Resolve everything BEFORE writing anything: a typo must not leave a
        # half-loaded table behind.
        missing = sorted({
            slug
            for row in rows
            for slug in (row.get('ingredient'), row.get('substitute'))
            if slug not in by_slug
        })
        if missing:
            raise CommandError(
                f"unknown canonical slug(s) in {options['path']}: {', '.join(missing)}")

        created = updated = 0
        for row in rows:
            ing = by_slug[row['ingredient']]
            sub = by_slug[row['substitute']]
            defaults = {
                'purpose': IngredientSubstitute.Purpose.AVAILABILITY,
                'quality_score': Decimal(str(row.get('quality_score', 0.80))),
                'conversion_factor': Decimal(str(row.get('conversion_factor', 1.0))),
                'substitute_unit': row.get('substitute_unit', '') or '',
            }
            existing = IngredientSubstitute.objects.filter(
                ingredient=ing, substitute=sub).first()

            if existing is None:
                created += 1
                if not options['dry_run']:
                    IngredientSubstitute.objects.create(
                        ingredient=ing, substitute=sub, **defaults)
                continue

            # Never rewrite a hand-made preference/dietary row.
            if existing.purpose != IngredientSubstitute.Purpose.AVAILABILITY:
                self.stdout.write(
                    f'  skip {ing.slug} -> {sub.slug} (purpose={existing.purpose})')
                continue

            if any(getattr(existing, k) != v for k, v in defaults.items()):
                updated += 1
                if not options['dry_run']:
                    for k, v in defaults.items():
                        setattr(existing, k, v)
                    existing.save(update_fields=list(defaults))

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}loaded={len(rows)} created={created} updated={updated}'))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution -v 1`

Expected: `Ran 10 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/data/ingredient_substitutions_cz.yaml diet_planner/management/commands/load_availability_substitutions.py diet_planner/tests/test_ingredient_substitution.py
git commit -m "feat(availability): Czech substitution table and its loader"
```

---

### Task 4: The pure substitution planner

**Files:**
- Create: `diet_planner/services/ingredient_substitution.py`
- Test: `diet_planner/tests/test_ingredient_substitution.py`

This is the decision layer: no LLM, no writes. It answers *"can this recipe be fully saved, and what exactly changes?"*

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_ingredient_substitution.py`:

```python
from diet_planner.models import CuratedRecipe


def _recipe(**kw):
    defaults = dict(
        slug='test-recipe', name_cs='Testovací recept',
        meal_types=['dinner'], ingredients=[], instructions=[],
        base_servings=2, source_url='https://example.com/r',
        source_name='Example', status=CuratedRecipe.Status.PUBLISHED,
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class PlanSubstitutionsTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())
        from diet_planner.services.ingredient_substitution import substitution_table
        self.table = substitution_table()

    def test_fully_covered_recipe_is_saveable(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertTrue(plan.saveable)
        self.assertEqual(len(plan.changes), 1)
        change = plan.changes[0]
        self.assertEqual(change.old_name, 'vanilkový extrakt')
        self.assertEqual(change.new_name, 'vanilkové aroma')
        self.assertEqual(change.new_canonical, 'vanilla-aroma')
        self.assertEqual(change.new_unit, 'ml')

    def test_partially_covered_recipe_is_not_saveable(self):
        """One uncovered blocker leaves the recipe unbuyable — change nothing."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'tahini', 'canonical': 'tahini', 'quantity': 30, 'unit': 'g'},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.uncovered, ['tahini'])
        self.assertEqual(plan.changes, [])

    def test_common_recipe_needs_no_plan(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'}])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.changes, [])
        self.assertEqual(plan.uncovered, [])

    def test_conversion_factor_scales_quantity(self):
        from diet_planner.services.ingredient_substitution import (
            SubstitutionRule, plan_substitutions,
        )
        table = {'vanilla-extract': SubstitutionRule(
            old_slug='vanilla-extract', new_slug='vanilla-aroma',
            new_name='vanilkové aroma', conversion_factor=2.0,
            new_unit='ml', quality_score=0.9)}
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 3, 'unit': 'lžička'}])
        plan = plan_substitutions(r, table)
        self.assertEqual(plan.changes[0].new_quantity, 6.0)

    def test_stale_catalog_id_is_dropped(self):
        """catalog_id points at a StoreProduct for the OLD ingredient."""
        from diet_planner.services.ingredient_substitution import (
            apply_changes_to_ingredients, plan_substitutions,
        )
        r = _recipe(ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička', 'catalog_id': 4242}])
        plan = plan_substitutions(r, self.table)
        rewritten = apply_changes_to_ingredients(r.ingredients, plan)
        self.assertNotIn('catalog_id', rewritten[0])
        self.assertEqual(rewritten[0]['canonical'], 'vanilla-aroma')
        self.assertEqual(rewritten[0]['name'], 'vanilkové aroma')

    def test_gluten_free_recipe_refuses_gluten_bearing_swap(self):
        """tamari -> soy sauce silently breaks a gluten_free promise."""
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(dietary_tags=['gluten_free'], ingredients=[
            {'name': 'tamari', 'canonical': 'tamari', 'quantity': 20, 'unit': 'ml'}])
        plan = plan_substitutions(r, self.table)
        self.assertFalse(plan.saveable)
        self.assertEqual(plan.uncovered, ['tamari'])

    def test_optional_ingredients_are_ignored(self):
        from diet_planner.services.ingredient_substitution import plan_substitutions
        r = _recipe(ingredients=[
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
            {'name': 'tahini', 'canonical': 'tahini', 'quantity': 30,
             'unit': 'g', 'optional': True},
        ])
        plan = plan_substitutions(r, self.table)
        self.assertEqual(plan.uncovered, [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution.PlanSubstitutionsTests -v 1`

Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.ingredient_substitution'`

- [ ] **Step 3: Write the planner**

Create `diet_planner/services/ingredient_substitution.py`:

```python
"""Deciding whether an unshoppable recipe can be rewritten into a shoppable one.

Pure: no LLM, no writes. The command in
`management/commands/apply_availability_substitutions.py` owns the side
effects; everything here is a function of (recipe, table).

See docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md §6
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from diet_planner.models.catalog import Availability, IngredientSubstitute
from diet_planner.services.ingredient_availability import (
    _dict_entries,
    _entry_availability,
    availability_index,
)

#: Swaps that would quietly break a dietary promise the recipe makes. The
#: substitute is fine in general; it is not fine in a recipe carrying this tag.
_TAG_INCOMPATIBLE = {
    'gluten_free': {'soy-sauce', 'wheat-flour', 'oats', 'barley', 'couscous'},
    'vegan': {'honey', 'butter', 'yogurt', 'milk', 'eggs'},
    'dairy_free': {'butter', 'yogurt', 'milk', 'cream'},
}


@dataclass(frozen=True)
class SubstitutionRule:
    old_slug: str
    new_slug: str
    new_name: str
    conversion_factor: float
    new_unit: str
    quality_score: float


@dataclass(frozen=True)
class IngredientChange:
    index: int
    old_name: str
    old_slug: str
    new_name: str
    new_canonical: str
    new_quantity: float | None
    new_unit: str


@dataclass
class SubstitutionPlan:
    saveable: bool = False
    changes: List[IngredientChange] = field(default_factory=list)
    uncovered: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """The adaptation_note body: 'tamari → sójová omáčka, ...'."""
        return ', '.join(f'{c.old_name} → {c.new_name}' for c in self.changes)


def substitution_table() -> Dict[str, SubstitutionRule]:
    """slug -> best availability swap. Highest quality_score wins a tie."""
    rows = (
        IngredientSubstitute.objects
        .filter(purpose=IngredientSubstitute.Purpose.AVAILABILITY)
        .select_related('ingredient', 'substitute')
        .order_by('-quality_score')
    )
    table: Dict[str, SubstitutionRule] = {}
    for row in rows:
        if row.ingredient.slug in table:
            continue  # already have a better-scoring swap
        table[row.ingredient.slug] = SubstitutionRule(
            old_slug=row.ingredient.slug,
            new_slug=row.substitute.slug,
            new_name=row.substitute.name_cs or row.substitute.name,
            conversion_factor=float(row.conversion_factor),
            new_unit=row.substitute_unit or '',
            quality_score=float(row.quality_score),
        )
    return table


def _breaks_dietary_promise(recipe, rule: SubstitutionRule) -> bool:
    for tag in (recipe.dietary_tags or []):
        if rule.new_slug in _TAG_INCOMPATIBLE.get(tag, ()):
            return True
    return False


def plan_substitutions(recipe, table: Dict[str, SubstitutionRule],
                       index: Dict[str, str] | None = None) -> SubstitutionPlan:
    """What it would take to make `recipe` shoppable.

    `saveable` is True only when EVERY blocker is covered. Partial coverage is
    worthless: a recipe with one remaining unbuyable ingredient still fails the
    one-stop bar, and we would have rewritten a sourced recipe for nothing.
    """
    if index is None:
        index = availability_index()

    plan = SubstitutionPlan()
    entries = recipe.ingredients or []

    for position, ing in enumerate(entries):
        if not isinstance(ing, dict) or ing.get('optional'):
            continue
        availability, key = _entry_availability(ing, index)
        if availability == Availability.COMMON:
            continue

        rule = table.get(key)
        if rule is None or _breaks_dietary_promise(recipe, rule):
            plan.uncovered.append(key)
            continue

        quantity = ing.get('quantity')
        try:
            new_quantity = (
                round(float(quantity) * rule.conversion_factor, 3)
                if quantity is not None else None
            )
        except (TypeError, ValueError):
            new_quantity = None

        plan.changes.append(IngredientChange(
            index=position,
            old_name=(ing.get('name') or '').strip(),
            old_slug=key,
            new_name=rule.new_name,
            new_canonical=rule.new_slug,
            new_quantity=new_quantity,
            new_unit=rule.new_unit or (ing.get('unit') or ''),
        ))

    plan.uncovered = sorted(set(plan.uncovered))
    plan.saveable = bool(plan.changes) and not plan.uncovered
    if not plan.saveable:
        plan.changes = []
    return plan


def apply_changes_to_ingredients(ingredients, plan: SubstitutionPlan) -> List[dict]:
    """A NEW ingredients list with the plan applied. Does not mutate the input."""
    out = [dict(ing) if isinstance(ing, dict) else ing for ing in (ingredients or [])]
    for change in plan.changes:
        entry = out[change.index]
        entry['name'] = change.new_name
        entry['canonical'] = change.new_canonical
        if change.new_quantity is not None:
            entry['quantity'] = change.new_quantity
        if change.new_unit:
            entry['unit'] = change.new_unit
        # Points at a StoreProduct for the ingredient we just replaced.
        entry.pop('catalog_id', None)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_ingredient_substitution -v 1`

Expected: `Ran 17 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/ingredient_substitution.py diet_planner/tests/test_ingredient_substitution.py
git commit -m "feat(availability): pure substitution planner, all-or-nothing coverage"
```

---

### Task 5: The bounded instruction rewrite

**Files:**
- Create: `diet_planner/services/substitution_rewrite.py`
- Test: `diet_planner/tests/test_substitution_rewrite.py`

Only steps whose text names a swapped ingredient are sent to the LLM. Everything else is passed through verbatim — an unbounded "regenerate the recipe" call is exactly how a sourced recipe silently becomes a different dish.

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_substitution_rewrite.py`:

```python
"""The LLM instruction rewrite: bounded, fail-closed, no silent regeneration."""
import json

from django.test import TestCase

from diet_planner.services.ingredient_substitution import IngredientChange, SubstitutionPlan


def _plan():
    return SubstitutionPlan(saveable=True, changes=[IngredientChange(
        index=0, old_name='vanilkový extrakt', old_slug='vanilla-extract',
        new_name='vanilkové aroma', new_canonical='vanilla-aroma',
        new_quantity=1.0, new_unit='ml')])


class RewriteInstructionsTests(TestCase):
    def test_only_affected_steps_are_sent_to_the_llm(self):
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = [
            {'text': 'Smíchejte mouku a cukr.', 'time_min': 2},
            {'text': 'Přidejte vanilkový extrakt.', 'time_min': 1},
        ]
        seen = {}

        def fake_generate(prompt):
            seen['prompt'] = prompt
            return json.dumps({'steps': [
                {'text': 'Přidejte vanilkové aroma.', 'time_min': 1}]})

        out = rewrite_instructions(steps, _plan(), generate=fake_generate)
        self.assertEqual(out[0]['text'], 'Smíchejte mouku a cukr.')
        self.assertEqual(out[1]['text'], 'Přidejte vanilkové aroma.')
        self.assertIn('vanilkový extrakt', seen['prompt'])
        self.assertNotIn('Smíchejte mouku a cukr', seen['prompt'],
                         "unaffected step must not be sent for regeneration")

    def test_no_affected_step_skips_the_llm_entirely(self):
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = [{'text': 'Smíchejte mouku a cukr.', 'time_min': 2}]

        def explode(prompt):
            raise AssertionError('LLM must not be called')

        out = rewrite_instructions(steps, _plan(), generate=explode)
        self.assertEqual(out, steps)

    def test_step_count_mismatch_fails_closed(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions,
        )
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}]

        def bad_generate(prompt):
            return json.dumps({'steps': [{'text': 'a'}, {'text': 'b'}]})

        with self.assertRaises(RewriteError):
            rewrite_instructions(steps, _plan(), generate=bad_generate)

    def test_llm_error_fails_closed(self):
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions,
        )
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}]

        def bad_generate(prompt):
            raise RuntimeError('gemini 503')

        with self.assertRaises(RewriteError):
            rewrite_instructions(steps, _plan(), generate=bad_generate)

    def test_old_ingredient_left_in_output_fails_closed(self):
        """The whole point is removing the name — a passthrough is a failure."""
        from diet_planner.services.substitution_rewrite import (
            RewriteError, rewrite_instructions,
        )
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}]

        def lazy_generate(prompt):
            return json.dumps({'steps': [{'text': 'Přidejte vanilkový extrakt.'}]})

        with self.assertRaises(RewriteError):
            rewrite_instructions(steps, _plan(), generate=lazy_generate)

    def test_preserves_tip_and_time_when_llm_omits_them(self):
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = [{'text': 'Přidejte vanilkový extrakt.', 'time_min': 3, 'tip': 'Nemíchejte moc.'}]

        def terse_generate(prompt):
            return json.dumps({'steps': [{'text': 'Přidejte vanilkové aroma.'}]})

        out = rewrite_instructions(steps, _plan(), generate=terse_generate)
        self.assertEqual(out[0]['time_min'], 3)
        self.assertEqual(out[0]['tip'], 'Nemíchejte moc.')


class StringStepTests(TestCase):
    def test_plain_string_steps_are_handled(self):
        """Older corpus rows store instructions as bare strings."""
        from diet_planner.services.substitution_rewrite import rewrite_instructions
        steps = ['Přidejte vanilkový extrakt.']

        def fake_generate(prompt):
            return json.dumps({'steps': [{'text': 'Přidejte vanilkové aroma.'}]})

        out = rewrite_instructions(steps, _plan(), generate=fake_generate)
        self.assertEqual(out[0]['text'], 'Přidejte vanilkové aroma.')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_substitution_rewrite -v 1`

Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.substitution_rewrite'`

- [ ] **Step 3: Write the rewriter**

Create `diet_planner/services/substitution_rewrite.py`:

```python
"""Rewriting the instruction steps that name a substituted ingredient.

Deliberately narrow. We are editing someone else's credited recipe, so the
LLM sees only the steps that mention the swapped ingredient, and must return
exactly that many steps back. Anything else raises and the caller discards the
whole rewrite — a half-adapted recipe is worse than an unshoppable one.
"""
from __future__ import annotations

import json
import logging
from typing import Callable, List, Optional

from django.conf import settings

from diet_planner.services.ingredient_substitution import SubstitutionPlan

logger = logging.getLogger(__name__)


class RewriteError(Exception):
    """The rewrite could not be trusted; caller must discard it."""


_PROMPT = (
    'Toto jsou kroky českého receptu, ve kterých se mění jedna surovina.\n'
    'Záměny:\n{swaps}\n\n'
    'Přepiš KAŽDÝ krok tak, aby používal novou surovinu. Zachovej styl, tón '
    'i pořadí. Neměň nic jiného — žádné nové kroky, žádné rady navíc. Pokud '
    'záměna vyžaduje jinou přípravu (např. mletí ovesných vloček místo ovesné '
    'mouky), doplň to stručně do téhož kroku.\n\n'
    'Kroky ({count}):\n{steps}\n\n'
    'Vrať POUZE JSON: {{"steps": [{{"text": "..."}}, ...]}} — přesně {count} '
    'kroků ve stejném pořadí.'
)


def _default_generate(prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=getattr(settings, 'GEMINI_API_KEY', None))
    model = genai.GenerativeModel(getattr(settings, 'GEMINI_MODEL', 'gemini-2.5-flash'))
    resp = model.generate_content(prompt)
    return getattr(resp, 'text', '') or ''


def _step_text(step) -> str:
    if isinstance(step, dict):
        return step.get('text') or ''
    return str(step or '')


def _mentions(text: str, name: str) -> bool:
    """Czech is inflected, so match on the stem rather than the exact form
    ('vanilkový extrakt' appears as 'vanilkového extraktu')."""
    haystack = text.lower()
    for word in name.lower().split():
        stem = word[:-2] if len(word) > 5 else word
        if stem and stem in haystack:
            return True
    return False


def rewrite_instructions(
    instructions, plan: SubstitutionPlan,
    *, generate: Optional[Callable[[str], str]] = None,
) -> List[dict]:
    """Instruction list with swapped ingredients renamed in the affected steps.

    Raises RewriteError if the model returns the wrong shape, errors, or leaves
    an old ingredient name in place.
    """
    from diet_planner.services.prompt_facets import _strip_code_fence

    steps = list(instructions or [])
    if not plan.changes:
        return steps

    affected = [
        i for i, step in enumerate(steps)
        if any(_mentions(_step_text(step), c.old_name) for c in plan.changes)
    ]
    if not affected:
        # The swap never surfaces in the prose — ingredient rewrite is enough.
        return steps

    swaps = '\n'.join(f'- {c.old_name} → {c.new_name}' for c in plan.changes)
    numbered = '\n'.join(f'{n + 1}. {_step_text(steps[i])}' for n, i in enumerate(affected))
    prompt = _PROMPT.format(swaps=swaps, count=len(affected), steps=numbered)

    gen = generate or _default_generate
    try:
        raw = gen(prompt)
        data = json.loads(_strip_code_fence(raw))
        new_steps = data['steps']
    except RewriteError:
        raise
    except Exception as exc:
        raise RewriteError(f'instruction rewrite failed: {exc}') from exc

    if not isinstance(new_steps, list) or len(new_steps) != len(affected):
        raise RewriteError(
            f'expected {len(affected)} steps, got '
            f'{len(new_steps) if isinstance(new_steps, list) else type(new_steps).__name__}')

    out = [dict(s) if isinstance(s, dict) else {'text': str(s)} for s in steps]
    for n, position in enumerate(affected):
        new_text = (new_steps[n] or {}).get('text', '').strip() if isinstance(
            new_steps[n], dict) else str(new_steps[n]).strip()
        if not new_text:
            raise RewriteError(f'empty step text at position {position}')
        for change in plan.changes:
            if _mentions(new_text, change.old_name) and not _mentions(
                    new_text, change.new_name):
                raise RewriteError(
                    f'step {position} still names {change.old_name!r}')
        # Keep everything the model was not asked to produce.
        out[position]['text'] = new_text

    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_substitution_rewrite -v 1`

Expected: `Ran 7 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/substitution_rewrite.py diet_planner/tests/test_substitution_rewrite.py
git commit -m "feat(availability): bounded LLM rewrite of affected instruction steps"
```

---

### Task 6: `apply_availability_substitutions`

**Files:**
- Create: `diet_planner/management/commands/apply_availability_substitutions.py`
- Test: `diet_planner/tests/test_apply_substitutions.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_apply_substitutions.py`:

```python
"""The substitution command: dry-run, judge gate, snapshot, rollup refresh."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from diet_planner.models import CuratedRecipe


def _recipe(**kw):
    defaults = dict(
        slug='vanilkovy-kolac', name_cs='Vanilkový koláč',
        meal_types=['snack'], base_servings=4,
        source_url='https://example.com/r', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        ingredients=[
            {'name': 'vanilkový extrakt', 'canonical': 'vanilla-extract',
             'quantity': 1, 'unit': 'lžička'},
            {'name': 'sůl', 'canonical': 'salt', 'quantity': 5, 'unit': 'g'},
        ],
        instructions=[{'text': 'Přidejte vanilkový extrakt.', 'time_min': 1}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class ApplySubstitutionsTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())
        call_command('load_availability_substitutions', stdout=StringIO())

    def _patched(self, judge_ok=True):
        return (
            mock.patch(
                'diet_planner.management.commands.apply_availability_substitutions'
                '.rewrite_instructions',
                return_value=[{'text': 'Přidejte vanilkové aroma.', 'time_min': 1}]),
            mock.patch(
                'diet_planner.management.commands.apply_availability_substitutions'
                '.judge_curated_recipe',
                return_value={'ran': True, 'passed': judge_ok}),
        )

    def test_dry_run_writes_nothing(self):
        r = _recipe()
        rewrite, judge = self._patched()
        out = StringIO()
        with rewrite, judge:
            call_command('apply_availability_substitutions', '--dry-run', stdout=out)
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.adaptation_note, '')
        self.assertIn('vanilkový extrakt', out.getvalue())

    def test_applies_and_snapshots(self):
        r = _recipe()
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-aroma')
        self.assertEqual(r.ingredients[0]['name'], 'vanilkové aroma')
        self.assertEqual(r.instructions[0]['text'], 'Přidejte vanilkové aroma.')
        self.assertIn('vanilkový extrakt', r.adaptation_note)
        self.assertEqual(
            r.original_ingredients[0]['canonical'], 'vanilla-extract',
            "the source author's original must be preserved")

    def test_rollup_is_recomputed(self):
        r = _recipe()
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, 'common')
        self.assertEqual(r.shopping_blockers, [])

    def test_judge_rejection_discards_the_whole_rewrite(self):
        r = _recipe()
        rewrite, judge = self._patched(judge_ok=False)
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.instructions[0]['text'], 'Přidejte vanilkový extrakt.')
        self.assertEqual(r.adaptation_note, '')

    def test_rewrite_error_discards_the_whole_rewrite(self):
        from diet_planner.services.substitution_rewrite import RewriteError
        r = _recipe()
        with mock.patch(
            'diet_planner.management.commands.apply_availability_substitutions'
            '.rewrite_instructions', side_effect=RewriteError('bad shape'),
        ):
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'vanilla-extract')
        self.assertEqual(r.adaptation_note, '')

    def test_uncovered_recipe_is_left_alone(self):
        r = _recipe(slug='tahini-dressing', ingredients=[
            {'name': 'tahini', 'canonical': 'tahini', 'quantity': 30, 'unit': 'g'}],
            instructions=[{'text': 'Rozmíchejte tahini.'}])
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.ingredients[0]['canonical'], 'tahini')

    def test_limit_bounds_the_batch(self):
        for n in range(3):
            _recipe(slug=f'kolac-{n}')
        rewrite, judge = self._patched()
        out = StringIO()
        with rewrite, judge:
            call_command('apply_availability_substitutions', '--limit=2', stdout=out)
        changed = CuratedRecipe.objects.exclude(adaptation_note='').count()
        self.assertEqual(changed, 2)

    def test_already_adapted_recipe_is_not_reprocessed(self):
        r = _recipe(adaptation_note='Upraveno pro dostupnost: x → y')
        rewrite, judge = self._patched()
        with rewrite, judge:
            call_command('apply_availability_substitutions', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.adaptation_note, 'Upraveno pro dostupnost: x → y')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_apply_substitutions -v 1`

Expected: FAIL — `CommandError: Unknown command: 'apply_availability_substitutions'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/apply_availability_substitutions.py`:

```python
"""Rewrite unshoppable recipes into Czech-shoppable ones.

All-or-nothing per recipe: the ingredient rewrite, the instruction rewrite and
the coherence judge must all succeed, or the recipe is left exactly as its
author wrote it. We are editing credited third-party recipes, so
`original_ingredients` keeps the original and `adaptation_note` discloses the
change on the recipe page.

See docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md §6
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.services.ingredient_availability import (
    availability_index,
    compute_shopping_difficulty,
)
from diet_planner.services.ingredient_substitution import (
    apply_changes_to_ingredients,
    plan_substitutions,
    substitution_table,
)
from diet_planner.services.recipe_curation import judge_curated_recipe
from diet_planner.services.substitution_rewrite import RewriteError, rewrite_instructions

_NOTE_PREFIX = 'Upraveno pro dostupnost v českých obchodech: '


class Command(BaseCommand):
    help = 'Substitute hard-to-buy ingredients in curated recipes.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--slug', default=None, help='Adapt one recipe only')
        parser.add_argument(
            '--skip-judge', action='store_true',
            help='Skip the coherence judge (for offline reruns; not for prod)')

    def handle(self, *args, **options):
        table = substitution_table()
        if not table:
            self.stdout.write(self.style.WARNING(
                'no availability substitutions loaded — '
                'run load_availability_substitutions first'))
            return

        index = availability_index()
        qs = CuratedRecipe.objects.exclude(
            shopping_difficulty=CuratedRecipe.ShoppingDifficulty.COMMON,
        ).filter(adaptation_note='').order_by('id')
        if options['slug']:
            qs = qs.filter(slug=options['slug'])

        adapted = skipped = failed = 0

        for recipe in qs.iterator():
            if options['limit'] is not None and adapted >= options['limit']:
                break

            plan = plan_substitutions(recipe, table, index=index)
            if not plan.saveable:
                skipped += 1
                if plan.uncovered:
                    self.stdout.write(
                        f'  skip {recipe.slug}: uncovered {", ".join(plan.uncovered)}')
                continue

            self.stdout.write(f'{recipe.slug}: {plan.summary()}')

            new_ingredients = apply_changes_to_ingredients(recipe.ingredients, plan)
            try:
                new_instructions = rewrite_instructions(recipe.instructions, plan)
            except RewriteError as exc:
                failed += 1
                self.stdout.write(self.style.WARNING(f'  rewrite failed: {exc}'))
                continue

            if options['dry_run']:
                for change in plan.changes:
                    self.stdout.write(
                        f'    - {change.old_name} {change.new_quantity}'
                        f' {change.new_unit} -> {change.new_name}')
                adapted += 1
                continue

            # Judge the CANDIDATE, not the stored row: build an unsaved copy.
            candidate = CuratedRecipe(
                id=recipe.id, slug=recipe.slug, name_cs=recipe.name_cs,
                description=recipe.description,
                ingredients=new_ingredients, instructions=new_instructions,
                base_servings=recipe.base_servings,
            )
            if not options['skip_judge']:
                verdict = judge_curated_recipe(candidate)
                if verdict.get('ran') and not verdict.get('passed', True):
                    failed += 1
                    self.stdout.write(self.style.WARNING(
                        '  judge rejected the rewrite — discarded'))
                    continue

            with transaction.atomic():
                if not recipe.original_ingredients:
                    recipe.original_ingredients = recipe.ingredients
                recipe.ingredients = new_ingredients
                recipe.instructions = new_instructions
                recipe.adaptation_note = (_NOTE_PREFIX + plan.summary())[:255]
                tier, blockers = compute_shopping_difficulty(recipe, index=index)
                recipe.shopping_difficulty = tier
                recipe.shopping_blockers = blockers
                recipe.save(update_fields=[
                    'ingredients', 'instructions', 'adaptation_note',
                    'original_ingredients', 'shopping_difficulty',
                    'shopping_blockers', 'updated_at',
                ])
            adapted += 1

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}adapted={adapted} skipped={skipped} failed={failed}'))
```

- [ ] **Step 4: Confirm the judge's verdict key**

The command reads `verdict.get('passed')`. Confirm that is what `judge_curated_recipe` actually returns (it builds its result from `verdict.as_stats()` at `recipe_curation.py:280`):

```bash
grep -n -A 25 "def judge_curated_recipe" diet_planner/services/recipe_curation.py
```

If the returned dict uses a different key for the pass/fail signal, use that key in the command instead — do not add a translation layer. Update the test's mock return value to match.

- [ ] **Step 5: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_apply_substitutions -v 1`

Expected: `Ran 9 tests ... OK`

- [ ] **Step 6: Commit**

```bash
git add diet_planner/management/commands/apply_availability_substitutions.py diet_planner/tests/test_apply_substitutions.py
git commit -m "feat(availability): apply substitutions with judge gate and snapshot"
```

---

### Task 7: Unpublish the residue

**Files:**
- Create: `diet_planner/management/commands/unpublish_unshoppable.py`
- Test: `diet_planner/tests/test_apply_substitutions.py`

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_apply_substitutions.py`:

```python
class UnpublishUnshoppableTests(TestCase):
    def setUp(self):
        call_command('seed_canonical_ingredients', stdout=StringIO())
        call_command('rate_ingredient_availability', stdout=StringIO())

    def test_specialty_published_becomes_draft(self):
        r = _recipe(slug='sushi-miska', ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.shopping_difficulty, 'specialty')

        out = StringIO()
        call_command('unpublish_unshoppable', stdout=out)
        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.DRAFT)
        self.assertIn('sushi-miska', out.getvalue())

    def test_findable_recipe_stays_published(self):
        """Only specialty is demoted; findable is a bigger-shop trip, not a wall."""
        r = _recipe(slug='findable-dish', ingredients=[
            {'name': 'javorový sirup', 'canonical': 'maple-syrup',
             'quantity': 30, 'unit': 'ml'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        call_command('unpublish_unshoppable', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)

    def test_nothing_is_deleted(self):
        _recipe(slug='sushi-miska', ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        call_command('unpublish_unshoppable', stdout=StringIO())
        self.assertTrue(CuratedRecipe.objects.filter(slug='sushi-miska').exists())

    def test_dry_run_writes_nothing(self):
        r = _recipe(slug='sushi-miska', ingredients=[
            {'name': 'nori', 'canonical': 'nori', 'quantity': 2, 'unit': 'ks'}])
        call_command('recompute_shopping_difficulty', stdout=StringIO())
        call_command('unpublish_unshoppable', '--dry-run', stdout=StringIO())
        r.refresh_from_db()
        self.assertEqual(r.status, CuratedRecipe.Status.PUBLISHED)
```

**Note:** if `nori` is not a canonical rated `specialty` in `ingredient_availability.yaml`, pick one that is (check with `grep -B1 "availability: specialty" diet_planner/data/ingredient_availability.yaml | head`) and use its slug and `name_cs` throughout this test class.

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_apply_substitutions.UnpublishUnshoppableTests -v 1`

Expected: FAIL — `CommandError: Unknown command: 'unpublish_unshoppable'`

- [ ] **Step 3: Write the command**

Create `diet_planner/management/commands/unpublish_unshoppable.py`:

```python
"""Demote published recipes you still cannot shop for in a Czech supermarket.

Draft, never delete: shopping_blockers records exactly why each one went, so a
future substitution table or a wider bar can bring it straight back.
"""
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = 'Move specialty-difficulty published recipes to draft.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')

    def handle(self, *args, **options):
        qs = CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED,
            shopping_difficulty=CuratedRecipe.ShoppingDifficulty.SPECIALTY,
        ).order_by('slug')

        demoted = 0
        for recipe in qs.iterator():
            demoted += 1
            self.stdout.write(
                f'  {recipe.slug}: {", ".join(recipe.shopping_blockers or [])}')
            if not options['dry_run']:
                recipe.status = CuratedRecipe.Status.DRAFT
                recipe.save(update_fields=['status', 'updated_at'])

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(f'{prefix}demoted={demoted}'))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_apply_substitutions -v 1`

Expected: `Ran 13 tests ... OK`

- [ ] **Step 5: Commit**

```bash
git add diet_planner/management/commands/unpublish_unshoppable.py diet_planner/tests/test_apply_substitutions.py
git commit -m "feat(availability): demote still-unshoppable recipes to draft"
```

---

### Task 8: Ranking

**Files:**
- Modify: `llm_diet_planner_project/settings.py:389`
- Modify: `diet_planner/services/recipe_retrieval.py:425` and `~516`
- Test: `diet_planner/tests/test_availability_ranking.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_availability_ranking.py`:

```python
"""Shopping difficulty in retrieval: a hard gate plus a small soft penalty."""
from django.test import TestCase, override_settings

from diet_planner.models import CuratedRecipe
from diet_planner.services.recipe_retrieval import eligible_recipes_for_slot, score_recipe


def _recipe(slug, difficulty='common', blockers=None, **kw):
    defaults = dict(
        slug=slug, name_cs=slug, meal_types=['dinner'], base_servings=2,
        source_url=f'https://example.com/{slug}', source_name='Example',
        status=CuratedRecipe.Status.PUBLISHED,
        shopping_difficulty=difficulty, shopping_blockers=blockers or [],
        ingredients=[{'name': 'sůl', 'canonical': 'salt', 'quantity': 5,
                      'unit': 'g', 'catalog_id': 1}],
        instructions=[{'text': 'Uvařte.'}],
    )
    defaults.update(kw)
    return CuratedRecipe.objects.create(**defaults)


class EligibilityTests(TestCase):
    def test_specialty_is_excluded(self):
        common = _recipe('easy-dish')
        _recipe('hard-dish', difficulty='specialty', blockers=['tahini'])
        out = eligible_recipes_for_slot(
            'dinner', set(), pool=list(CuratedRecipe.objects.all()),
            enforce_mapping=False)
        self.assertEqual([r.slug for r in out], [common.slug])

    def test_findable_stays_eligible(self):
        _recipe('findable-dish', difficulty='findable', blockers=['maple-syrup'])
        out = eligible_recipes_for_slot(
            'dinner', set(), pool=list(CuratedRecipe.objects.all()),
            enforce_mapping=False)
        self.assertEqual(len(out), 1)


class PenaltyTests(TestCase):
    def _score(self, recipe):
        return score_recipe(recipe, used_recipe_ids=set(), used_cuisines=[])

    @override_settings(AVAILABILITY_RANKING_ENABLED=True)
    def test_blocker_costs_one_point_each(self):
        common = _recipe('a')
        findable = _recipe('b', difficulty='findable', blockers=['maple-syrup'])
        self.assertAlmostEqual(self._score(common) - self._score(findable), 1.0)

    @override_settings(AVAILABILITY_RANKING_ENABLED=True)
    def test_penalty_is_capped(self):
        common = _recipe('a')
        many = _recipe('b', difficulty='findable',
                       blockers=['x', 'y', 'z', 'w', 'v'])
        self.assertAlmostEqual(self._score(common) - self._score(many), 3.0)

    @override_settings(AVAILABILITY_RANKING_ENABLED=False)
    def test_flag_off_means_no_penalty(self):
        common = _recipe('a')
        findable = _recipe('b', difficulty='findable', blockers=['maple-syrup'])
        self.assertAlmostEqual(self._score(common), self._score(findable))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_availability_ranking -v 1`

Expected: FAIL — `test_specialty_is_excluded` returns both recipes.

- [ ] **Step 3: Add the settings flag**

In `llm_diet_planner_project/settings.py`, directly after the `AVAILABILITY_GATE_ENABLED` line (389):

```python
# Rank easy-to-shop recipes above hard-to-shop ones. Separate from the intake
# gate so the corpus repair can land before user-visible ranking shifts.
AVAILABILITY_RANKING_ENABLED = config('AVAILABILITY_RANKING_ENABLED', default=False, cast=bool)
```

- [ ] **Step 4: Add the hard gate**

In `diet_planner/services/recipe_retrieval.py`, in `eligible_recipes_for_slot`, after the `enforce_mapping` check (line 425-426):

```python
        if enforce_mapping and not r.is_catalog_mapped():
            continue
        # Unshoppable in an ordinary Czech supermarket. Unconditional: after
        # unpublish_unshoppable this is belt-and-braces for published rows, but
        # it still covers the enforce_mapping=False chat-draft path.
        if r.shopping_difficulty == CuratedRecipe.ShoppingDifficulty.SPECIALTY:
            continue
```

- [ ] **Step 5: Add the penalty**

In `diet_planner/services/recipe_retrieval.py`, add next to the other weight constants (after line 439):

```python
# Shopping friction. At 1.0 per blocker a single blocker is exactly enough to
# push a findable recipe out of the _SAMPLING_WINDOW against an equally-scoring
# common one — it loses ties, which is the intent. Against _WANTED_HIT_WEIGHT
# (20.0) it is negligible, so it can never override what the user asked for.
_SHOPPING_BLOCKER_PENALTY = 1.0
_SHOPPING_PENALTY_CAP = 3.0
```

Then in `score_recipe`, after the difficulty bonus (line 515-516):

```python
    # Difficulty: prefer easy (novice-friendly is the whole point).
    if recipe.difficulty == CuratedRecipe.Difficulty.EASY:
        score += 2.0

    # Shopping friction: prefer a dish the user can buy in one stop.
    if (getattr(settings, 'AVAILABILITY_RANKING_ENABLED', False)
            and recipe.shopping_difficulty != CuratedRecipe.ShoppingDifficulty.COMMON):
        score -= min(
            len(recipe.shopping_blockers or []) * _SHOPPING_BLOCKER_PENALTY,
            _SHOPPING_PENALTY_CAP)
```

Confirm `settings` is imported in this module (`from django.conf import settings`); add the import if it is not.

- [ ] **Step 6: Run test to verify it passes**

Run: `docker-compose run --rm web python manage.py test diet_planner.tests.test_availability_ranking -v 1`

Expected: `Ran 5 tests ... OK`

- [ ] **Step 7: Run the whole backend suite for regressions**

Run: `docker-compose run --rm web python manage.py test diet_planner billing analytics -v 1`

Expected: `OK`. The retrieval gate is the riskiest change in this plan — any grounding test that builds a fixture recipe without setting `shopping_difficulty` will now get the model default. If failures appear there, fix the fixtures, not the gate.

- [ ] **Step 8: Commit**

```bash
git add llm_diet_planner_project/settings.py diet_planner/services/recipe_retrieval.py diet_planner/tests/test_availability_ranking.py
git commit -m "feat(grounding): exclude specialty recipes, penalise shopping blockers"
```

---

### Task 9: Run the repair

Code is done; this task changes data. Local first, then prod.

- [ ] **Step 1: Load everything locally**

```bash
docker-compose run --rm web python manage.py migrate
docker-compose run --rm web python manage.py seed_canonical_ingredients
docker-compose run --rm web python manage.py rate_ingredient_availability
docker-compose run --rm web python manage.py load_availability_substitutions
docker-compose run --rm web python manage.py recompute_shopping_difficulty
```

Expected: `loaded=10 created=10 updated=0`, then `recipes=<N> changed=<N>`

- [ ] **Step 2: Dry-run the substitutions and READ THE DIFF**

```bash
docker-compose run --rm web python manage.py apply_availability_substitutions --dry-run > /tmp/subs-dryrun.txt
tail -40 /tmp/subs-dryrun.txt
```

Expected: a per-recipe list of swaps and a closing `[dry-run] adapted=N skipped=M failed=0`.

**This is a review checkpoint, not a formality.** Read the swap list. If a swap looks wrong for a specific dish (sesame oil in an Asian dressing is the one to watch), remove that pair from `ingredient_substitutions_cz.yaml`, re-run the loader, and dry-run again.

- [ ] **Step 3: Apply in a reviewable first batch**

```bash
docker-compose run --rm web python manage.py apply_availability_substitutions --limit=20
```

Expected: `adapted=20 skipped=M failed=K`. Spot-check three adapted recipes:

```bash
docker-compose run --rm web python manage.py shell -c "
from diet_planner.models import CuratedRecipe
for r in CuratedRecipe.objects.exclude(adaptation_note='')[:3]:
    print(r.slug, '|', r.adaptation_note)
    print('  ', [i.get('name') for i in r.ingredients])
    print('  ', [s.get('text') for s in r.instructions][:2])
"
```

Confirm the ingredient names, the instruction text and the note all agree. Then run the rest:

```bash
docker-compose run --rm web python manage.py apply_availability_substitutions
```

- [ ] **Step 4: Re-check the long-tail ratings BEFORE demoting anything**

Unpublish acts on `specialty` ratings, and the Phase 1 review knowingly left ~57 low-impact rows as Claude's guess rather than the owner's judgement. Known-suspect calls flagged at the time: `hřebíček`/cloves (ordinary in any CZ supermarket), `nálev z oliv` (a mapping artifact, not a purchasable item at all), and asparagus / fennel / parsnip / cherries / dates (rated harshly). Demoting a recipe on a wrong rating is a silent, invisible loss.

```bash
docker-compose run --rm web python manage.py shell -c "
from diet_planner.models import CuratedRecipe
from collections import Counter
c = Counter()
for r in CuratedRecipe.objects.filter(status='published', shopping_difficulty='specialty'):
    for b in (r.shopping_blockers or []):
        c[b] += 1
for slug, n in c.most_common():
    print(f'{n:4d}  {slug}')
"
```

Read every slug in that list — it is the complete set of reasons recipes are about to be demoted. For each one that is actually an ordinary supermarket item, correct it in `diet_planner/data/ingredient_availability.yaml` (set `confidence: owner` with a note), then re-run:

```bash
docker-compose run --rm web python manage.py rate_ingredient_availability
docker-compose run --rm web python manage.py recompute_shopping_difficulty
```

Repeat Step 2-3 if the corrections newly make some recipes saveable.

- [ ] **Step 5: Demote the residue**

```bash
docker-compose run --rm web python manage.py unpublish_unshoppable --dry-run
docker-compose run --rm web python manage.py unpublish_unshoppable
```

- [ ] **Step 6: Re-measure**

```bash
docker-compose run --rm web python manage.py report_shopping_difficulty > docs/shopping-difficulty-report-phase2.txt
cat docs/shopping-difficulty-report-phase2.txt
```

Expected: `common` well above the 294 baseline, `specialty` at 0 among published rows, and — the number that decides whether this shipped or backfired — **no `<-- THIN` marker that was not already thin in the 2026-08-11 baseline**.

- [ ] **Step 7: STOP — pool check before prod**

Compare the two reports side by side:

```bash
diff <(sed -n '/pool by meal_type/,/blocking ingredients/p' docs/shopping-difficulty-report-2026-08-11.txt) \
     <(sed -n '/pool by meal_type/,/blocking ingredients/p' docs/shopping-difficulty-report-phase2.txt)
```

If any facet pool **shrank** (unpublish outran substitution for that diet), do not roll to prod. Report to the owner instead: the fix is more substitution pairs or new curation, not a smaller corpus. Phase 1's report showed breakfast/vegan and snack/vegan as the fragile ones — those are where this will show up first.

- [ ] **Step 8: Commit the report**

```bash
git add docs/shopping-difficulty-report-phase2.txt
git commit -m "docs: corpus obtainability after the substitution repair"
```

- [ ] **Step 9: PR, CI, merge**

```bash
git push -u origin feat/ingredient-obtainability-phase-2
gh pr create --base develop --title "feat: ingredient obtainability phase 2 — substitute, unpublish, rank" --body "..."
gh run watch <run-id> --exit-status
gh pr merge <pr> --squash
```

CI runs the backend suite and the frontend typecheck on every PR into `develop` (`.github/workflows/tests.yml`). Wait for green before merging.

- [ ] **Step 10: Prod rollout**

Prod deploys from the `prod` branch, not `develop` (`[[recipe-coherence-judge]]`). Commands run through the DO console harness at `/tmp/do_exec.py` (`[[prod-console-exec-harness]]`).

```bash
git checkout prod && git merge --ff-only develop && git push origin prod
# wait for the DO deployment to reach ACTIVE, then:
cd /tmp && python3 do_exec.py "python manage.py seed_canonical_ingredients"
cd /tmp && python3 do_exec.py "python manage.py rate_ingredient_availability"
cd /tmp && python3 do_exec.py "python manage.py load_availability_substitutions"
cd /tmp && python3 do_exec.py "python manage.py apply_availability_substitutions --dry-run"
```

Read the prod dry-run before applying — prod's corpus is not identical to local. Then apply, demote, and re-report on prod. Flip `AVAILABILITY_RANKING_ENABLED=true` in the DO app spec **last**, once the corpus repair is verified.

- [ ] **Step 11: QA**

Run `/qa-prod`. Recipe pages must show the adaptation note where one exists, and no plan may contain a demoted recipe.

---

## Self-Review

**Spec coverage:**

| Spec deliverable (§) | Task | Status |
|---|---|---|
| `IngredientSubstitute.purpose` / `substitute_unit` (§1) | 1 | covered |
| `vanilla-aroma` needs its own canonical (§6 note) | 2 | covered — spec calls this out explicitly |
| `ingredient_substitutions_cz.yaml` seed (§6) | 3 | covered |
| `load_availability_substitutions` (§6) | 3 | covered, idempotent + fails loudly |
| Saveable vs not-saveable split (§6 table) | 3 | covered — only saveable pairs seeded |
| Rewrite ingredient row, drop stale `catalog_id` (§6.1) | 4 | covered, tested |
| LLM rewrites only affected steps (§6.2) | 5 | covered, tested both directions |
| Judge gate, discard whole rewrite (§6.3) | 6 | covered, tested |
| Snapshot + `adaptation_note` + recompute (§6.4) | 6 | covered, tested |
| `--dry-run` / `--limit` (§6) | 6 | covered, tested |
| Unpublish residue, never delete (§7) | 7 | covered, tested |
| Exclude specialty in `eligible_recipes_for_slot` (§8) | 8 | covered |
| Blocker penalty + cap behind flag (§8) | 8 | covered, calibration tested |
| Attribution preserved (§6) | 6 | covered — `original_ingredients` + note |

**Beyond the spec, added deliberately:** `_TAG_INCOMPATIBLE` in Task 4. The spec's own table proposes `tamari → sójová omáčka`, which silently breaks a `gluten_free` recipe's promise — and `[[dietary-preferences-enforcement]]` made those tags hard-enforced everywhere. Substituting into a violation would be a worse bug than the one this plan fixes.

**Placeholder scan:** no TBD/TODO/"similar to Task N". Every code step carries complete code; every command step carries expected output. Two steps are deliberate verification-before-coding (Task 3 Step 3's slug check, Task 6 Step 4's judge-key check) rather than placeholders — both name the exact command and what to do with each outcome.

**Type consistency:** `substitution_table() -> Dict[str, SubstitutionRule]` is defined in Task 4 and consumed in Task 6. `plan_substitutions(recipe, table, index=None) -> SubstitutionPlan` and `apply_changes_to_ingredients(ingredients, plan) -> List[dict]` match their call sites. `rewrite_instructions(instructions, plan, *, generate=None) -> List[dict]` matches Task 6's mock signature. `SubstitutionPlan.summary()` is defined in Task 4 and called in Task 6. `IngredientChange` field names (`old_name`, `new_name`, `new_canonical`, `new_quantity`, `new_unit`, `index`) are used identically in Tasks 4, 5 and 6. `CuratedRecipe.ShoppingDifficulty.COMMON/SPECIALTY` come from Phase 1 Task 2.

**Known risk:** `_mentions()` in Task 5 stems Czech words crudely (drops the last two characters of any word longer than five). It over-matches — "vanilkový extrakt" will also match a step mentioning "vanilkový cukr" — which sends an extra step to the LLM. That is the safe direction: an unnecessary rewrite is caught by the judge, whereas a missed step would leave an unbuyable ingredient named in the prose. Tested via `test_only_affected_steps_are_sent_to_the_llm`.
