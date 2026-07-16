# Settings PR A — Shared Preferences Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the preference option-sets, the `Preferences` type, the multi-select toggle rule, and the prompt-building logic into one shared module (`frontend/src/lib/preferences.ts`), then refactor `Onboarding.tsx` and `CreatePlan.tsx` to consume it — with **zero behavior change**.

**Architecture:** Today the option ids (`goal`, `dietary_styles`, …) exist in two places: inline `const` arrays in `Onboarding.tsx` and implicit map keys in `CreatePlan.tsx`. This PR makes the module the single source of truth so the upcoming Settings page (PR B) can reuse them without a third copy. This PR is pure refactor: no new user-facing behavior, no backend change, no CSS/Tailwind class moves (only data/logic moves, so the "Tailwind drops unknown classes" risk does not apply here).

**Tech Stack:** React 18 + TypeScript (Vite), Vitest for unit tests.

**Why PR A first:** it touches the signup → onboarding → first-plan ad funnel. Shipping and QA'ing it in isolation keeps that regression risk away from the larger Settings build (PR B). See design spec `docs/superpowers/specs/2026-07-16-profile-settings-page-design.md` (Phasing).

---

## File Structure

- **Create** `frontend/src/lib/preferences.ts` — single source of truth: option arrays, `Preferences` type, `DEFAULT_PREFERENCES`, `toggleMultiValue()`, `buildPreferencesPrompt()`.
- **Create** `frontend/src/lib/preferences.test.ts` — unit tests locking the extracted logic to its current output.
- **Modify** `frontend/src/pages/Onboarding.tsx` — delete the inline arrays + `OnboardingData` interface; import from the module; route its `toggleMulti` through `toggleMultiValue`.
- **Modify** `frontend/src/pages/CreatePlan.tsx` — replace the inline prompt-map block (L46–64) with a `buildPreferencesPrompt()` call.

---

## Task 1: Create the shared preferences module (TDD)

**Files:**
- Create: `frontend/src/lib/preferences.ts`
- Test: `frontend/src/lib/preferences.test.ts`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/lib/preferences.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import {
  GOALS,
  DIETARY_STYLES,
  ALLERGIES,
  COOKING_SKILLS,
  COOKING_TIMES,
  DEFAULT_PREFERENCES,
  toggleMultiValue,
  buildPreferencesPrompt,
} from './preferences';

describe('option arrays', () => {
  it('expose the canonical ids (guards against accidental edits)', () => {
    expect(GOALS.map(o => o.id)).toEqual(['lose_weight', 'eat_healthy', 'save_money', 'save_time']);
    expect(DIETARY_STYLES.map(o => o.id)).toEqual(['none', 'vegetarian', 'vegan', 'gluten_free', 'keto', 'high_protein']);
    expect(ALLERGIES.map(o => o.id)).toEqual(['none', 'lactose', 'gluten', 'nuts', 'eggs', 'fish', 'soy']);
    expect(COOKING_SKILLS.map(o => o.id)).toEqual(['beginner', 'intermediate', 'advanced']);
    expect(COOKING_TIMES.map(o => o.id)).toEqual(['15min', '30min', '60min', 'unlimited']);
  });
});

describe('DEFAULT_PREFERENCES', () => {
  it('matches the onboarding initial state', () => {
    expect(DEFAULT_PREFERENCES).toEqual({
      goal: '',
      dietary_styles: [],
      allergies: [],
      household_size: 2,
      weekly_budget: 1500,
      cooking_skill: '',
      cooking_time: '',
      country: 'CZ',
      shop: 'ROHLIK',
    });
  });
});

describe('toggleMultiValue', () => {
  it('adds and removes a normal value', () => {
    expect(toggleMultiValue([], 'vegan')).toEqual(['vegan']);
    expect(toggleMultiValue(['vegan'], 'vegan')).toEqual([]);
  });
  it('selecting a normal value clears "none"', () => {
    expect(toggleMultiValue(['none'], 'vegan')).toEqual(['vegan']);
  });
  it('selecting "none" clears everything', () => {
    expect(toggleMultiValue(['vegan', 'keto'], 'none')).toEqual(['none']);
  });
  it('toggling "none" off when already set empties the list', () => {
    expect(toggleMultiValue(['none'], 'none')).toEqual([]);
  });
});

