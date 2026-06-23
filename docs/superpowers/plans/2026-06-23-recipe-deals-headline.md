# Recipe Deals Headline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fabricated absolute price-range display with a per-recipe headline of currently-ACTIVE leaflet discounts on the recipe's ingredients.

**Architecture:** A read-only backend service (`recipe_deals`) loads all active `LEAFLET_DISCOUNT` PriceRecords once, indexes them by canonical slug, and matches a recipe's ingredients against that index. A new `deals` serializer field exposes it. The frontend stops rendering the absolute price and renders a deals headline + list instead. The pricing engine stays in the codebase, dormant, for a later savings phase.

**Tech Stack:** Django 5 (services + DRF serializers + Django TestCase), React 18 + TypeScript (Vite). Backend is TDD; frontend has no unit-test harness, so frontend tasks verify via `tsc --noEmit`.

**Spec:** `docs/superpowers/specs/2026-06-23-recipe-deals-headline-design.md`

---

## File Structure

- Create `diet_planner/services/recipe_deals.py` — active-deal matching service (one responsibility: recipe ingredients → active deals).
- Create `diet_planner/tests/test_recipe_deals.py` — service tests.
- Create `diet_planner/tests/test_recipe_serializer_deals.py` — serializer field test.
- Modify `diet_planner/tests/factories.py` — add `make_store` + extend `make_price` with `valid_from_offset_days` and `source_url`.
- Modify `diet_planner/serializers.py` — add `deals` SerializerMethodField to `RecipeSerializer` (keep `price_range` dormant).
- Modify `frontend/src/lib/pricing.ts` — gate `getRecipeRange` to null (Phase 1a); add `RecipeDeal`/`RecipeDeals` types + `getRecipeDeals` (Phase 1b).
- Modify `frontend/src/pages/PublicRecipePage.tsx`, `RecipePage.tsx`, `RecipeIndexPage.tsx` — remove price block, render deals headline.

---

## Task 1: Hide the fabricated absolute price (Phase 1a — ship to stop the bleeding)

**Files:**
- Modify: `frontend/src/lib/pricing.ts` (the `getRecipeRange` function)

- [ ] **Step 1: Gate `getRecipeRange` to always return null**

Replace the body of `getRecipeRange` in `frontend/src/lib/pricing.ts`:

