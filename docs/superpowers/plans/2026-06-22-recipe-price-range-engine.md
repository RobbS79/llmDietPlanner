# Recipe Price-Range Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pure, fully-tested service that turns a recipe's ingredients + servings into an honest from–to price range (total + per-portion) from the static price book.

**Architecture:** Extract the per-line consumed-cost math out of `EstimatePricer` into a shared pure helper (`pricing_core.consumed_line_cost`), so unit conversion lives in one place. Build `recipe_pricing.price_recipe` on top of that helper: sum consumed costs for the low end, multiply by a measured overhead factor for the high end, divide by servings for per-portion, and report coverage. No UI, no DB writes, no LLM.

**Tech Stack:** Python 3.12, Django 5.2 (`manage.py test`), the existing `diet_planner/services` modules (`units`, `estimate_pricer`, `piece_weights`, `canonical_lookup`).

Spec: `docs/superpowers/specs/2026-06-22-recipe-price-range-design.md`

---

### Task 1: Extract shared `consumed_line_cost` helper

Behavior-preserving refactor: move the per-line cost math from `EstimatePricer._consumed_cost` into a pure module function both pricers can call.

**Files:**
- Create: `diet_planner/services/pricing_core.py`
- Create: `diet_planner/tests/test_pricing_core.py`
- Modify: `diet_planner/services/estimate_pricer.py` (lines 39-41 constant, 150-185 method, import)

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_pricing_core.py`:

```python
from django.test import SimpleTestCase

from diet_planner.services.pricing_core import consumed_line_cost