describe('buildPreferencesPrompt', () => {
  it('reproduces the CreatePlan prompt string exactly', () => {
    const { prompt, restrictions } = buildPreferencesPrompt({
      goal: 'lose_weight',
      dietary_styles: ['vegetarian', 'none'],
      allergies: ['lactose'],
      household_size: 2,
      weekly_budget: 1500,
      cooking_skill: 'beginner',
      cooking_time: '30min',
      country: 'CZ',
    });
    expect(prompt).toBe(
      'Chci zhubnout. vegetariánská strava. bez laktózy. Pro 2 osoby. Rozpočet 1500 CZK/týden. jednoduché recepty pro začátečníky. Max 30 minut na přípravu.'
    );
    expect(restrictions).toBe('bez laktózy');
  });
  it('omits unlimited cooking time and uses EUR for SK', () => {
    const { prompt } = buildPreferencesPrompt({
      goal: 'save_money',
      dietary_styles: ['none'],
      allergies: ['none'],
      household_size: 1,
      weekly_budget: 80,
      cooking_skill: 'advanced',
      cooking_time: 'unlimited',
      country: 'SK',
    });
    expect(prompt).toBe('Chci šetřit za jídlo. Pro 1 osobu. Rozpočet 80 EUR/týden. i složitější recepty.');
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/preferences.test.ts`
Expected: FAIL — `Failed to resolve import "./preferences"` (module does not exist yet).

- [ ] **Step 3: Write the module**

Create `frontend/src/lib/preferences.ts`:

```ts
// Single source of truth for onboarding/profile preference options and the
// derived meal-plan prompt. Consumed by Onboarding, CreatePlan, and (PR B) Settings.

export interface PreferenceOption {
  id: string;
  label: string;
  icon?: string;
  desc?: string;
}

export interface Preferences {
  goal: string;
  dietary_styles: string[];
  allergies: string[];
  household_size: number;
  weekly_budget: number;
  cooking_skill: string;
  cooking_time: string;
  country: string;
  shop: string;
}

export const GOALS: PreferenceOption[] = [
  { id: 'lose_weight', label: 'Chci zhubnout', icon: '🎯', desc: 'Snížit váhu zdravým způsobem' },
  { id: 'eat_healthy', label: 'Chci jíst zdravěji', icon: '🥗', desc: 'Vyvážená strava s nutričními hodnotami' },
  { id: 'save_money', label: 'Chci šetřit za jídlo', icon: '💰', desc: 'Levnější nákupy bez plýtvání' },
  { id: 'save_time', label: 'Chci šetřit čas', icon: '⏱️', desc: 'Rychlé recepty a hotový plán' },
];

export const DIETARY_STYLES: PreferenceOption[] = [
  { id: 'none', label: 'Bez omezení' },
  { id: 'vegetarian', label: 'Vegetarián' },
  { id: 'vegan', label: 'Vegan' },
  { id: 'gluten_free', label: 'Bezlepkové' },
  { id: 'keto', label: 'Keto / Low-carb' },
  { id: 'high_protein', label: 'Vysoko proteinové' },
];

export const ALLERGIES: PreferenceOption[] = [
  { id: 'none', label: 'Žádné alergie' },
  { id: 'lactose', label: 'Laktóza' },
  { id: 'gluten', label: 'Lepek' },
  { id: 'nuts', label: 'Ořechy' },
  { id: 'eggs', label: 'Vejce' },
  { id: 'fish', label: 'Ryby' },
  { id: 'soy', label: 'Sója' },
];

export const COOKING_SKILLS: PreferenceOption[] = [
  { id: 'beginner', label: 'Začátečník', desc: 'Jednoduché recepty, málo ingrediencí' },
  { id: 'intermediate', label: 'Pokročilý', desc: 'Středně náročné recepty' },
  { id: 'advanced', label: 'Zkušený kuchař', desc: 'Nebojím se i složitějších receptů' },
];

export const COOKING_TIMES: PreferenceOption[] = [
  { id: '15min', label: 'Do 15 min' },
  { id: '30min', label: 'Do 30 min' },
  { id: '60min', label: 'Do 60 min' },
  { id: 'unlimited', label: 'Čas nehraje roli' },
];

export const DEFAULT_PREFERENCES: Preferences = {
  goal: '',
  dietary_styles: [],
  allergies: [],
  household_size: 2,
  weekly_budget: 1500,
  cooking_skill: '',
  cooking_time: '',
  country: 'CZ',
  shop: 'ROHLIK',
};

// Multi-select rule with mutual exclusivity for the "none" sentinel.
// Extracted verbatim from Onboarding.toggleMulti.
export function toggleMultiValue(current: string[], id: string): string[] {
  if (id === 'none') return current.includes('none') ? [] : ['none'];
  const without = current.filter(v => v !== 'none');
  return without.includes(id) ? without.filter(v => v !== id) : [...without, id];
}

// Builds the Czech free-text prompt + dietary-restrictions string fed into
// plan generation. Extracted verbatim from CreatePlan's prefill effect.
export function buildPreferencesPrompt(
  prefs: Partial<Preferences>
): { prompt: string; restrictions: string } {
  const goalMap: Record<string, string> = { lose_weight: 'Chci zhubnout', eat_healthy: 'Chci jíst zdravěji', save_money: 'Chci šetřit za jídlo', save_time: 'Chci šetřit čas při vaření' };
  const styleMap: Record<string, string> = { vegetarian: 'vegetariánská strava', vegan: 'veganská strava', gluten_free: 'bezlepková dieta', keto: 'keto dieta', high_protein: 'vysoko proteinová strava' };
  const allergyMap: Record<string, string> = { lactose: 'bez laktózy', gluten: 'bez lepku', nuts: 'bez ořechů', eggs: 'bez vajec', fish: 'bez ryb', soy: 'bez sóji' };
  const skillMap: Record<string, string> = { beginner: 'jednoduché recepty pro začátečníky', intermediate: 'středně náročné recepty', advanced: 'i složitější recepty' };
  const timeMap: Record<string, string> = { '15min': 'Max 15 minut na přípravu', '30min': 'Max 30 minut na přípravu', '60min': 'Max 60 minut na přípravu' };

  const parts: string[] = [];
  if (prefs.goal) parts.push(goalMap[prefs.goal] || '');
  const styles = (prefs.dietary_styles || []).filter((s: string) => s !== 'none').map((s: string) => styleMap[s]).filter(Boolean);
  if (styles.length) parts.push(styles.join(', '));
  const allergies = (prefs.allergies || []).filter((a: string) => a !== 'none').map((a: string) => allergyMap[a]).filter(Boolean);
  if (allergies.length) parts.push(allergies.join(', '));
  if (prefs.household_size) parts.push(`Pro ${prefs.household_size} ${prefs.household_size === 1 ? 'osobu' : 'osoby'}`);
  if (prefs.weekly_budget) parts.push(`Rozpočet ${prefs.weekly_budget} ${prefs.country === 'SK' ? 'EUR' : 'CZK'}/týden`);
  if (prefs.cooking_skill) parts.push(skillMap[prefs.cooking_skill] || '');
  if (prefs.cooking_time && prefs.cooking_time !== 'unlimited') parts.push(timeMap[prefs.cooking_time] || '');

  const prompt = parts.filter(Boolean).join('. ') + '.';
  const restrictions = allergies.length > 0 ? allergies.join(', ') : '';
  return { prompt, restrictions };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/preferences.test.ts`
Expected: PASS (all describe blocks green).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/preferences.ts frontend/src/lib/preferences.test.ts
git commit -m "refactor(prefs): extract shared preferences module (options, toggle, prompt)"
```

---

## Task 2: Refactor Onboarding.tsx to consume the module

**Files:**
- Modify: `frontend/src/pages/Onboarding.tsx`

- [ ] **Step 1: Add the import**

In `frontend/src/pages/Onboarding.tsx`, add after the existing `import { trackQuizStarted } from '@/lib/analytics';` line:

```ts
import {
  GOALS,
  DIETARY_STYLES,
  ALLERGIES,
  COOKING_SKILLS,
  COOKING_TIMES,
  DEFAULT_PREFERENCES,
  toggleMultiValue,
  type Preferences,
} from '@/lib/preferences';
```

- [ ] **Step 2: Delete the now-duplicated inline declarations**

Delete these blocks (they now live in the module):
- `const GOALS = [ ... ];` (currently L18–23)
- `const DIETARY_STYLES = [ ... ];` (L25–32)
- `const ALLERGIES = [ ... ];` (L34–42)
- `const COOKING_SKILLS = [ ... ];` (L44–48)
- `const COOKING_TIMES = [ ... ];` (L50–55)
- `interface OnboardingData { ... }` (L57–67)

Keep the `STEPS` array (L10–16) — it is onboarding-only (labels + lucide icons) and is not part of the shared preference model.

- [ ] **Step 3: Point the state type + initial value at the module**

Replace the `useState<OnboardingData>({ ... })` initializer (currently L74–84) with:

```ts
  const [data, setData] = useState<Preferences>(DEFAULT_PREFERENCES);
```

Then update the two other `OnboardingData` references to `Preferences`:
- `saveMutation`'s `mutationFn` param type: `(payload: { onboarding_completed: boolean; dietary_preferences: Preferences })` (currently L94).
- `update`'s field type: `const update = (field: keyof Preferences, value: any) => ...` (currently L110).

- [ ] **Step 4: Route toggleMulti through the shared helper**

Replace the `toggleMulti` function (currently L112–119) with:

```ts
  const toggleMulti = (field: 'dietary_styles' | 'allergies', id: string) => {
    setData(prev => ({ ...prev, [field]: toggleMultiValue(prev[field], id) }));
  };
```

- [ ] **Step 5: Typecheck + existing tests**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: no type errors; all existing tests still PASS. (Use `tsc --noEmit`, not `npm run build` — the dev box OOMs on `vite build`; full build runs in the deploy pipeline.)

- [ ] **Step 6: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors/warnings (there must be no unused imports left behind — e.g. confirm `Check`/other lucide icons are still used).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/Onboarding.tsx
git commit -m "refactor(prefs): Onboarding consumes shared preferences module"
```

---

## Task 3: Refactor CreatePlan.tsx to consume buildPreferencesPrompt

**Files:**
- Modify: `frontend/src/pages/CreatePlan.tsx`

- [ ] **Step 1: Add the import**

In `frontend/src/pages/CreatePlan.tsx`, add after `import { ProtocolUpload } from '@/components/ProtocolUpload';`:

```ts
import { buildPreferencesPrompt } from '@/lib/preferences';
```

- [ ] **Step 2: Replace the inline prompt-map block**

Replace the body of the prefill `useEffect` — specifically the map declarations and part-building (currently L46–64, from `const goalMap` through the `const restrictions = ...` line) — so the effect reads:

```ts
  useEffect(() => {
    const prefs = (location.state as any)?.fromOnboarding || profile?.dietary_preferences;
    if (!prefs || Object.keys(prefs).length === 0) return;

    const { prompt, restrictions } = buildPreferencesPrompt(prefs);

    setFormData(prev => ({
      ...prev,
      prompt: prev.prompt || prompt,
      dietary_restrictions: prev.dietary_restrictions || restrictions,
      country: prefs.country || prev.country,
      language_code: prefs.country === 'SK' ? 'sk' : 'cs',
    }));
  }, [profile?.dietary_preferences, location.state]);
```

(The `setFormData` call and dependency array are unchanged — only the local map/parts logic is removed in favor of the shared call.)

- [ ] **Step 3: Typecheck + existing tests**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: no type errors; all tests PASS.

- [ ] **Step 4: Lint**

Run: `cd frontend && npm run lint`
Expected: no errors/warnings.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/CreatePlan.tsx
git commit -m "refactor(prefs): CreatePlan uses shared buildPreferencesPrompt"
```

---

## Task 4: Final verification & deploy gate

- [ ] **Step 1: Full unit-test + typecheck + lint sweep**

Run: `cd frontend && npx tsc --noEmit && npx vitest run && npm run lint`
Expected: type-clean, all tests PASS, lint clean.

- [ ] **Step 2: Confirm no leftover duplication**

Run: `cd frontend && grep -rn "const GOALS\|const DIETARY_STYLES\|const ALLERGIES\|interface OnboardingData\|const goalMap\|const styleMap" src/`
Expected: matches ONLY in `src/lib/preferences.ts` (the `*Map` consts) — no matches remaining in `Onboarding.tsx` or `CreatePlan.tsx`.

- [ ] **Step 3: Post-deploy prod QA (funnel-critical)**

After this PR is merged and deployed, run the `/qa-prod` skill and manually walk the funnel on prod (per the always-test-prod rule): sign up → complete the onboarding quiz (each step's selections register, "none" exclusivity works) → land on `/create` and confirm the prompt textarea is prefilled with the same Czech sentence the quiz answers imply → generate a plan. The generated prompt must read identically to pre-refactor behavior.

---

## Self-Review

- **Spec coverage:** This plan implements the "shared-enum refactor (PR A)" phase of the spec's Phasing section and the Section-1 dependency (`preferences.ts`). It does NOT touch backend, Settings page, or the other four sections — those are PR B, by design. No PR-A spec requirement is left unimplemented.
- **Placeholder scan:** No TBD/TODO/"handle edge cases" — every code step shows complete code; every run step shows the exact command + expected result.
- **Type consistency:** `Preferences`, `PreferenceOption`, `DEFAULT_PREFERENCES`, `toggleMultiValue`, `buildPreferencesPrompt` are named identically in the module (Task 1) and every consumer (Tasks 2–3). `toggleMultiValue(current, id)` signature matches its call sites. `buildPreferencesPrompt(prefs) → { prompt, restrictions }` matches the CreatePlan usage.
- **Behavior preservation guard:** the `buildPreferencesPrompt` test locks the exact output string; `tsc --noEmit` + existing tests + lint guard the two consumer refactors; prod QA (Task 4) is the funnel-level confirmation.
