# Per-Recipe Portion Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive portion stepper to the per-recipe view so changing the portion count rescales the displayed ingredient amounts live, and fix the broken serving denominator that drives it.

**Architecture:** Backend makes `Recipe.servings` truthful (it must equal the portion count the stored ingredient quantities describe). The frontend scales **client-side**: a `PortionStepper` holds the chosen portion count and pure helpers in `lib/portions.ts` compute `qty × (chosen / baseServings)` and format each amount (Czech decimal comma, unit-aware rounding, Czech plurals). A shared `RecipeIngredients` component owns the stepper + list and is dropped into both `RecipePage` and `PublicRecipePage`. The deals headline is portion-invariant and is left untouched.

**Tech Stack:** Django 5.1 (DRF) + React 18 / TypeScript / Vite / Tailwind. Backend tests: Django `TestCase` (`python manage.py test`). Frontend tests: Vitest + Testing Library (added in Task 3 — not yet present).

**Spec:** `docs/superpowers/specs/2026-06-23-per-recipe-portion-scaling-design.md`

---

## File Structure

**Backend (modify):**
- `diet_planner/services/recipe_retrieval.py` — `scale_recipe_to_meal` emits `servings`.
- `diet_planner/views.py` — `RecipeDetailView` create passes `servings`.
- `diet_planner/tests/test_recipe_retrieval.py` — new assertions.
- `diet_planner/tests/test_recipe_servings_creation.py` — new view test (create).

**Frontend (create):**
- `frontend/src/lib/portions.ts` — pure scaling/format/plural helpers.
- `frontend/src/lib/portions.test.ts` — helper unit tests.
- `frontend/src/components/recipe/PortionStepper.tsx` — −/[n]/+ control.
- `frontend/src/components/recipe/PortionStepper.test.tsx` — component test.
- `frontend/src/components/recipe/RecipeIngredients.tsx` — Ingredients card (stepper + scaled list).
- `frontend/src/components/recipe/RecipeIngredients.test.tsx` — component test.
- `frontend/src/test/setup.ts` — Testing Library setup.

**Frontend (modify):**
- `frontend/vite.config.ts` — add `test` block.
- `frontend/package.json` — add dev deps + `test` scripts.
- `frontend/src/pages/RecipePage.tsx` — use `RecipeIngredients`, drop the duplicate static servings badge.
- `frontend/src/pages/PublicRecipePage.tsx` — same.

---

## Task 1: Backend — `scale_recipe_to_meal` emits truthful `servings`

**Files:**
- Modify: `diet_planner/services/recipe_retrieval.py:322-337` (the returned dict)
- Test: `diet_planner/tests/test_recipe_retrieval.py`

- [ ] **Step 1: Write the failing test**

Add to `diet_planner/tests/test_recipe_retrieval.py` inside `class ScaleTest(TestCase):` (the class starting at line 163):

```python
    def test_meal_carries_base_servings(self):
        r = make_recipe(base_servings=4)
        meal = scale_recipe_to_meal(r)
        self.assertEqual(meal['servings'], 4)

    def test_meal_servings_defaults_to_base_one(self):
        r = make_recipe(base_servings=1)
        meal = scale_recipe_to_meal(r)
        self.assertEqual(meal['servings'], 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_recipe_retrieval.ScaleTest -v 2`
Expected: FAIL — `KeyError: 'servings'` (the meal dict has no `servings` key).

- [ ] **Step 3: Add the `servings` key to the meal dict**

In `diet_planner/services/recipe_retrieval.py`, in the `return { ... }` of `scale_recipe_to_meal` (currently lines 322-337), add a `servings` entry right after `'name'`:

```python
    return {
        'name': recipe.name_cs,
        'servings': recipe.base_servings,
        'description': recipe.description or '',
        'food_category': '',  # stock-image slug; left blank -> generic fallback
        'preparation_time': recipe.total_time or recipe.prep_time or None,
        'ingredients': ingredients,
        'instructions': instructions,
        'nutritional_info': nutritional_info,
        # --- grounding provenance (consumed by RecipePage attribution) ---
        'source': 'curated',
        'curated_recipe_id': recipe.id,
        'curated_recipe_slug': recipe.slug,
        'source_name': recipe.source_name,
        'source_url': recipe.source_url,
        'source_author': recipe.source_author or '',
    }
```