```typescript
// Pull a confident price range off a recipe object, else null.
// PIVOT 2026-06-23: absolute price display is disabled — the estimate
// fabricated whole-pack costs for unconvertible units (see deals-headline
// spec). The backend engine stays; we just stop surfacing it. Returns null so
// every price block stops rendering. Replaced by getRecipeDeals (Task 5).
export const getRecipeRange = (_recipe: any): RecipePriceRange | null => {
  return null;
};
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0 (no type errors). The three pages call `getRecipeRange(recipe)` and short-circuit on null, so their price blocks now never render.

- [ ] **Step 3: Confirm no price block can render**

Run: `cd frontend && grep -n "getRecipeRange" src/pages/*.tsx`
Expected: each usage is inside a `getRecipeRange(recipe) && (…)` guard, which is now always falsy. No price shown anywhere.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/pricing.ts
git commit -m "fix(pricing): stop displaying fabricated absolute recipe price

The price-range estimate charged a whole pack for unconvertible units
(e.g. spoons), producing absurd totals (784 CZK soup). Gate getRecipeRange
to null so no fabricated price renders; engine kept for later savings phase.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Extend test factories (support for active/expired/planned deals + source_url)

**Files:**
- Modify: `diet_planner/tests/factories.py`
- Test: none (factory change; exercised by Task 3)

- [ ] **Step 1: Add `make_store` and extend `make_price`**

In `diet_planner/tests/factories.py`, add `GroceryStore` is already imported. Add this helper after `make_canonical`:

```python
def make_store(code: str, **kwargs) -> GroceryStore:
    return GroceryStore.objects.get_or_create(
        code=code,
        defaults={
            'name': kwargs.pop('name', code.replace('_', ' ').title()),
            'chain': kwargs.pop('chain', code),
            'country': kwargs.pop('country', 'CZ'),
            'currency': kwargs.pop('currency', 'CZK'),
            **kwargs,
        },
    )[0]
```

Then change `make_price`'s signature to add two params (place them with the other keyword args):

```python
    valid_for_days: int = 7,
    valid_from_offset_days: int = 0,
    source_url: str = '',
    confidence: Decimal = Decimal('0.85'),
```

And change the body's time handling + record creation:

```python
    now = timezone.now()
    valid_from = now + timedelta(days=valid_from_offset_days)
    return PriceRecord.objects.create(
        store_product=store_product,
        price=Decimal(str(price)),
        currency=currency or store.currency,
        source_type=source_type,
        confidence=confidence,
        valid_from=valid_from,
        valid_until=valid_from + timedelta(days=valid_for_days),
        original_price=Decimal(str(original_price)) if original_price is not None else None,
        discount_percentage=discount_percentage,
        scraped_at=now,
        source_url=source_url,
    )
```

(For `valid_from_offset_days=0` this is identical to the old behaviour — `valid_from=now`, `valid_until=now+valid_for_days` — so existing tests are unaffected.)

- [ ] **Step 2: Verify existing pricing tests still pass**

Run: `python3 manage.py test diet_planner.tests.test_build_price_book diet_planner.tests.test_estimate_pricer -v 1`
Expected: OK (all pass — factory change is backward-compatible).

- [ ] **Step 3: Commit**

```bash
git add diet_planner/tests/factories.py
git commit -m "test(pricing): make_store helper + make_price valid_from offset/source_url

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: `recipe_deals` service (Phase 1b — the ACTIVE-only matcher)

**Files:**
- Create: `diet_planner/services/recipe_deals.py`
- Test: `diet_planner/tests/test_recipe_deals.py`

- [ ] **Step 1: Write the failing tests**

Create `diet_planner/tests/test_recipe_deals.py`:

```python
"""recipe_deals active-only matching.

A deal is ACTIVE only inside its real validity window (valid_from <= now <
valid_until, non-null end), from a real LEAFLET_DISCOUNT record tied to a
canonical. Future-dated (planned), expired, open-ended, non-leaflet, and
canonical-less records are never ACTIVE.
"""
from django.test import TestCase

from diet_planner.models import PriceSourceType
from diet_planner.services.canonical_lookup import clear_cache
from diet_planner.services.recipe_deals import recipe_deals
from diet_planner.tests.factories import make_canonical, make_price, make_store


class RecipeDealsTest(TestCase):
    def setUp(self):
        # name_cs='cibule' so resolve_canonical('cibule') maps to this canonical
        # (the resolver is DB-based over name/name_cs/name_sk + aliases).
        make_store('LIDL_CZ', name='Lidl')
        make_store('ALBERT_CZ', name='Albert')
        self.onion = make_canonical('onion', default_unit='ks', name_cs='cibule')
        clear_cache()   # drop the cached normalized index after seeding rows

    def _leaflet(self, canonical, *, store='LIDL_CZ', name='cibule',
                 offset=0, days=7, url='http://lidl.cz/cibule'):
        return make_price(
            store_code=store, normalized_name=name, price='9.90',
            source_type=PriceSourceType.LEAFLET_DISCOUNT, canonical=canonical,
            valid_from_offset_days=offset, valid_for_days=days, source_url=url,
        )

    def test_active_deal_is_matched(self):
        self._leaflet(self.onion)
        out = recipe_deals([{'name': 'cibule', 'canonical': 'onion',
                             'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 1)
        self.assertEqual(out['total'], 1)
        deal = out['deals'][0]
        self.assertEqual(deal['canonical'], 'onion')
        self.assertEqual(deal['shop'], 'Lidl')
        self.assertEqual(deal['source_url'], 'http://lidl.cz/cibule')
        self.assertEqual(deal['ingredient'], 'cibule')

    def test_future_dated_planned_deal_excluded(self):
        self._leaflet(self.onion, offset=3)   # starts in 3 days
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_expired_deal_excluded(self):
        self._leaflet(self.onion, offset=-10, days=7)  # ended 3 days ago
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_open_ended_deal_excluded(self):
        pr = self._leaflet(self.onion)
        pr.valid_until = None
        pr.save(update_fields=['valid_until'])
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_regular_price_is_not_a_deal(self):
        make_price(store_code='LIDL_CZ', normalized_name='cibule', price='9.90',
                   source_type=PriceSourceType.STORE_REGULAR, canonical=self.onion)
        out = recipe_deals([{'canonical': 'onion', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 0)

    def test_canonical_resolved_from_name_when_slug_absent(self):
        self._leaflet(self.onion)
        out = recipe_deals([{'name': 'cibule', 'quantity': 1, 'unit': 'ks'}])
        self.assertEqual(out['matched'], 1)

    def test_unmatched_ingredient_counts_toward_total_only(self):
        self._leaflet(self.onion)
        out = recipe_deals([
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks'},
            {'name': 'mystery', 'canonical': 'mystery-xyz', 'quantity': 1, 'unit': 'g'},
        ])
        self.assertEqual(out['matched'], 1)
        self.assertEqual(out['total'], 2)

    def test_optional_ingredient_ignored(self):
        self._leaflet(self.onion)
        out = recipe_deals([
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks'},
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks', 'optional': True},
        ])
        self.assertEqual(out['total'], 1)   # optional not counted
        self.assertEqual(out['matched'], 1)

    def test_deduped_to_one_deal_per_canonical(self):
        self._leaflet(self.onion, store='LIDL_CZ')
        self._leaflet(self.onion, store='ALBERT_CZ', url='http://albert.cz/c')
        out = recipe_deals([
            {'canonical': 'onion', 'quantity': 1, 'unit': 'ks'},
            {'canonical': 'onion', 'quantity': 2, 'unit': 'ks'},
        ])
        self.assertEqual(out['matched'], 1)
        self.assertEqual(len(out['deals']), 1)

    def test_empty_ingredients(self):
        self.assertEqual(recipe_deals([]), {'matched': 0, 'total': 0, 'deals': []})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 manage.py test diet_planner.tests.test_recipe_deals -v 1`
Expected: FAIL — `ModuleNotFoundError: No module named 'diet_planner.services.recipe_deals'`.

- [ ] **Step 3: Write the service**

Create `diet_planner/services/recipe_deals.py`:

```python
"""Active leaflet deals for a recipe's ingredients.

A deal is ACTIVE only when a real LEAFLET_DISCOUNT PriceRecord is in its
validity window right now (valid_from <= now < valid_until, with a real
non-null end), tied to a canonical ingredient. Nothing future-dated (planned),
expired, open-ended, fabricated, or mocked is ever ACTIVE. See
docs/superpowers/specs/2026-06-23-recipe-deals-headline-design.md.
"""
from diet_planner.models import PriceRecord, PriceSourceType
from diet_planner.services.canonical_lookup import resolve_canonical


def _ingredient_slug(ingredient):
    slug = (ingredient.get('canonical') or '').strip()
    if slug:
        return slug
    name = (ingredient.get('name') or '').strip()
    canonical = resolve_canonical(name) if name else None
    return canonical.slug if canonical else None


def _active_deal_index():
    """canonical slug -> chosen active deal dict.

    Active window enforced by .current() (valid_from <= now and not expired);
    we additionally require a real end date and a canonical link. Deterministic
    pick per canonical: soonest-expiring, then store code.
    """
    records = (
        PriceRecord.objects.current()
        .filter(
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_until__isnull=False,
            store_product__canonical_ingredient__isnull=False,
        )
        .select_related('store_product__store',
                        'store_product__canonical_ingredient')
        .order_by('valid_until', 'store_product__store__code')
    )
    index = {}
    for record in records:
        product = record.store_product
        slug = product.canonical_ingredient.slug
        if slug in index:                      # keep first = soonest-expiring
            continue
        index[slug] = {
            'canonical': slug,
            # Clean brand name for the headline ("Lidl"), not the verbose seeded
            # store.name ("Lidl (Czech Republic)"). chain is an uppercase code.
            'shop': product.store.chain.title(),
            'display_name': product.name,
            'source_url': record.source_url or product.source_url or '',
            'valid_until': record.valid_until,
        }
    return index


def recipe_deals(ingredients):
    """Active deals for a recipe's ingredient list.

    Returns {matched, total, deals}: `total` counts non-optional ingredients,
    `deals` has one entry per matched canonical (deduped), each carrying the
    recipe `ingredient` label.
    """
    index = _active_deal_index()
    deals = []
    seen = set()
    total = 0
    for ingredient in ingredients or []:
        if ingredient.get('optional'):
            continue
        total += 1
        slug = _ingredient_slug(ingredient)
        if not slug or slug in seen:
            continue
        deal = index.get(slug)
        if not deal:
            continue
        seen.add(slug)
        deals.append({**deal, 'ingredient': ingredient.get('name') or slug})
    return {'matched': len(deals), 'total': total, 'deals': deals}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 manage.py test diet_planner.tests.test_recipe_deals -v 1`
Expected: OK — 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/recipe_deals.py diet_planner/tests/test_recipe_deals.py
git commit -m "feat(pricing): recipe_deals service — active-only leaflet deal matching

Returns {matched,total,deals} for a recipe's ingredients, counting only
genuinely-active LEAFLET_DISCOUNT records (valid_from<=now<valid_until, real
end date, canonical-linked). Future-dated/expired/open-ended excluded.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Expose `deals` on `RecipeSerializer`

**Files:**
- Modify: `diet_planner/serializers.py` (`RecipeSerializer`, around lines 267–323)
- Test: `diet_planner/tests/test_recipe_serializer_deals.py`

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_recipe_serializer_deals.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal, PriceSourceType, Recipe
from diet_planner.serializers import RecipeSerializer
from diet_planner.tests.factories import make_canonical, make_price, make_store


class RecipeDealsFieldTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u1', password='x')
        self.goal = DietaryGoal.objects.create(user=self.user, country='CZ')
        make_store('LIDL_CZ', name='Lidl')
        onion = make_canonical('onion', default_unit='ks')
        make_price(store_code='LIDL_CZ', normalized_name='cibule', price='9.90',
                   source_type=PriceSourceType.LEAFLET_DISCOUNT, canonical=onion,
                   source_url='http://lidl.cz/cibule')

    def _recipe(self, ingredients):
        return Recipe.objects.create(
            meal_identifier=f'g{self.goal.id}:0:dinner:0',
            dietary_goal=self.goal, name='Test dish',
            ingredients=ingredients, servings=4,
        )

    def test_deals_present_for_recipe_with_active_deal(self):
        r = self._recipe([{'name': 'cibule', 'canonical': 'onion',
                           'quantity': 1, 'unit': 'ks'}])
        deals = RecipeSerializer(r).data['deals']
        self.assertEqual(deals['matched'], 1)
        self.assertEqual(deals['total'], 1)
        self.assertEqual(deals['deals'][0]['shop'], 'Lidl')

    def test_deals_empty_when_no_match(self):
        r = self._recipe([{'name': 'mystery', 'canonical': 'mystery-xyz',
                           'quantity': 100, 'unit': 'g'}])
        deals = RecipeSerializer(r).data['deals']
        self.assertEqual(deals['matched'], 0)
        self.assertEqual(deals['deals'], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 manage.py test diet_planner.tests.test_recipe_serializer_deals -v 1`
Expected: FAIL — `KeyError: 'deals'` (field not on serializer).

- [ ] **Step 3: Add the `deals` field**

In `diet_planner/serializers.py`, in `RecipeSerializer`, next to the existing `price_range = serializers.SerializerMethodField()` (around line 267) add:

```python
    deals = serializers.SerializerMethodField()
```

Add `'deals'` after `'price_range',` in BOTH the `Meta.fields` list (around line 280) AND the `Meta.read_only_fields` list (around line 296) — mirroring how `price_range` (a read-only `SerializerMethodField`) appears in both:

```python
            'price_range',
            'deals',
```

Add the method next to `get_price_range` (after it, around line 323):

```python
    def get_deals(self, obj):
        """Currently-active leaflet deals on this recipe's ingredients.
        See services.recipe_deals — active-only, never fabricated."""
        from .services.recipe_deals import recipe_deals
        return recipe_deals(obj.ingredients or [])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 manage.py test diet_planner.tests.test_recipe_serializer_deals -v 1`
Expected: OK — 2 tests pass.

- [ ] **Step 5: Run the serializer + deals suites together (no regressions)**

Run: `python3 manage.py test diet_planner.tests.test_recipe_serializer_deals diet_planner.tests.test_recipe_serializer_price_range diet_planner.tests.test_recipe_deals -v 1`
Expected: OK — all pass (price_range still works, dormant but intact).

- [ ] **Step 6: Commit**

```bash
git add diet_planner/serializers.py diet_planner/tests/test_recipe_serializer_deals.py
git commit -m "feat(pricing): expose active deals on RecipeSerializer.deals

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Frontend deal types + accessor

**Files:**
- Modify: `frontend/src/lib/pricing.ts`

- [ ] **Step 1: Add `RecipeDeal`/`RecipeDeals` types and `getRecipeDeals`**

Append to `frontend/src/lib/pricing.ts`:

```typescript
// ---- Per-recipe active deals (deals-headline pivot, 2026-06-23) ----

// Mirrors backend services.recipe_deals output. Active-only — every deal here
// is currently live (valid_from <= now < valid_until). Never a price/savings.
export interface RecipeDeal {
  ingredient: string;
  canonical: string;
  shop: string;
  display_name: string;
  source_url: string;
  valid_until: string | null;
}

export interface RecipeDeals {
  matched: number;
  total: number;
  deals: RecipeDeal[];
}

// Pull active deals off a recipe object; null when there are none to show.
export const getRecipeDeals = (recipe: any): RecipeDeals | null => {
  const d = recipe?.deals as RecipeDeals | undefined;
  return d && d.matched > 0 ? d : null;
};
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/pricing.ts
git commit -m "feat(pricing): RecipeDeals type + getRecipeDeals accessor

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Render the deals headline (replace the dead price block)

**Files:**
- Modify: `frontend/src/pages/PublicRecipePage.tsx`
- Modify: `frontend/src/pages/RecipePage.tsx`
- Modify: `frontend/src/pages/RecipeIndexPage.tsx`

CZ copy (Claude-authored; EN gloss for review):
- Headline: `{matched} z {total} surovin ve slevě tento týden` — EN: "{matched} of {total} ingredients on sale this week".
- List row: `{display_name} — {shop}` linking to `source_url`. EN: same.

- [ ] **Step 1: Replace the price block in `PublicRecipePage.tsx`**

Change the import on line 8 from:

```typescript
import { fmtRange, getRecipeRange } from '@/lib/pricing';
```

to:

```typescript
import { getRecipeDeals } from '@/lib/pricing';
```

Replace the entire `{getRecipeRange(recipe) && (() => { … })()}` block (around lines 144–158) with:

```tsx
        {getRecipeDeals(recipe) && (() => {
          const d = getRecipeDeals(recipe)!;
          return (
            <div className="mt-3 rounded-lg bg-emerald-50 p-3">
              <p className="text-sm font-medium text-emerald-800">
                {d.matched} z {d.total} surovin ve slevě tento týden
              </p>
              <ul className="mt-1 space-y-0.5">
                {d.deals.map((deal) => (
                  <li key={deal.canonical} className="text-[13px] text-emerald-700">
                    <a href={deal.source_url} target="_blank" rel="noopener noreferrer"
                       className="hover:underline">
                      {deal.display_name} — {deal.shop}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          );
        })()}
```

- [ ] **Step 2: Replace the price block in `RecipePage.tsx`**

Apply the same import change (line 10) and replace the `{getRecipeRange(recipe) && (() => { … })()}` block (around lines 165–179) with the identical deals block from Step 1.

- [ ] **Step 3: Replace the price block in `RecipeIndexPage.tsx`**

Change the import (line 8) to `import { getRecipeDeals } from '@/lib/pricing';`. Replace the grid-card `{getRecipeRange(recipe) && (() => { … })()}` block (around lines 84–92) with a compact count-only badge (the grid card has no room for a full list):

```tsx
                    {getRecipeDeals(recipe) && (() => {
                      const d = getRecipeDeals(recipe)!;
                      return (
                        <span className="mt-1 inline-block rounded bg-emerald-100 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700">
                          {d.matched} ve slevě
                        </span>
                      );
                    })()}
```

(EN gloss for `{d.matched} ve slevě`: "{matched} on sale".)

- [ ] **Step 4: Verify no dangling references and type-check**

Run: `cd frontend && grep -rn "getRecipeRange\|fmtRange" src/pages/ ; npx tsc --noEmit`
Expected: grep returns nothing in `src/pages/`; `tsc` exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PublicRecipePage.tsx frontend/src/pages/RecipePage.tsx frontend/src/pages/RecipeIndexPage.tsx
git commit -m "feat(pricing): recipe deals headline replaces absolute price block

Detail pages show 'N z M surovin ve slevě tento týden' + deal list (shop +
leaflet link); grid shows a compact 'N ve slevě' badge. Active deals only.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Full backend suite + final verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full pricing-related backend suite**

Run: `python3 manage.py test diet_planner.tests.test_recipe_deals diet_planner.tests.test_recipe_serializer_deals diet_planner.tests.test_recipe_serializer_price_range diet_planner.tests.test_estimate_pricer diet_planner.tests.test_build_price_book diet_planner.tests.test_recipe_pricing diet_planner.tests.test_pricing_core -v 1`
Expected: OK — all pass.

- [ ] **Step 2: Frontend type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3 (optional, recommended): verify on prod data**

After deploy, fetch a known recipe and confirm the `deals` payload is active-only:
`curl -fsS "https://squid-app-6avsy.ondigitalocean.app/api/recipes/public/35/" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['deals'])"`
Expected: `{matched, total, deals:[…]}` with deals whose `valid_until` is in the future.

---

## Notes / out of scope

- **CZK savings** is deferred (no `discount_percentage` in data) — separate spec/phase.
- **Only 18 recipes are `is_public=True`** (vs 372 curated) — a separate publishing gap; not addressed here.
- `price_range` serializer field and the pricing engine are intentionally **kept** (dormant) for the later savings phase; only the frontend stops using them.
- No frontend unit-test harness exists; frontend tasks are verified by `tsc --noEmit` and (Task 7) prod-data spot check.
