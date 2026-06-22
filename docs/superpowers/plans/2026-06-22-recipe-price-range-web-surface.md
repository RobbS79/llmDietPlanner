# Recipe Price-Range — Web Surface (Sub-project 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Expose the per-recipe from–to price range on the recipe API and render it on the three recipe-serializer-fed web surfaces (public recipe grid, public recipe detail, private recipe detail).

**Architecture:** Add one `price_range` `SerializerMethodField` to the single `RecipeSerializer`, computed via the `price_recipe` engine from sub-project 1 (not the heavy `compute_pricing` catalog path). The field flows automatically to every endpoint using that serializer. The React side adds a `RecipePriceRange` type + range formatter to `lib/pricing.ts`, then renders a price block on each surface, **only when the range is present and `confident`**.

**Tech Stack:** Django REST Framework serializer; React 18 + TypeScript + Tailwind (no FE unit tests — verified by `tsc`/build).

**Scope (v1):** API + `RecipeIndexPage`, `PublicRecipePage`, `RecipePage`. **Out:** PlanView meal cards (fed by plan-days JSON, not the recipe serializer), the Django SSR HTML recipe page (`/recepty/{pk}/{slug}/`), and request-based currency conversion (uses the recipe's goal currency, default CZK).

Depends on: `diet_planner/services/recipe_pricing.py` (`price_recipe`, `RecipeRange`).

---

### Task 1: Add `price_range` to RecipeSerializer

**Files:**
- Modify: `diet_planner/serializers.py:263-301` (`RecipeSerializer`)
- Test: `diet_planner/tests/test_recipe_serializer_price_range.py` (create)

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_recipe_serializer_price_range.py`:

```python
from django.contrib.auth.models import User
from django.test import TestCase

from diet_planner.models import DietaryGoal, Recipe
from diet_planner.serializers import RecipeSerializer


class RecipePriceRangeFieldTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('u1', password='x')
        # country drives currency; CZ -> CZK, matching the price book.
        self.goal = DietaryGoal.objects.create(user=self.user, country='CZ')

    def _recipe(self, ingredients, servings=4):
        return Recipe.objects.create(
            meal_identifier=f'g{self.goal.id}:0:dinner:0',
            dietary_goal=self.goal, name='Test dish',
            ingredients=ingredients, servings=servings,
        )

    def test_price_range_present_for_priceable_recipe(self):
        # canonicals known to exist in the real book
        r = self._recipe([
            {'name': 'kuřecí prsa', 'canonical': 'chicken-breast', 'quantity': 600, 'unit': 'g'},
            {'name': 'rýže', 'canonical': 'rice-jasmine', 'quantity': 320, 'unit': 'g'},
        ])
        pr = RecipeSerializer(r).data['price_range']
        self.assertIsNotNone(pr)
        self.assertLess(pr['low'], pr['high'])               # range opens upward
        self.assertEqual(pr['currency'], 'CZK')
        self.assertTrue(pr['confident'])
        self.assertIsNotNone(pr['per_portion_low'])
        # per-portion is the total divided by servings
        self.assertAlmostEqual(pr['per_portion_low'], pr['low'] / 4, places=2)

    def test_price_range_null_when_nothing_prices(self):
        r = self._recipe([{'name': 'mystery', 'canonical': 'mystery-xyz',
                           'quantity': 100, 'unit': 'g'}])
        self.assertIsNone(RecipeSerializer(r).data['price_range'])

    def test_price_range_null_for_empty_ingredients(self):
        r = self._recipe([])
        self.assertIsNone(RecipeSerializer(r).data['price_range'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 manage.py test diet_planner.tests.test_recipe_serializer_price_range -v 2`
Expected: FAIL — `KeyError: 'price_range'`

- [ ] **Step 3: Add the field + method**

In `diet_planner/serializers.py`, in `RecipeSerializer`:

Add field declaration after `image_url = serializers.SerializerMethodField()`:

```python
    price_range = serializers.SerializerMethodField()
```

Add `'price_range',` to `Meta.fields` (after `'image_url',`) and to `Meta.read_only_fields`.

Add the method (next to `get_image_url`):

```python
    def get_price_range(self, obj):
        """Honest per-recipe from-to cost from the static book. Null when the
        recipe has no priceable ingredients. See recipe_pricing.price_recipe."""
        from .services.recipe_pricing import price_recipe

        currency = getattr(obj.dietary_goal, 'currency', None) or 'CZK'
        r = price_recipe(obj.ingredients or [], obj.servings, currency=currency)
        if r is None:
            return None
        return {
            'low': round(r.low, 2),
            'high': round(r.high, 2),
            'per_portion_low': round(r.per_portion_low, 2) if r.per_portion_low is not None else None,
            'per_portion_high': round(r.per_portion_high, 2) if r.per_portion_high is not None else None,
            'currency': r.currency,
            'confident': r.confident,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 manage.py test diet_planner.tests.test_recipe_serializer_price_range -v 2`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add diet_planner/serializers.py diet_planner/tests/test_recipe_serializer_price_range.py
git commit -m "feat(pricing): expose per-recipe price_range on RecipeSerializer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Frontend types + range formatter

**Files:**
- Modify: `frontend/src/lib/pricing.ts`

- [ ] **Step 1: Add the type and helper**

Append to `frontend/src/lib/pricing.ts`:

```typescript
// ---- Per-recipe price range (sub-project 2) ----

// Mirrors the backend RecipeSerializer.price_range payload
// (diet_planner/services/recipe_pricing.py RecipeRange). Always an estimate.
export interface RecipePriceRange {
  low: number;
  high: number;
  per_portion_low: number | null;
  per_portion_high: number | null;
  currency: string;
  confident: boolean;
}

// Format a from–to as "1 250–1 600" (Czech locale, em dash, no currency).
// Caller adds the `~` prefix and currency suffix to match existing copy.
export const fmtRange = (
  lo: number | null | undefined,
  hi: number | null | undefined,
  decimals = 0,
): string => `${fmtMoney(lo, decimals)}–${fmtMoney(hi, decimals)}`;

// Pull a confident price range off a recipe object, else null.
export const getRecipeRange = (recipe: any): RecipePriceRange | null => {
  const pr = recipe?.price_range;
  return pr && pr.confident ? (pr as RecipePriceRange) : null;
};
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/pricing.ts
git commit -m "feat(pricing): RecipePriceRange type + fmtRange/getRecipeRange helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Render price card on recipe detail pages

Both `PublicRecipePage.tsx` and `RecipePage.tsx` share the same layout (header badges → ingredients sidebar → instructions). Add an identical price card after the header badges, before the two-column body.

**Files:**
- Modify: `frontend/src/pages/PublicRecipePage.tsx`
- Modify: `frontend/src/pages/RecipePage.tsx`

- [ ] **Step 1: Import the helpers (both files)**

Ensure each file imports from the pricing lib (add `fmtRange`, `getRecipeRange`, `fmtMoney` to the existing `lib/pricing` import, or add a new import line):

```typescript
import { fmtMoney, fmtRange, getRecipeRange } from '../lib/pricing';
```

- [ ] **Step 2: Add the price card (both files)**

Immediately after the recipe header/badges block (around the description, before the ingredients/instructions two-column grid), insert:

```tsx
{getRecipeRange(recipe) && (
  <div className="mb-8 inline-block rounded-xl border border-emerald-500/15 bg-emerald-500/5 px-5 py-4">
    <p className="mb-1 text-[9px] font-black uppercase italic tracking-[0.3em] text-zinc-400">
      Přibližná cena · na porci
    </p>
    <p className="text-3xl font-black italic tracking-tighter tabular-nums text-white">
      ~{fmtRange(getRecipeRange(recipe)!.per_portion_low, getRecipeRange(recipe)!.per_portion_high)}{' '}
      <span className="text-base not-italic text-emerald-500">{getRecipeRange(recipe)!.currency === 'EUR' ? '€' : 'Kč'}</span>
    </p>
    <p className="mt-1 text-[11px] italic text-zinc-400 tabular-nums">
      celý recept ~{fmtRange(getRecipeRange(recipe)!.low, getRecipeRange(recipe)!.high)} {getRecipeRange(recipe)!.currency === 'EUR' ? '€' : 'Kč'}
    </p>
    <p className="mt-2 text-[10px] italic text-zinc-500">z reálných cen Rohlíku · jen odhad</p>
  </div>
)}
```

(If `per_portion_low` is null because servings is missing, the per-portion line still renders "—" via fmtMoney; acceptable — most recipes have servings. The whole-recipe line is always meaningful.)

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds, no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/PublicRecipePage.tsx frontend/src/pages/RecipePage.tsx
git commit -m "feat(pricing): per-recipe price-range card on recipe detail pages

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Render inline range on the public recipe grid

**Files:**
- Modify: `frontend/src/pages/RecipeIndexPage.tsx`

- [ ] **Step 1: Import the helpers**

Add to the imports:

```typescript
import { fmtRange, getRecipeRange } from '../lib/pricing';
```

- [ ] **Step 2: Add inline range to each card**

Inside the card render loop (after the description paragraph, before the prep-time/servings footer), insert:

```tsx
{getRecipeRange(recipe) && (
  <p className="mt-2 text-[10px] font-black uppercase italic tracking-widest tabular-nums text-emerald-400">
    ~{fmtRange(getRecipeRange(recipe)!.low, getRecipeRange(recipe)!.high)} {getRecipeRange(recipe)!.currency === 'EUR' ? '€' : 'Kč'}
    {getRecipeRange(recipe)!.per_portion_low != null && (
      <span className="text-zinc-500"> · ~{fmtRange(getRecipeRange(recipe)!.per_portion_low, getRecipeRange(recipe)!.per_portion_high)}/porce</span>
    )}
  </p>
)}
```

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/RecipeIndexPage.tsx
git commit -m "feat(pricing): inline per-recipe price range on public recipe grid

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage (umbrella sub-project 2 = "Surface range on recipe display + API"):**
- API exposure → Task 1 (`price_range` on the one shared `RecipeSerializer`, reaches all 3 endpoints).
- Public grid → Task 4. Public detail → Task 3 (`PublicRecipePage`). Private detail → Task 3 (`RecipePage`).
- Uses `price_recipe` engine (not `compute_pricing`) → Task 1 Step 3.
- Render only when confident → Tasks 3 & 4 via `getRecipeRange`.

**Placeholder scan:** none — all code concrete.

**Type consistency:** `price_range` payload keys (`low`, `high`, `per_portion_low`, `per_portion_high`, `currency`, `confident`) identical across serializer (Task 1), TS type (Task 2), and component usage (Tasks 3-4). `getRecipeRange`/`fmtRange` signatures match their call sites.

**Deferred (later sub-projects / explicitly out of v1):** PlanView meal-card range (needs price in plan-days payload), SSR HTML recipe page price, multi-currency conversion by visitor locale, per-recipe shopping lists (sub-project 3), plan roll-up (sub-project 4).