(Ingredient quantities stay at base — `factor=1.0` — which is exactly what `base_servings` portions describe. Do not change the scaling math.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_recipe_retrieval.ScaleTest -v 2`
Expected: PASS (including the existing `test_scaling_factor`).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/services/recipe_retrieval.py diet_planner/tests/test_recipe_retrieval.py
git commit -m "fix(recipe): scale_recipe_to_meal emits base_servings as meal servings

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backend — `RecipeDetailView` persists `servings` on create

**Files:**
- Modify: `diet_planner/views.py:467-481` (the `Recipe.objects.create(...)` call)
- Test: `diet_planner/tests/test_recipe_servings_creation.py` (create)

- [ ] **Step 1: Write the failing test**

Create `diet_planner/tests/test_recipe_servings_creation.py`:

```python
"""RecipeDetailView must persist the meal's serving count so per-portion
scaling and pricing use the true denominator (not the model default of 1)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from diet_planner.models import DietaryGoal, DietaryPlan, Recipe


class RecipeCreationServingsTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="chef")
        self.goal = DietaryGoal.objects.create(
            user=self.user, prompt="x", num_days=1, country="CZ", currency="CZK",
        )
        # A curated meal already has vetted instructions, so the view skips the
        # LLM regeneration path entirely (is_curated == True).
        self.meal = {
            "name": "Bramborové halušky",
            "servings": 4,
            "source": "curated",
            "description": "",
            "instructions": ["Uvař brambory.", "Zpracuj těsto a vař halušky."],
            "ingredients": [{"name": "brambory", "quantity": 600, "unit": "g"}],
            "nutritional_info": {},
        }
        DietaryPlan.objects.create(
            dietary_goal=self.goal,
            days=[{"day_number": 1, "lunch": self.meal}],
            currency="CZK",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_created_recipe_uses_meal_servings(self):
        url = reverse(
            "diet_planner:recipe-detail",
            kwargs={"meal_identifier": f"{self.goal.id}:1:lunch:0"},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        recipe = Recipe.objects.get(meal_identifier=f"{self.goal.id}:1:lunch:0")
        self.assertEqual(recipe.servings, 4)

    def test_servings_defaults_to_one_when_absent(self):
        # A generated (non-curated) meal carries no servings -> default 1.
        DietaryPlan.objects.filter(dietary_goal=self.goal).update(
            days=[{"day_number": 1, "dinner": {
                "name": "Salát", "source": "curated",
                "instructions": ["Smíchej suroviny dohromady."],
                "ingredients": [{"name": "salát", "quantity": 100, "unit": "g"}],
            }}],
        )
        url = reverse(
            "diet_planner:recipe-detail",
            kwargs={"meal_identifier": f"{self.goal.id}:1:dinner:0"},
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        recipe = Recipe.objects.get(meal_identifier=f"{self.goal.id}:1:dinner:0")
        self.assertEqual(recipe.servings, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python manage.py test diet_planner.tests.test_recipe_servings_creation -v 2`
Expected: `test_created_recipe_uses_meal_servings` FAILS — `4 != 1` (servings not passed, defaults to 1). `test_servings_defaults_to_one_when_absent` passes already.

- [ ] **Step 3: Pass `servings` into `Recipe.objects.create`**

In `diet_planner/views.py`, the `Recipe.objects.create(...)` call (lines 467-481), add a `servings` kwarg after `dietary_goal=goal,`:

```python
        recipe = Recipe.objects.create(
            meal_identifier=meal_identifier,
            dietary_goal=goal,
            servings=meal.get('servings') or 1,
            name=meal.get('name', ''),
            description=meal.get('description', ''),
            food_category=meal.get('food_category', '') or guess_category(meal.get('name', ''), meal.get('ingredients', [])),
            instructions=instructions,
            ingredients=meal.get('ingredients', []),
            preparation_time=meal.get('preparation_time'),
            nutritional_info=meal.get('nutritional_info', {}),
            source_name=meal.get('source_name', '') or '',
            source_url=meal.get('source_url', '') or '',
            source_author=meal.get('source_author', '') or '',
            curated_recipe_slug=meal.get('curated_recipe_slug', '') or '',
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python manage.py test diet_planner.tests.test_recipe_servings_creation -v 2`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add diet_planner/views.py diet_planner/tests/test_recipe_servings_creation.py
git commit -m "fix(recipe): persist meal servings on Recipe create

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Frontend — add Vitest + Testing Library

The frontend currently has **no unit-test runner** (only Playwright e2e). This task adds Vitest so the portion helpers and components can be TDD'd.

**Files:**
- Modify: `frontend/package.json` (dev deps + scripts)
- Modify: `frontend/vite.config.ts` (test block)
- Create: `frontend/src/test/setup.ts`

- [ ] **Step 1: Install dev dependencies**

Run:
```bash
npm --prefix frontend install -D vitest@^2 jsdom@^25 @testing-library/react@^16 @testing-library/jest-dom@^6 @testing-library/user-event@^14
```
Expected: packages added to `devDependencies`, no errors.

- [ ] **Step 2: Create the Testing Library setup file**

Create `frontend/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

- [ ] **Step 3: Add the `test` block to `vite.config.ts`**

In `frontend/vite.config.ts`, add a `test` key to the returned config object (sibling of `build`). Also add the triple-slash reference at the very top of the file so TypeScript knows about `test`:

At the top of the file (line 1), add:
```ts
/// <reference types="vitest/config" />
```

Inside the returned config object (after the `build: { ... }` block), add:
```ts
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
```

- [ ] **Step 4: Add test scripts to `package.json`**

In `frontend/package.json` `"scripts"`, add:
```json
    "test": "vitest run",
    "test:watch": "vitest",
```

- [ ] **Step 5: Add a smoke test and run it**

Create `frontend/src/test/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest';

describe('vitest setup', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2);
  });
});
```

Run: `npm --prefix frontend run test`
Expected: PASS — 1 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/src/test/setup.ts frontend/src/test/smoke.test.ts
git commit -m "test(frontend): add vitest + testing-library harness

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Frontend — `lib/portions.ts` scaling & formatting helpers

**Files:**
- Create: `frontend/src/lib/portions.ts`
- Test: `frontend/src/lib/portions.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/portions.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import {
  scaleAmount,
  czechPlural,
  pluralizeUnit,
  roundForUnit,
  formatNumber,
  formatScaledIngredient,
  PORTION_FORMS,
} from './portions';

describe('scaleAmount', () => {
  it('scales linearly', () => {
    expect(scaleAmount(100, 4, 8)).toBe(200);
    expect(scaleAmount(100, 4, 2)).toBe(50);
  });
  it('treats non-positive base servings as 1', () => {
    expect(scaleAmount(100, 0, 3)).toBe(300);
  });
});

describe('czechPlural', () => {
  it('picks the right form', () => {
    expect(czechPlural(1, PORTION_FORMS)).toBe('porce');
    expect(czechPlural(3, PORTION_FORMS)).toBe('porce');
    expect(czechPlural(5, PORTION_FORMS)).toBe('porcí');
    expect(czechPlural(0, PORTION_FORMS)).toBe('porcí');
  });
});

describe('pluralizeUnit', () => {
  it('passes metric/unknown units through verbatim', () => {
    expect(pluralizeUnit(3, 'kg')).toBe('kg');
    expect(pluralizeUnit(3, 'g')).toBe('g');
    expect(pluralizeUnit(3, 'ks')).toBe('ks');
  });
  it('inflects known counted units for integers', () => {
    expect(pluralizeUnit(1, 'lžíce')).toBe('lžíce');
    expect(pluralizeUnit(5, 'lžíce')).toBe('lžic');
    expect(pluralizeUnit(5, 'vejce')).toBe('vajec');
  });
  it('uses the few-form for fractional amounts', () => {
    expect(pluralizeUnit(0.5, 'lžíce')).toBe('lžíce');
  });
  it('returns empty string for missing unit', () => {
    expect(pluralizeUnit(2, null)).toBe('');
  });
});

describe('roundForUnit', () => {
  it('rounds by unit family', () => {
    expect(roundForUnit(80.4, 'g')).toBe(80);
    expect(roundForUnit(0.3000004, 'kg')).toBe(0.3);
    expect(roundForUnit(1.24, 'ks')).toBe(1);
    expect(roundForUnit(1.3, 'ks')).toBe(1.5);
  });
});

describe('formatNumber', () => {
  it('uses a Czech decimal comma and trims zeros', () => {
    expect(formatNumber(0.5)).toBe('0,5');
    expect(formatNumber(80)).toBe('80');
    expect(formatNumber(1.5)).toBe('1,5');
  });
});

describe('formatScaledIngredient', () => {
  it('scales, rounds, and labels with unit', () => {
    const r = formatScaledIngredient(
      { name: 'brambory', quantity: 300, unit: 'kg' }, 4, 8,
    );
    expect(r.name).toBe('brambory');
    expect(r.amountLabel).toBe('600 kg');
  });
  it('returns a null amountLabel for to-taste ingredients', () => {
    const r = formatScaledIngredient(
      { name: 'sůl', quantity: null, unit: null }, 4, 8,
    );
    expect(r.amountLabel).toBeNull();
  });
  it('omits the unit when there is none', () => {
    const r = formatScaledIngredient(
      { name: 'vejce', quantity: 2, unit: '' }, 4, 8,
    );
    expect(r.amountLabel).toBe('4');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- portions`
Expected: FAIL — cannot resolve `./portions` (module not created yet).

- [ ] **Step 3: Implement `lib/portions.ts`**

Create `frontend/src/lib/portions.ts`:

```ts
// Per-recipe portion scaling helpers. Pure functions — no React, no I/O.
// Mirrors toprecepty.cz's model: exact base value per ingredient, scaled
// linearly to the chosen portion count, rounded only for display.

export type PluralForms = [one: string, few: string, many: string];

// 1 porce / 2-4 porce / 5+ porcí
export const PORTION_FORMS: PluralForms = ['porce', 'porce', 'porcí'];

// Counted Czech units that inflect. Metric units (g/kg/ml/l/ks) are invariant
// and intentionally absent — they pass through verbatim.
export const UNIT_PLURALS: Record<string, PluralForms> = {
  'lžíce': ['lžíce', 'lžíce', 'lžic'],
  'lžička': ['lžička', 'lžičky', 'lžiček'],
  'vejce': ['vejce', 'vejce', 'vajec'],
  'plátek': ['plátek', 'plátky', 'plátků'],
  'hrnek': ['hrnek', 'hrnky', 'hrnků'],
  'konzerva': ['konzerva', 'konzervy', 'konzerv'],
  'špetka': ['špetka', 'špetky', 'špetek'],
};

export interface IngredientInput {
  name: string;
  quantity: number | string | null;
  unit?: string | null;
  optional?: boolean;
}

export interface ScaledIngredient {
  name: string;
  amountLabel: string | null; // null when quantity-less ("to taste")
  optional: boolean;
}

export function scaleAmount(qty: number, baseServings: number, chosen: number): number {
  const base = baseServings > 0 ? baseServings : 1;
  return qty * (chosen / base);
}

export function czechPlural(n: number, forms: PluralForms): string {
  if (n === 1) return forms[0];
  if (n >= 2 && n <= 4) return forms[1];
  return forms[2];
}

export function pluralizeUnit(value: number, unit: string | null | undefined): string {
  if (!unit) return '';
  const forms = UNIT_PLURALS[unit];
  if (!forms) return unit; // metric / unknown -> verbatim
  if (Number.isInteger(value)) return czechPlural(value, forms);
  return forms[1]; // fractional decimals read naturally with the few-form
}

export function roundForUnit(value: number, unit: string | null | undefined): number {
  const u = (unit || '').toLowerCase();
  if (u === 'g' || u === 'ml') return Math.round(value);
  if (u === 'kg' || u === 'l') return Math.round(value * 10) / 10;
  if (u === 'ks' || u === '') return Math.round(value * 2) / 2; // allow halves
  return Math.round(value * 100) / 100; // up to 2 decimals
}

export function formatNumber(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  return rounded.toString().replace('.', ',');
}

export function formatScaledIngredient(
  ing: IngredientInput,
  baseServings: number,
  chosen: number,
): ScaledIngredient {
  const qty = ing.quantity;
  const optional = !!ing.optional;
  if (typeof qty !== 'number' || !(qty > 0)) {
    return { name: ing.name, amountLabel: null, optional };
  }
  const rounded = roundForUnit(scaleAmount(qty, baseServings, chosen), ing.unit);
  const unitLabel = pluralizeUnit(rounded, ing.unit);
  const num = formatNumber(rounded);
  return { name: ing.name, amountLabel: unitLabel ? `${num} ${unitLabel}` : num, optional };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- portions`
Expected: PASS — all `portions.test.ts` cases green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/portions.ts frontend/src/lib/portions.test.ts
git commit -m "feat(recipe): portion scaling + czech-plural format helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Frontend — `PortionStepper` component

**Files:**
- Create: `frontend/src/components/recipe/PortionStepper.tsx`
- Test: `frontend/src/components/recipe/PortionStepper.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/recipe/PortionStepper.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PortionStepper } from './PortionStepper';

describe('PortionStepper', () => {
  it('renders the count with the right Czech plural', () => {
    render(<PortionStepper value={5} onChange={() => {}} />);
    expect(screen.getByText(/5 porcí/)).toBeInTheDocument();
  });

  it('increments and decrements within bounds', async () => {
    const onChange = vi.fn();
    render(<PortionStepper value={4} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText('Více porcí'));
    expect(onChange).toHaveBeenLastCalledWith(5);
    await userEvent.click(screen.getByLabelText('Méně porcí'));
    expect(onChange).toHaveBeenLastCalledWith(3);
  });

  it('disables decrement at the minimum', () => {
    render(<PortionStepper value={1} onChange={() => {}} />);
    expect(screen.getByLabelText('Méně porcí')).toBeDisabled();
  });

  it('disables increment at the maximum', () => {
    render(<PortionStepper value={20} onChange={() => {}} />);
    expect(screen.getByLabelText('Více porcí')).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- PortionStepper`
Expected: FAIL — cannot resolve `./PortionStepper`.

- [ ] **Step 3: Implement `PortionStepper.tsx`**

Create `frontend/src/components/recipe/PortionStepper.tsx`:

```tsx
import { Users, Minus, Plus } from 'lucide-react';
import { czechPlural, PORTION_FORMS } from '@/lib/portions';

interface PortionStepperProps {
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
}

export const PortionStepper = ({ value, onChange, min = 1, max = 20 }: PortionStepperProps) => {
  const dec = () => onChange(Math.max(min, value - 1));
  const inc = () => onChange(Math.min(max, value + 1));
  const btn =
    'flex items-center justify-center w-7 h-7 rounded-lg bg-slate-700 border border-slate-600 ' +
    'text-zinc-200 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed';

  return (
    <div className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.15em] text-zinc-300">
      <button type="button" aria-label="Méně porcí" onClick={dec} disabled={value <= min} className={btn}>
        <Minus size={14} />
      </button>
      <span className="flex items-center gap-1.5 min-w-[68px] justify-center">
        <Users size={14} className="text-emerald-500" />
        {value} {czechPlural(value, PORTION_FORMS)}
      </span>
      <button type="button" aria-label="Více porcí" onClick={inc} disabled={value >= max} className={btn}>
        <Plus size={14} />
      </button>
    </div>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- PortionStepper`
Expected: PASS — all 4 cases green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/recipe/PortionStepper.tsx frontend/src/components/recipe/PortionStepper.test.tsx
git commit -m "feat(recipe): PortionStepper control

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Frontend — `RecipeIngredients` component (stepper + scaled list)

This component owns the portion state and renders the whole Ingredients card, so both pages stay DRY.

**Files:**
- Create: `frontend/src/components/recipe/RecipeIngredients.tsx`
- Test: `frontend/src/components/recipe/RecipeIngredients.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/recipe/RecipeIngredients.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RecipeIngredients } from './RecipeIngredients';

const ingredients = [
  { name: 'brambory', quantity: 600, unit: 'g' },
  { name: 'sůl', quantity: null, unit: null }, // to taste
];

describe('RecipeIngredients', () => {
  it('renders amounts at the base serving count by default', () => {
    render(<RecipeIngredients ingredients={ingredients} baseServings={4} />);
    expect(screen.getByText('— 600 g')).toBeInTheDocument();
    expect(screen.getByText('sůl')).toBeInTheDocument();
  });

  it('rescales amounts when portions change', async () => {
    render(<RecipeIngredients ingredients={ingredients} baseServings={4} />);
    await userEvent.click(screen.getByLabelText('Více porcí')); // 4 -> 5
    expect(screen.getByText('— 750 g')).toBeInTheDocument();
  });

  it('never shows an amount for a to-taste ingredient', async () => {
    render(<RecipeIngredients ingredients={ingredients} baseServings={4} />);
    await userEvent.click(screen.getByLabelText('Více porcí'));
    expect(screen.getByText('sůl')).toBeInTheDocument();
    expect(screen.queryByText(/sůl —/)).not.toBeInTheDocument();
  });

  it('defaults base servings to 1 when missing', () => {
    render(<RecipeIngredients ingredients={[{ name: 'rýže', quantity: 100, unit: 'g' }]} />);
    expect(screen.getByText('— 100 g')).toBeInTheDocument();
    expect(screen.getByText(/1 porce/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- RecipeIngredients`
Expected: FAIL — cannot resolve `./RecipeIngredients`.

- [ ] **Step 3: Implement `RecipeIngredients.tsx`**

Create `frontend/src/components/recipe/RecipeIngredients.tsx`:

```tsx
import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { formatScaledIngredient, type IngredientInput } from '@/lib/portions';
import { PortionStepper } from './PortionStepper';

interface RecipeIngredientsProps {
  ingredients: Array<IngredientInput | string>;
  baseServings?: number | null;
}

export const RecipeIngredients = ({ ingredients, baseServings }: RecipeIngredientsProps) => {
  const base = baseServings && baseServings > 0 ? baseServings : 1;
  const [portions, setPortions] = useState(base);

  return (
    <Card className="p-8 md:col-span-1 text-left h-fit md:sticky md:top-10">
      <div className="flex items-center justify-between gap-4 mb-6 pb-4 border-b border-slate-600">
        <h2 className="text-lg font-black text-white uppercase tracking-tighter italic">
          Ingredience
        </h2>
        <PortionStepper value={portions} onChange={setPortions} />
      </div>
      <ul className="space-y-3">
        {(ingredients || []).map((ing, idx) => {
          if (typeof ing === 'string') {
            return (
              <li key={idx} className="flex items-start gap-3 text-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
                <span className="text-zinc-300">{ing}</span>
              </li>
            );
          }
          const s = formatScaledIngredient(ing, base, portions);
          return (
            <li key={idx} className="flex items-start gap-3 text-sm">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
              <span className="text-zinc-300">
                <span className="font-bold text-white">{s.name}</span>
                {s.amountLabel && <span className="text-zinc-300 ml-1">— {s.amountLabel}</span>}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
};
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --prefix frontend run test -- RecipeIngredients`
Expected: PASS — all 4 cases green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/recipe/RecipeIngredients.tsx frontend/src/components/recipe/RecipeIngredients.test.tsx
git commit -m "feat(recipe): RecipeIngredients card with live portion scaling

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Frontend — wire `RecipeIngredients` into both recipe pages

Replace the hand-rolled Ingredients card in each page with `<RecipeIngredients>`, and drop the now-duplicate static servings badge from the meta row (the stepper owns the portion display). Leave the deals block and schema.org JSON-LD untouched.

**Files:**
- Modify: `frontend/src/pages/RecipePage.tsx`
- Modify: `frontend/src/pages/PublicRecipePage.tsx`

- [ ] **Step 1: Edit `RecipePage.tsx` — add import**

Add to the import block (after line 10, `import { getRecipeDeals } from '@/lib/pricing';`):
```tsx
import { RecipeIngredients } from '@/components/recipe/RecipeIngredients';
```

- [ ] **Step 2: Edit `RecipePage.tsx` — remove the static servings badge**

Delete the servings badge block (lines 142-146):
```tsx
            {recipe.servings && (
              <div className="flex items-center gap-2 bg-slate-700 border border-slate-600 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                <Users size={14} className="text-emerald-500" /> {recipe.servings} {recipe.servings > 1 ? 'porcí' : 'porce'}
              </div>
            )}
```

- [ ] **Step 3: Edit `RecipePage.tsx` — replace the Ingredients card**

Replace the entire Ingredients `<Card>...</Card>` block (lines 187-209, the comment `{/* Ingredients sidebar */}` through the closing `</Card>`) with:
```tsx
          {/* Ingredients sidebar */}
          <RecipeIngredients ingredients={recipe.ingredients || []} baseServings={recipe.servings} />
```

- [ ] **Step 4: Edit `RecipePage.tsx` — drop the now-unused `Users` import**

The lucide import on line 4 is:
```tsx
import { ArrowLeft, Clock, Users, ChefHat, Loader2 } from 'lucide-react';
```
`Users` is no longer used here (it now lives in `PortionStepper`). Change it to:
```tsx
import { ArrowLeft, Clock, ChefHat, Loader2 } from 'lucide-react';
```
(If a later grep shows `Users` is still referenced elsewhere in the file, leave it — but as of this plan it is only the deleted badge.)

- [ ] **Step 5: Apply the same four edits to `PublicRecipePage.tsx`**

- Add `import { RecipeIngredients } from '@/components/recipe/RecipeIngredients';` to its import block.
- Delete the servings badge block (lines 136-140 — identical markup to Step 2).
- Replace the Ingredients `<Card>...</Card>` block (lines 166-183) with:
```tsx
          <RecipeIngredients ingredients={recipe.ingredients || []} baseServings={recipe.servings} />
```
- Remove `Users` from its `lucide-react` import if now unused (check the file: `grep -n "Users" frontend/src/pages/PublicRecipePage.tsx` — if the only hit was the deleted badge, drop it from the import).

- [ ] **Step 6: Typecheck, lint, and run the full frontend test suite**

Run: `npm --prefix frontend run build`
Expected: `tsc` passes (no unused-import or type errors) and the Vite build succeeds.

Run: `npm --prefix frontend run lint`
Expected: 0 errors / 0 warnings (eslint runs with `--max-warnings 0`).

Run: `npm --prefix frontend run test`
Expected: all suites PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/RecipePage.tsx frontend/src/pages/PublicRecipePage.tsx
git commit -m "feat(recipe): live portion stepper on recipe + public recipe pages

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Full verification pass

- [ ] **Step 1: Backend test suite**

Run: `python manage.py test diet_planner.tests.test_recipe_retrieval diet_planner.tests.test_recipe_servings_creation -v 2`
Expected: all PASS.

- [ ] **Step 2: Frontend suite + build + lint**

Run: `npm --prefix frontend run test && npm --prefix frontend run lint && npm --prefix frontend run build`
Expected: all green.

- [ ] **Step 3: Manual smoke (optional but recommended)**

Start the dev stack, open a recipe with `base_servings > 1`, and confirm:
- The Ingredients card header shows the stepper at the recipe's base count.
- Clicking `+` / `−` rescales every quantitied ingredient; "to taste" items (e.g. `sůl`) stay name-only.
- The deals headline ("N z M surovin ve slevě") is unchanged by the stepper.
- The meta row no longer shows a separate static "N porcí" badge.

---

## Notes / Out of Scope

- No toprecepty.cz parser or new recipe source (scaling fidelity only).
- Absolute price display stays dormant; deals are portion-invariant and untouched.
- Portion selection is ephemeral (resets on reload) — no persistence.
- Old `Recipe` rows created before Task 2 keep `servings = 1`; they simply default the stepper to 1. New recipes get the truthful base. No backfill in scope.