class ConsumedLineCostTest(SimpleTestCase):
    G_ENTRY = {'unit': 'g', 'price_per_unit': 0.30, 'pack': 500.0}
    KS_ENTRY = {'unit': 'ks', 'price_per_unit': 2.0, 'pack': 10.0}

    def test_same_dimension_is_prorated(self):
        # 400 g * 0.30 = 120.0 (charge only what's consumed, not a pack)
        self.assertEqual(consumed_line_cost(self.G_ENTRY, 400, 'g'), 120.0)

    def test_zero_or_missing_quantity_unpriceable(self):
        self.assertIsNone(consumed_line_cost(self.G_ENTRY, 0, 'g'))
        self.assertIsNone(consumed_line_cost(self.G_ENTRY, None, 'g'))

    def test_dimension_mismatch_no_grams_falls_back_to_one_pack(self):
        # recipe in grams, book per-piece, no bridge -> one typical pack: 10 * 2.0
        self.assertEqual(consumed_line_cost(self.KS_ENTRY, 100, 'g'), 20.0)

    def test_piece_weight_bridge(self):
        # 220 g / 110 g-per-piece = 2 pieces * 2.0 = 4.0
        self.assertEqual(consumed_line_cost(self.KS_ENTRY, 220, 'g', grams=110), 4.0)

    def test_no_price_unpriceable(self):
        self.assertIsNone(consumed_line_cost({'unit': 'g', 'price_per_unit': 0, 'pack': 5}, 10, 'g'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 manage.py test diet_planner.tests.test_pricing_core -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.pricing_core'`

- [ ] **Step 3: Create the helper**

Create `diet_planner/services/pricing_core.py`:

```python
"""Shared per-line cost math for the pricing paths.

Single source of truth for converting one recipe/shopping line ("qty unit")
into a cost against a price-book entry, including the piece<->weight bridge.
Both the whole-plan EstimatePricer and the per-recipe range engine call this,
so unit conversion never forks into a second path — the fork is what produced
the 238k Kč chicken (see [[prod-pricing-fabrication-surface]]).
"""
import logging
from typing import Optional

from diet_planner.services.units import to_base

logger = logging.getLogger(__name__)

# With correct unit conversion, no real line needs more than this many packs.
MAX_PACKAGES = 50


def consumed_line_cost(entry, qty, unit, grams=None) -> Optional[float]:
    """Pro-rated cost of `qty unit` against book `entry`.

    Charges only the consumed amount (10 ml of a 1 L bottle ~ the price of
    10 ml). Bridges count<->mass via `grams` (typical piece weight) when the
    line and the book disagree on dimension. Falls back to one typical pack
    when the quantity can't be converted at all. Returns None when not
    priceable (no/zero price, missing or non-positive quantity).
    """
    if qty is None or qty <= 0:
        return None
    pack = float(entry.get('pack') or 0)
    ppu = float(entry.get('price_per_unit') or 0)
    if ppu <= 0:
        return None
    need_base, need_dim = to_base(qty, unit)
    _, book_dim = to_base(1.0, entry.get('unit', ''))
    if need_dim is not None and book_dim == need_dim:
        cost = need_base * ppu
    elif (grams and need_dim is not None and book_dim is not None
          and {need_dim, book_dim} == {'count', 'mass'}):
        # Piece<->weight bridge: recipe and book disagree on dimension.
        if book_dim == 'count':       # book per-piece, recipe in grams
            cost = (need_base / grams) * ppu
        else:                          # book per-gram, recipe in pieces
            cost = (need_base * grams) * ppu
    else:
        # Can't convert and no piece weight to bridge -> one typical pack.
        return pack * ppu if pack > 0 else None
    # Guard against absurd quantities (bad data): never charge more than a
    # sane number of packs for a single line.
    if pack > 0:
        cap = MAX_PACKAGES * pack * ppu
        if cost > cap:
            logger.warning("consumed_line_cost: capping cost for unit %s "
                           "(qty %s) at %s packs", unit, qty, MAX_PACKAGES)
            cost = cap
    return cost
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 manage.py test diet_planner.tests.test_pricing_core -v 2`
Expected: PASS (5 tests)

- [ ] **Step 5: Refactor `EstimatePricer` to delegate**

In `diet_planner/services/estimate_pricer.py`:

Add to the imports block (near line 23-29):

```python
from diet_planner.services.pricing_core import consumed_line_cost
```

Delete the now-shared constant (lines 39-41):

```python
# Same defensive ceiling as the catalog resolver: with correct unit conversion
# no real recipe needs this many packs of one product.
MAX_PACKAGES = 50
```

Replace the entire `_consumed_cost` method (lines 150-185) with a thin wrapper:

```python
    def _consumed_cost(self, entry, qty, unit, grams=None) -> Optional[float]:
        """Pro-rated cost for one line — see pricing_core.consumed_line_cost."""
        return consumed_line_cost(entry, qty, unit, grams)
```

- [ ] **Step 6: Run the full estimate-pricer suite (refactor guard)**

Run: `python3 manage.py test diet_planner.tests.test_pricing_core diet_planner.tests.test_estimate_pricer -v 2`
Expected: PASS — all existing `test_estimate_pricer` cases still green (behavior unchanged), plus the 5 new helper tests.

- [ ] **Step 7: Commit**

```bash
git add diet_planner/services/pricing_core.py diet_planner/tests/test_pricing_core.py diet_planner/services/estimate_pricer.py
git commit -m "refactor(pricing): extract consumed_line_cost into shared pricing_core

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `price_recipe` — low/high totals + per-portion

**Files:**
- Create: `diet_planner/services/recipe_pricing.py`
- Create: `diet_planner/tests/test_recipe_pricing.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_recipe_pricing.py`:

```python
from django.test import SimpleTestCase

from diet_planner.services.recipe_pricing import price_recipe, PACK_OVERHEAD

# Injected fake book — tests never touch the real book file or the DB.
BOOK = {
    'chicken': {'unit': 'g', 'price_per_unit': 0.30, 'pack': 500.0},
    'rice': {'unit': 'g', 'price_per_unit': 0.05, 'pack': 1000.0},
}


def ing(canonical, qty, unit, **kw):
    # `name` mirrors `canonical` so the canonical-first path is exercised
    # without hitting resolve_canonical (which needs the DB).
    return {'name': canonical, 'canonical': canonical,
            'quantity': qty, 'unit': unit, **kw}


class PriceRecipeTotalsTest(SimpleTestCase):
    def test_low_is_sum_of_consumed_costs(self):
        # chicken 400 g * 0.30 = 120 ; rice 200 g * 0.05 = 10 ; low = 130
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 4, book=BOOK)
        self.assertEqual(r.low, 130.0)

    def test_high_is_low_times_overhead(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 4, book=BOOK)
        self.assertEqual(r.high, 130.0 * PACK_OVERHEAD)  # 162.5

    def test_per_portion_divides_by_servings(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 4, book=BOOK)
        self.assertEqual(r.per_portion_low, 130.0 / 4)
        self.assertEqual(r.per_portion_high, (130.0 * PACK_OVERHEAD) / 4)

    def test_missing_servings_yields_no_per_portion(self):
        r = price_recipe([ing('chicken', 400, 'g')], None, book=BOOK)
        self.assertIsNone(r.per_portion_low)
        self.assertIsNone(r.per_portion_high)
        self.assertEqual(r.low, 120.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 manage.py test diet_planner.tests.test_recipe_pricing -v 2`
Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.recipe_pricing'`

- [ ] **Step 3: Create the engine**

Create `diet_planner/services/recipe_pricing.py`:

```python
"""Per-recipe from-to price range from the static price book.

Low end = sum of consumed ingredient costs (the food actually in the dish).
High end = low * PACK_OVERHEAD, the measured consumed->till overhead. The range
is pantry-agnostic (counts staples): a recipe viewer wants "what this dish
costs", not "assuming you own oil". See
docs/superpowers/specs/2026-06-22-recipe-price-range-design.md.
"""
from dataclasses import dataclass
from typing import Optional

from diet_planner.services.canonical_lookup import resolve_canonical
from diet_planner.services.estimate_pricer import _FX_FROM_CZK, _load_book
from diet_planner.services.piece_weights import load_piece_weights
from diet_planner.services.pricing_core import consumed_line_cost

# Measured consumed->till overhead (see spec eval). Tune from real-spend feedback.
PACK_OVERHEAD = 1.25
# Below this priced-ingredient fraction the range is too thin to show confidently.
COVERAGE_MIN = 0.6


@dataclass(frozen=True)
class RecipeRange:
    low: float
    high: float
    per_portion_low: Optional[float]
    per_portion_high: Optional[float]
    currency: str
    priced_count: int
    total_count: int
    confident: bool


def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fx(currency: str, book_currency: str) -> float:
    if currency == book_currency:
        return 1.0
    return _FX_FROM_CZK.get(currency, 1.0)


def price_recipe(ingredients, servings, *, currency='CZK', book=None) -> Optional[RecipeRange]:
    """Return a RecipeRange for `ingredients`, or None if nothing prices.

    `ingredients`: [{name, quantity, unit, canonical?, optional?}].
    `book`: optional injected price map (defaults to the loaded book) — for tests.
    """
    if not ingredients:
        return None
    data = _load_book()
    prices = book if book is not None else data['prices']
    book_currency = data.get('currency', 'CZK')
    weights = load_piece_weights()

    low = 0.0
    priced = total = 0
    for ing in ingredients:
        if ing.get('optional'):
            continue
        total += 1
        slug = ing.get('canonical')
        if not slug:
            name = (ing.get('name') or '').strip()
            c = resolve_canonical(name) if name else None
            slug = c.slug if c else None
        entry = prices.get(slug) if slug else None
        if not entry:
            continue
        cost = consumed_line_cost(entry, _num(ing.get('quantity')),
                                  ing.get('unit', ''), weights.get(slug))
        if cost is None:
            continue
        low += cost
        priced += 1

    if priced == 0:
        return None
    low *= _fx(currency, book_currency)
    high = low * PACK_OVERHEAD
    per_portion_low = per_portion_high = None
    if isinstance(servings, int) and servings > 0:
        per_portion_low = low / servings
        per_portion_high = high / servings
    confident = total > 0 and (priced / total) >= COVERAGE_MIN
    return RecipeRange(low, high, per_portion_low, per_portion_high,
                       currency, priced, total, confident)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 manage.py test diet_planner.tests.test_recipe_pricing -v 2`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/recipe_pricing.py diet_planner/tests/test_recipe_pricing.py
git commit -m "feat(pricing): per-recipe from-to range engine (totals + per-portion)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Coverage, confidence, optional ingredients

**Files:**
- Modify: `diet_planner/tests/test_recipe_pricing.py` (append a test class)

(The engine already implements these — this task pins the behavior with tests.)

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_recipe_pricing.py`:

```python
class PriceRecipeCoverageTest(SimpleTestCase):
    def test_unknown_ingredient_counts_toward_total_not_priced(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('mystery', 100, 'g')], 2, book=BOOK)
        self.assertEqual(r.priced_count, 1)
        self.assertEqual(r.total_count, 2)
        self.assertEqual(r.low, 120.0)

    def test_low_coverage_marks_not_confident(self):
        # 1 of 2 priced = 0.5 < COVERAGE_MIN (0.6)
        r = price_recipe([ing('chicken', 400, 'g'), ing('mystery', 100, 'g')], 2, book=BOOK)
        self.assertFalse(r.confident)

    def test_full_coverage_is_confident(self):
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')], 2, book=BOOK)
        self.assertTrue(r.confident)

    def test_optional_ingredient_excluded_from_totals_and_counts(self):
        r = price_recipe(
            [ing('chicken', 400, 'g'), ing('rice', 200, 'g', optional=True)], 2, book=BOOK)
        self.assertEqual(r.low, 120.0)
        self.assertEqual(r.total_count, 1)
        self.assertEqual(r.priced_count, 1)

    def test_nothing_prices_returns_none(self):
        self.assertIsNone(price_recipe([ing('mystery', 100, 'g')], 2, book=BOOK))
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python3 manage.py test diet_planner.tests.test_recipe_pricing.PriceRecipeCoverageTest -v 2`
Expected: PASS (5 tests) — the engine from Task 2 already implements this behavior.

- [ ] **Step 3: Commit**

```bash
git add diet_planner/tests/test_recipe_pricing.py
git commit -m "test(pricing): pin recipe-range coverage/confidence/optional behavior

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: FX and edge cases

**Files:**
- Modify: `diet_planner/tests/test_recipe_pricing.py` (append a test class)

- [ ] **Step 1: Write the failing test**

Append to `diet_planner/tests/test_recipe_pricing.py`:

```python
class PriceRecipeEdgeTest(SimpleTestCase):
    def test_eur_currency_scales_the_czk_book(self):
        # low 130 CZK / 25 = 5.2 EUR
        r = price_recipe([ing('chicken', 400, 'g'), ing('rice', 200, 'g')],
                         4, currency='EUR', book=BOOK)
        self.assertEqual(r.currency, 'EUR')
        self.assertAlmostEqual(r.low, 5.2, places=2)

    def test_empty_ingredients_returns_none(self):
        self.assertIsNone(price_recipe([], 4, book=BOOK))

    def test_zero_quantity_line_is_unpriced(self):
        r = price_recipe([ing('chicken', 0, 'g'), ing('rice', 200, 'g')], 2, book=BOOK)
        self.assertEqual(r.priced_count, 1)
        self.assertEqual(r.low, 10.0)

    def test_zero_servings_yields_no_per_portion(self):
        r = price_recipe([ing('chicken', 400, 'g')], 0, book=BOOK)
        self.assertIsNone(r.per_portion_low)
        self.assertEqual(r.low, 120.0)
```

- [ ] **Step 2: Run test to verify it passes**

Run: `python3 manage.py test diet_planner.tests.test_recipe_pricing.PriceRecipeEdgeTest -v 2`
Expected: PASS (4 tests).

- [ ] **Step 3: Run the whole pricing suite**

Run: `python3 manage.py test diet_planner.tests.test_pricing_core diet_planner.tests.test_recipe_pricing diet_planner.tests.test_estimate_pricer -v 2`
Expected: PASS — all green (helper + recipe engine + unchanged plan estimator).

- [ ] **Step 4: Commit**

```bash
git add diet_planner/tests/test_recipe_pricing.py
git commit -m "test(pricing): recipe-range FX scaling and edge cases

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Interface `RecipeRange` + `price_recipe(...)` → Task 2 (matches spec fields exactly).
- Model B calc (low = Σ consumed, high = low × overhead) → Task 2.
- Shared `consumed_line_cost` DRY refactor → Task 1.
- `PACK_OVERHEAD = 1.25`, `COVERAGE_MIN = 0.6` constants → Task 2.
- Pantry-agnostic (counts staples) → no exclusion logic in engine; verified implicitly (chicken/rice priced regardless).
- Optional excluded → Task 3.
- Coverage/confidence → Task 3.
- FX reuse → Task 4.
- Edge cases (empty→None, zero qty, zero/missing servings) → Tasks 2 & 4.
- Piece↔weight bridge via shared helper → Task 1 (`test_piece_weight_bridge`).
- Refactor guard (estimate_pricer unchanged) → Task 1 Step 6.

**Placeholder scan:** none — every step has concrete code/commands.

**Type consistency:** `price_recipe`, `RecipeRange`, fields (`low`, `high`, `per_portion_low`, `per_portion_high`, `currency`, `priced_count`, `total_count`, `confident`), `consumed_line_cost`, `PACK_OVERHEAD`, `COVERAGE_MIN` used identically across spec, engine, and tests. Test helper `ing(...)` consistent across all three test classes.

**Out of scope (later sub-projects):** serializer/API exposure, React rendering, per-recipe shopping lists, plan roll-up, retiring the whole-plan estimate.
