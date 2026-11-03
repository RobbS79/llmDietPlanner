# Uvařto First Visit: Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the landing page into the product. A visitor asks "Co dnes uvařit?", sees real recipes in seconds, collects dishes into one shopping list with this week's deals, and signs up only to keep it. The week plan is the second path.

**Architecture:**
- A basket store in `lib/basket.ts` (localStorage) carries the visitor's picks across the Google round-trip and email verification.
- `lib/discover.ts` holds typed API calls for the backend plan's endpoints.
- New components live in `components/discover/`, `components/auth/SignupSheet.tsx` and `components/plan/PlanSheet.tsx`.
- `pages/Landing.tsx` is rewritten. `pages/ShoppingList.tsx` is new at `/nakup`, which is public.

Market Paper tokens stay. Touched pages use sentence case with no `uppercase`/`italic`/`font-black`/`tracking-widest` labels.

**Tech stack:** React 18, React Router, TanStack Query, axios (`lib/api.ts`), Tailwind with Market Paper tokens (`paper`, `ink`, `green`, `paprika`, `muted`, `kraft`), vitest + Testing Library.

**Depends on:** `docs/superpowers/plans/2026-11-03-uvarto-first-visit-backend.md` (endpoints `/api/discover/`, `/api/discover/recipe/<id>/`, `/api/deals/this-week/`, `/api/shopping-list/compose/`, `/api/shopping-lists/`, and plan-schema `pinned_recipe_ids`).

**Reference:** the clickable mockup https://claude.ai/artifact/YF3fvtdfDhsP3dqEGN7BBP shows the intended layout and copy. The strings below come from the copy deck in "ty" voice. Do not change them without the owner.

**How to run checks (all tasks):** `cd frontend && npx vitest run <file>` for one file, `npm run test` and `npx tsc --noEmit` before every commit. `npm run lint` fails repo-wide for pre-existing reasons, so lint only the files you touch: `npx eslint <files>`.

---

## File map

| File | Responsibility |
|---|---|
| Create `src/lib/basket.ts` | Picks, people and at-home marks in localStorage; `attachBasketAfterLogin()` |
| Create `src/lib/discover.ts` | Types + API calls for discover, sheet, deals, compose, saved lists |
| Modify `src/lib/analytics.ts` | `trackSearch`, `trackViewRecipe`, `trackAddToList`, `trackOpenList`, `trackPlanStarted` |
| Modify `src/lib/api.ts` | 402 `LIST_LIMIT` is not redirected to /pricing |
| Create `src/components/discover/RecipeCard.tsx` | Card with photo, time, kcal, deals badge and "Chci tohle" |
| Create `src/components/discover/RecipeSheet.tsx` | Recipe detail over the results |
| Create `src/components/discover/DealsStrip.tsx` | "Tento týden v akci" |
| Create `src/components/discover/BasketTray.tsx` | Sticky tray |
| Create `src/components/discover/TurnstileGate.tsx` | Bot check widget when the API asks for it |
| Create `src/components/auth/SignupSheet.tsx` | Keep-it signup sheet |
| Create `src/components/plan/PlanSheet.tsx` | Two-question week plan |
| Create `src/lib/planSheet.ts` | Maps sheet answers to pool counts |
| Rewrite `src/pages/Landing.tsx` | Search-first landing page |
| Create `src/pages/ShoppingList.tsx` | `/nakup` combined list + save + welcome |
| Modify `src/App.tsx`, `src/entry-server.tsx` | `/nakup` route, attach-after-login, no forced onboarding |
| Modify `src/pages/LoginSuccess.tsx` | Return to `/nakup` when a basket is waiting |
| Modify `src/pages/CreatePlan.tsx` | No country/city |
| Modify `prerender.mjs`, `llm_diet_planner_project/views.py` (landing meta only, if present) | New landing title and description |

---

### Task 1: Basket store

**Files:**
- Create: `frontend/src/lib/basket.ts`
- Test: `frontend/src/lib/basket.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/basket.test.ts
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readBasket, toggleRecipe, setPeople, toggleAtHome, clearBasket, attachBasketAfterLogin, BASKET_KEY } from './basket';
import { api } from './api';

describe('basket', () => {
  beforeEach(() => localStorage.clear());

  it('starts empty with 2 people', () => {
    expect(readBasket()).toEqual({ v: 1, recipeIds: [], people: 2, atHome: [], query: '' });
  });

  it('toggles recipes and caps at 12', () => {
    toggleRecipe(5);
    expect(readBasket().recipeIds).toEqual([5]);
    toggleRecipe(5);
    expect(readBasket().recipeIds).toEqual([]);
    for (let i = 0; i < 15; i++) toggleRecipe(i);
    expect(readBasket().recipeIds).toHaveLength(12);
  });

  it('clamps people to 1..6 and toggles at-home keys', () => {
    setPeople(9);
    expect(readBasket().people).toBe(6);
    toggleAtHome('garlic|ks');
    expect(readBasket().atHome).toEqual(['garlic|ks']);
  });

  it('survives corrupt storage', () => {
    localStorage.setItem(BASKET_KEY, '{nope');
    expect(readBasket().recipeIds).toEqual([]);
  });

  it('attaches a non-empty basket once after login, then clears it', async () => {
    toggleRecipe(7);
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { data: { id: 1 } } } as never);
    expect(await attachBasketAfterLogin()).toBe('saved');
    expect(post).toHaveBeenCalledWith('/shopping-lists/', { recipe_ids: [7], people: 2, at_home: [], query: '' });
    expect(readBasket().recipeIds).toEqual([]);
    expect(await attachBasketAfterLogin()).toBe('empty');
  });

  it('keeps the basket when the free limit is hit', async () => {
    toggleRecipe(7);
    vi.spyOn(api, 'post').mockRejectedValue({ response: { status: 402, data: { code: 'LIST_LIMIT' } } });
    expect(await attachBasketAfterLogin()).toBe('limit');
    expect(readBasket().recipeIds).toEqual([7]);
  });

  it('clearBasket empties it', () => {
    toggleRecipe(1);
    clearBasket();
    expect(readBasket().recipeIds).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/lib/basket.test.ts`
Expected: FAIL with `Cannot find module './basket'`.

- [ ] **Step 3: Implement**

```ts
// frontend/src/lib/basket.ts
// The visitor's picks before signup (spec 2026-11-03). Lives in localStorage so
// the Google round-trip and email verification never lose it.
import { api } from './api';

export const BASKET_KEY = 'uvarto.basket.v1';
export const MAX_RECIPES = 12;
export type Basket = { v: 1; recipeIds: number[]; people: number; atHome: string[]; query: string };

const EMPTY: Basket = { v: 1, recipeIds: [], people: 2, atHome: [], query: '' };
const listeners = new Set<() => void>();

export function readBasket(): Basket {
  try {
    const raw = JSON.parse(localStorage.getItem(BASKET_KEY) || 'null');
    if (raw && raw.v === 1 && Array.isArray(raw.recipeIds)) return { ...EMPTY, ...raw };
  } catch { /* corrupt or unavailable: start fresh */ }
  return { ...EMPTY };
}

function write(next: Basket): Basket {
  try { localStorage.setItem(BASKET_KEY, JSON.stringify(next)); } catch { /* private mode */ }
  listeners.forEach((fn) => fn());
  return next;
}

export function subscribeBasket(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function toggleRecipe(id: number): Basket {
  const b = readBasket();
  const has = b.recipeIds.includes(id);
  const recipeIds = has ? b.recipeIds.filter((x) => x !== id)
    : [...b.recipeIds, id].slice(-MAX_RECIPES);
  return write({ ...b, recipeIds });
}

export const setPeople = (n: number) => write({ ...readBasket(), people: Math.min(6, Math.max(1, Math.round(n))) });
export const setQuery = (query: string) => write({ ...readBasket(), query: query.slice(0, 300) });

export function toggleAtHome(key: string): Basket {
  const b = readBasket();
  const atHome = b.atHome.includes(key) ? b.atHome.filter((k) => k !== key) : [...b.atHome, key];
  return write({ ...b, atHome });
}

export const clearBasket = () => write({ ...EMPTY });

export type AttachResult = 'saved' | 'empty' | 'limit' | 'error';

export async function attachBasketAfterLogin(): Promise<AttachResult> {
  const b = readBasket();
  if (!b.recipeIds.length) return 'empty';
  try {
    await api.post('/shopping-lists/', { recipe_ids: b.recipeIds, people: b.people, at_home: b.atHome, query: b.query });
    clearBasket();
    return 'saved';
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { code?: string } } };
    if (e.response?.status === 402 && e.response.data?.code === 'LIST_LIMIT') return 'limit';
    return 'error';
  }
}
```

- [ ] **Step 4: Run it and confirm it passes**

Run: `npx vitest run src/lib/basket.test.ts`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/lib/basket.ts src/lib/basket.test.ts
git commit -m "feat(discover): localStorage basket that survives signup"
```

---

### Task 2: API client, 402 exception and analytics events

**Files:**
- Create: `frontend/src/lib/discover.ts`
- Modify: `frontend/src/lib/api.ts` (the `402` branch of the response interceptor)
- Modify: `frontend/src/lib/analytics.ts` (append exports at the end)
- Test: `frontend/src/lib/discover.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/discover.test.ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { api } from './api';
import { searchRecipes, dealBadge, formatDealDate } from './discover';

describe('discover client', () => {
  afterEach(() => vi.restoreAllMocks());

  it('posts the query and unwraps data', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { data: { recipes: [], understood: [], exact: true, fallback: false, has_more: false } } } as never);
    const out = await searchRecipes('kuřecí prsa', 0);
    expect(post).toHaveBeenCalledWith('/discover/', { q: 'kuřecí prsa', page: 0, turnstile_token: undefined });
    expect(out.exact).toBe(true);
  });

  it('builds the copy-deck deals badge', () => {
    expect(dealBadge([])).toBeNull();
    expect(dealBadge(['česnek'])).toBe('V akci: česnek');
    expect(dealBadge(['česnek', 'olivový'])).toBe('V akci: česnek, olivový');
    expect(dealBadge(['česnek', 'a', 'b'])).toBe('V akci: česnek a 2 další');
  });

  it('formats a Czech short date', () => {
    expect(formatDealDate('2026-11-04T05:59:59+00:00')).toBe('4. 11.');
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/lib/discover.test.ts`
Expected: FAIL with `Cannot find module './discover'`.

- [ ] **Step 3: Implement the client**

```ts
// frontend/src/lib/discover.ts
import { api } from './api';

export type DealItem = { canonical: string; shop: string; display_name: string; valid_until: string; ingredient?: string };
export type RecipeCardData = {
  id: number; slug: string; name: string; image_url: string; minutes: number | null; kcal: number | null;
  deals: { matched: number; total: number; names: string[]; items: DealItem[] };
};
export type RecipeSheetData = RecipeCardData & {
  macros: { protein: number; carbs: number; fat: number } | null;
  ingredients: { name: string; canonical: string; quantity: number | null; unit: string }[];
  steps: string[];
  source: { name: string; url: string };
};
export type DiscoverResult = { understood: string[]; exact: boolean; fallback: boolean; has_more: boolean; recipes: RecipeCardData[] };
export type WeekDeal = { canonical: string; name: string; shop: string; valid_until: string };
export type ListLine = { name: string; canonical: string; amount: number | null; unit: string; needed_by: number; recipe_ids: number[]; deal: DealItem | null };

export async function searchRecipes(q: string, page: number, turnstileToken?: string): Promise<DiscoverResult> {
  const res = await api.post('/discover/', { q, page, turnstile_token: turnstileToken });
  return res.data.data;
}
export const getRecipeSheet = async (id: number): Promise<RecipeSheetData> => (await api.get(`/discover/recipe/${id}/`)).data.data;
export const getWeekDeals = async (): Promise<WeekDeal[]> => (await api.get('/deals/this-week/')).data.data.deals;
export const composeList = async (recipeIds: number[], people: number): Promise<{ recipes: RecipeCardData[]; lines: ListLine[] }> =>
  (await api.post('/shopping-list/compose/', { recipe_ids: recipeIds, people })).data.data;

export function dealBadge(names: string[]): string | null {
  if (!names.length) return null;
  if (names.length === 1) return `V akci: ${names[0]}`;
  if (names.length === 2) return `V akci: ${names[0]}, ${names[1]}`;
  return `V akci: ${names[0]} a ${names.length - 1} další`;
}

export function formatDealDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()}. ${d.getUTCMonth() + 1}.`;
}

export function formatAmount(amount: number | null, unit: string): string {
  if (amount == null) return '';
  return `${String(amount).replace('.', ',')} ${unit}`.trim();
}
```

- [ ] **Step 4: Change the 402 branch in `src/lib/api.ts`**

Replace:

```ts
    if (error.response?.status === 402) {
```

with:

```ts
    // LIST_LIMIT is answered in place by a paywall sheet (spec 2026-11-03);
    // only the plan-generation 402 jumps to /pricing.
    if (error.response?.status === 402 && error.response?.data?.code !== 'LIST_LIMIT') {
```

- [ ] **Step 5: Add the analytics events at the end of `src/lib/analytics.ts`**

```ts
export const trackSearch = (q: string) => track('Search', { search_string: q.slice(0, 100) });
export const trackViewRecipe = (id: number) => track('ViewContent', { content_ids: [String(id)], content_type: 'product' });
export const trackAddToList = (id: number) => track('AddToCart', { content_ids: [String(id)], content_type: 'product' });
export const trackOpenList = (n: number) => track('InitiateCheckout', { num_items: n });
export const trackPlanStarted = () => track('Lead');
```

- [ ] **Step 6: Run the checks and confirm they pass**

Run: `npx vitest run src/lib/discover.test.ts src/lib/analytics.test.ts && npx tsc --noEmit`
Expected: all pass, no type errors.

- [ ] **Step 7: Commit**

```bash
git add src/lib/discover.ts src/lib/discover.test.ts src/lib/api.ts src/lib/analytics.ts
git commit -m "feat(discover): typed API client, list-limit 402 stays in place, funnel events"
```

---

### Task 3: Recipe card, deals strip and basket tray

**Files:**
- Create: `frontend/src/components/discover/RecipeCard.tsx`
- Create: `frontend/src/components/discover/DealsStrip.tsx`
- Create: `frontend/src/components/discover/BasketTray.tsx`
- Create: `frontend/src/lib/useBasket.ts`
- Test: `frontend/src/components/discover/RecipeCard.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/discover/RecipeCard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RecipeCard } from './RecipeCard';

const card = { id: 3, slug: 's', name: 'Losos s medovo-česnekovou omáčkou z hnědého másla', image_url: '/x.webp',
  minutes: 20, kcal: null, deals: { matched: 1, total: 6, names: ['česnek'], items: [] } };

describe('RecipeCard', () => {
  it('shows time, hides unknown kcal, shows the deals badge', () => {
    render(<RecipeCard recipe={card} picked={false} onToggle={() => {}} onOpen={() => {}} />);
    expect(screen.getByText('20 min')).toBeInTheDocument();
    expect(screen.queryByText(/kcal/)).toBeNull();
    expect(screen.getByText('V akci: česnek')).toBeInTheDocument();
  });

  it('toggles and opens', async () => {
    const onToggle = vi.fn(); const onOpen = vi.fn();
    render(<RecipeCard recipe={card} picked={false} onToggle={onToggle} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole('button', { name: 'Chci tohle' }));
    expect(onToggle).toHaveBeenCalledWith(3);
    await userEvent.click(screen.getByRole('button', { name: card.name }));
    expect(onOpen).toHaveBeenCalledWith(3);
  });

  it('says it is in the list when picked', () => {
    render(<RecipeCard recipe={card} picked onToggle={() => {}} onOpen={() => {}} />);
    expect(screen.getByRole('button', { name: 'V seznamu ✓' })).toHaveAttribute('aria-pressed', 'true');
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/components/discover/RecipeCard.test.tsx`
Expected: FAIL with `Cannot find module './RecipeCard'`.

- [ ] **Step 3: Implement**

```ts
// frontend/src/lib/useBasket.ts
import { useSyncExternalStore } from 'react';
import { readBasket, subscribeBasket, type Basket } from './basket';

let cache = readBasket();
const subscribe = (fn: () => void) => subscribeBasket(() => { cache = readBasket(); fn(); });
export const useBasket = (): Basket => useSyncExternalStore(subscribe, () => cache, () => cache);
```

```tsx
// frontend/src/components/discover/RecipeCard.tsx
import type { RecipeCardData } from '@/lib/discover';
import { dealBadge } from '@/lib/discover';

type Props = { recipe: RecipeCardData; picked: boolean; onToggle: (id: number) => void; onOpen: (id: number) => void };

export function RecipeCard({ recipe, picked, onToggle, onOpen }: Props) {
  const meta = [recipe.minutes ? `${recipe.minutes} min` : null, recipe.kcal ? `${recipe.kcal} kcal na porci` : null]
    .filter(Boolean).join(' · ');
  const badge = dealBadge(recipe.deals.names);
  return (
    <article className="flex flex-col overflow-hidden rounded-2xl border border-kraft bg-white">
      <button type="button" onClick={() => onOpen(recipe.id)} aria-hidden="true" tabIndex={-1} className="aspect-[4/3] bg-ink">
        <img src={recipe.image_url} alt="" loading="lazy" className="h-full w-full object-cover" />
      </button>
      <div className="flex flex-1 flex-col gap-1.5 p-3.5">
        <button type="button" onClick={() => onOpen(recipe.id)} className="text-left hover:underline">
          <h3 className="font-display text-lg font-bold leading-tight text-ink">{recipe.name}</h3>
        </button>
        {meta && <p className="text-sm text-muted tabular-nums">{meta}</p>}
        {badge && <span className="self-start rounded-md bg-yellow-300 px-2 py-0.5 text-sm font-semibold text-ink">{badge}</span>}
        <button type="button" aria-pressed={picked} onClick={() => onToggle(recipe.id)}
          className={`mt-auto rounded-xl border-2 border-green px-3 py-2 font-bold ${picked ? 'bg-green text-white' : 'text-green'}`}>
          {picked ? 'V seznamu ✓' : 'Chci tohle'}
        </button>
      </div>
    </article>
  );
}
```

```tsx
// frontend/src/components/discover/DealsStrip.tsx
import { useQuery } from '@tanstack/react-query';
import { getWeekDeals, formatDealDate, type WeekDeal } from '@/lib/discover';

const SEARCH_WORD: Record<string, string> = {
  garlic: 'česneku', potatoes: 'brambor', 'olive-oil': 'olivového oleje', lemons: 'citronů',
  parsley: 'petržele', ginger: 'zázvoru', carrots: 'mrkve', cream: 'smetany', 'sour-cream': 'smetany',
};

export const dealSearch = (d: WeekDeal) =>
  `Co uvařit z ${SEARCH_WORD[d.canonical] ?? d.name.split(' ').slice(0, 2).join(' ').toLowerCase()}`;

export function DealsStrip({ onPick }: { onPick: (q: string) => void }) {
  const { data } = useQuery({ queryKey: ['week-deals'], queryFn: getWeekDeals, staleTime: 30 * 60 * 1000 });
  if (!data?.length) return null;   // stale or empty: hide entirely, never "0 v akci"
  return (
    <section className="py-8" aria-labelledby="deals-h">
      <h2 id="deals-h" className="font-display text-3xl font-bold text-ink">Tento týden v akci</h2>
      <p className="mt-1 max-w-prose text-[15px] text-muted">Suroviny z letáků Tesca, Lidlu, Kauflandu, Albertu a Penny. Klikni a uvidíš, co z nich uvařit.</p>
      <div className="mt-3 flex gap-2.5 overflow-x-auto pb-2">
        {data.map((d) => (
          <button key={d.canonical} type="button" onClick={() => onPick(dealSearch(d))}
            className="min-w-[150px] flex-none rounded-xl bg-yellow-300 px-3.5 py-2.5 text-left">
            <b className="block text-[17px] text-ink">{d.name.split(' ').slice(0, 2).join(' ')}</b>
            <span className="text-[13px] text-ink">{d.shop} · do {formatDealDate(d.valid_until)}</span>
          </button>
        ))}
      </div>
      <p className="mt-1 text-xs text-muted">Podle letáků, které obchody zveřejnily. Ceny neuvádíme a akce se můžou v jednotlivých prodejnách lišit.</p>
    </section>
  );
}
```

```tsx
// frontend/src/components/discover/BasketTray.tsx
import { useNavigate } from 'react-router-dom';
import { useBasket } from '@/lib/useBasket';
import { trackOpenList } from '@/lib/analytics';

export const dishesWord = (n: number) => (n === 1 ? 'jídlo' : n < 5 ? 'jídla' : 'jídel');

export function BasketTray() {
  const { recipeIds } = useBasket();
  const navigate = useNavigate();
  if (!recipeIds.length) return null;
  return (
    <div className="sticky bottom-3 z-10 my-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-ink py-3 pl-5 pr-3 text-white">
      <span>{recipeIds.length} {dishesWord(recipeIds.length)} v seznamu</span>
      <button type="button" onClick={() => { trackOpenList(recipeIds.length); navigate('/nakup'); }}
        className="rounded-xl bg-yellow-300 px-4 py-2.5 font-bold text-ink">Nákupní seznam</button>
    </div>
  );
}
```

`bg-yellow-300` is a Tailwind default colour. Before committing, confirm that `tailwind.config.js` doesn't disable default colours (`grep -n "colors" frontend/tailwind.config.js`). If it replaces the palette, add `deal: '#F6D84A'` to the theme colours and use `bg-deal` everywhere instead. Memory note: Tailwind drops unknown classes silently, so after `npm run build`, grep the built CSS for the class.

- [ ] **Step 4: Run the checks and confirm they pass**

Run: `npx vitest run src/components/discover/RecipeCard.test.tsx && npx tsc --noEmit`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/components/discover src/lib/useBasket.ts
git commit -m "feat(discover): recipe card, deals strip, basket tray"
```

---

### Task 4: Recipe sheet

**Files:**
- Create: `frontend/src/components/discover/RecipeSheet.tsx`
- Test: `frontend/src/components/discover/RecipeSheet.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/discover/RecipeSheet.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/discover';
import { RecipeSheet } from './RecipeSheet';

const sheet = { id: 1, slug: 's', name: 'Kulajda', image_url: '/k.webp', minutes: 55, kcal: 584,
  deals: { matched: 1, total: 9, names: ['česnek'], items: [{ canonical: 'garlic', shop: 'Tesco', display_name: 'Česnek', valid_until: '2026-11-04T05:59:59+00:00' }] },
  macros: { protein: 18, carbs: 40, fat: 30 }, source: { name: 'Toprecepty.cz', url: 'https://t.cz' },
  ingredients: [{ name: 'česnek', canonical: 'garlic', quantity: 1, unit: 'stroužky' }],
  steps: ['a', 'b', 'c', 'd'] };

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe('RecipeSheet', () => {
  it('shows macros, source, deal line, first two steps', async () => {
    vi.spyOn(client, 'getRecipeSheet').mockResolvedValue(sheet);
    wrap(<RecipeSheet id={1} picked={false} onToggle={() => {}} onClose={() => {}} />);
    expect(await screen.findByText('Kulajda')).toBeInTheDocument();
    expect(screen.getByText(/B 18 g · S 40 g · T 30 g/)).toBeInTheDocument();
    expect(screen.getByText('Podle receptu z Toprecepty.cz')).toBeInTheDocument();
    expect(screen.getByText(/česnek \(Tesco do 4\. 11\.\)/)).toBeInTheDocument();
    expect(screen.getByText('… a dalších 2 kroků')).toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    vi.spyOn(client, 'getRecipeSheet').mockResolvedValue(sheet);
    const onClose = vi.fn();
    wrap(<RecipeSheet id={1} picked={false} onToggle={() => {}} onClose={onClose} />);
    await screen.findByText('Kulajda');
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/components/discover/RecipeSheet.test.tsx`
Expected: FAIL with `Cannot find module`.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/discover/RecipeSheet.tsx
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getRecipeSheet, formatAmount, formatDealDate } from '@/lib/discover';

type Props = { id: number; picked: boolean; onToggle: (id: number) => void; onClose: () => void };

export function RecipeSheet({ id, picked, onToggle, onClose }: Props) {
  const { data: r } = useQuery({ queryKey: ['recipe-sheet', id], queryFn: () => getRecipeSheet(id) });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const dealCanon = new Set(r?.deals.items.map((d) => d.canonical));
  return (
    <div role="dialog" aria-modal="true" aria-label={r?.name ?? 'Recept'}
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 sm:items-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="max-h-[92%] w-full max-w-[680px] overflow-auto rounded-t-3xl bg-paper pb-6 sm:rounded-3xl">
        {!r ? <p className="p-6 text-muted">Načítám recept…</p> : (
          <>
            <div className="aspect-video"><img src={r.image_url} alt="" className="h-full w-full object-cover" /></div>
            <div className="flex flex-col gap-4 px-5 pt-4">
              <div>
                <button type="button" onClick={onClose} aria-label="Zavřít" className="float-right h-9 w-9 rounded-full border border-kraft bg-white">✕</button>
                <h2 className="font-display text-3xl font-bold leading-tight text-ink">{r.name}</h2>
                <p className="mt-1 text-sm text-muted tabular-nums">
                  {[r.minutes && `${r.minutes} min`, r.kcal && `${r.kcal} kcal na porci`,
                    r.macros && `B ${r.macros.protein} g · S ${r.macros.carbs} g · T ${r.macros.fat} g`].filter(Boolean).join(' · ')}
                </p>
                {r.source.name && (
                  <a href={r.source.url} target="_blank" rel="noopener noreferrer" className="text-sm text-muted underline">
                    Podle receptu z {r.source.name}
                  </a>
                )}
              </div>
              {r.deals.items.length > 0 && (
                <p className="rounded-xl bg-yellow-100 px-3 py-2.5 text-[15px] text-ink">
                  <b>Tento týden v akci:</b>{' '}
                  {r.deals.items.map((d) => `${d.display_name.split(' ').slice(0, 2).join(' ').toLowerCase()} (${d.shop} do ${formatDealDate(d.valid_until)})`).join(', ')}
                </p>
              )}
              <div>
                <p className="font-display text-lg font-bold">Suroviny na 1 porci</p>
                <ul className="list-disc pl-5">
                  {r.ingredients.map((i) => (
                    <li key={i.name}>{i.name} <span className="text-sm text-muted">{formatAmount(i.quantity && Math.round(i.quantity * 10) / 10, i.unit)}</span>
                      {dealCanon.has(i.canonical) && <span className="ml-1 rounded bg-yellow-300 px-1.5 text-xs font-semibold">v akci</span>}</li>
                  ))}
                </ul>
              </div>
              {r.steps.length > 0 && (
                <div>
                  <p className="font-display text-lg font-bold">Postup</p>
                  <ol className="list-decimal pl-5">{r.steps.slice(0, 2).map((s) => <li key={s}>{s}</li>)}</ol>
                  {r.steps.length > 2 && <p className="text-sm text-muted">… a dalších {r.steps.length - 2} kroků</p>}
                </div>
              )}
              <button type="button" onClick={() => { onToggle(r.id); onClose(); }}
                className="w-full rounded-xl bg-green px-4 py-3.5 text-[17px] font-bold text-white">
                {picked ? 'V seznamu ✓' : 'Chci tohle'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run the checks and confirm they pass**

Run: `npx vitest run src/components/discover/RecipeSheet.test.tsx && npx tsc --noEmit`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/components/discover/RecipeSheet.tsx src/components/discover/RecipeSheet.test.tsx
git commit -m "feat(discover): recipe sheet over results"
```

---

### Task 5: Bot check widget

**Files:**
- Create: `frontend/src/components/discover/TurnstileGate.tsx`

It has no unit test because Cloudflare's script can't run in jsdom. It is covered by the e2e smoke in Task 10 and by prod QA.

- [ ] **Step 1: Implement**

```tsx
// frontend/src/components/discover/TurnstileGate.tsx
// Shown only when /api/discover/ answers 403 CHALLENGE_REQUIRED. Without a
// site key (VITE_TURNSTILE_SITE_KEY) the backend never asks, so this never renders.
import { useEffect, useRef } from 'react';

declare global { interface Window { turnstile?: { render: (el: HTMLElement, o: Record<string, unknown>) => string } } }
const SITE_KEY = import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined;

export function TurnstileGate({ onToken }: { onToken: (token: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!SITE_KEY || !box.current) return;
    const mount = () => window.turnstile?.render(box.current!, { sitekey: SITE_KEY, callback: onToken, language: 'cs' });
    if (window.turnstile) { mount(); return; }
    const s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js';
    s.async = true; s.onload = mount;
    document.head.appendChild(s);
  }, [onToken]);
  return (
    <div className="my-4 rounded-2xl border border-kraft bg-white p-4">
      <p className="mb-2 text-ink">Jen rychlé ověření, že nejsi robot.</p>
      <div ref={box} />
    </div>
  );
}
```

- [ ] **Step 2: Type check**

Run: `npx tsc --noEmit`
Expected: no errors. If `import.meta.env.VITE_TURNSTILE_SITE_KEY` errors, add `readonly VITE_TURNSTILE_SITE_KEY?: string` to `ImportMetaEnv` in `src/vite-env.d.ts`.

- [ ] **Step 3: Commit**

```bash
git add src/components/discover/TurnstileGate.tsx src/vite-env.d.ts
git commit -m "feat(discover): Turnstile widget when the API asks for it"
```

---

### Task 6: Landing page rewrite

**Files:**
- Rewrite: `frontend/src/pages/Landing.tsx`
- Test: `frontend/src/pages/Landing.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/Landing.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/discover';
import { readBasket } from '@/lib/basket';
import { Landing } from './Landing';

const card = (id: number, name: string) => ({ id, slug: String(id), name, image_url: '/x.webp', minutes: 20, kcal: 500,
  deals: { matched: 0, total: 3, names: [], items: [] } });

const renderLanding = () => render(
  <QueryClientProvider client={new QueryClient()}><MemoryRouter><Landing /></MemoryRouter></QueryClientProvider>);

describe('Landing', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.spyOn(client, 'getWeekDeals').mockResolvedValue([]);
  });

  it('asks the question and offers the plan path', () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue({ understood: [], exact: true, fallback: false, has_more: false, recipes: [] });
    renderLanding();
    expect(screen.getByRole('heading', { level: 1, name: 'Co dnes uvařit?' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Poskládej mi plán' })).toBeInTheDocument();
    expect(screen.queryByText(/300\+/)).toBeNull();
  });

  it('searches, shows what it understood, and adds to the basket', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue({ understood: ['kuřecí prsa'], exact: true, fallback: false, has_more: false,
      recipes: [card(1, 'Kuře s rýží'), card(2, 'Kuřecí parmigiana')] });
    renderLanding();
    await userEvent.type(screen.getByLabelText('Co chceš uvařit'), 'kuřecí prsa');
    await userEvent.click(screen.getByRole('button', { name: 'Najít recepty' }));
    expect(await screen.findByText('Kuře s rýží')).toBeInTheDocument();
    expect(screen.getByText('kuřecí prsa', { selector: 'span' })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: 'Chci tohle' })[0]);
    expect(readBasket().recipeIds).toEqual([1]);
    expect(screen.getByRole('button', { name: 'Nákupní seznam' })).toBeInTheDocument();
  });

  it('says so when nothing in the collection meets the restrictions', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue({ understood: ['bez masa'], exact: false, fallback: false, has_more: false, recipes: [] });
    renderLanding();
    await userEvent.click(screen.getByRole('button', { name: 'Bez masa' }));
    expect(await screen.findByText(/Na tohle jsme nic nenašli/)).toBeInTheDocument();
    expect(screen.queryByText(/hledal hodně/)).toBeNull();
  });

  it('is honest when nothing matched exactly', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue({ understood: ['kachna'], exact: false, fallback: false, has_more: false, recipes: [card(3, 'Guláš')] });
    renderLanding();
    await userEvent.click(screen.getByRole('button', { name: 'Bez masa' }));
    expect(await screen.findByText(/nic přesného nenašli/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/pages/Landing.test.tsx`
Expected: FAIL, because the current Landing has a different headline and no search box.

- [ ] **Step 3: Rewrite `src/pages/Landing.tsx`**

The file keeps the `captureAttribution(window.location.search)` effect and the `PublicHeader`. Everything else is replaced.

```tsx
// frontend/src/pages/Landing.tsx
// The landing page IS the product (spec 2026-11-03): ask, see real recipes,
// pick, get one shopping list. Copy: docs copy deck, informal "ty".
import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { RecipeCard } from '@/components/discover/RecipeCard';
import { RecipeSheet } from '@/components/discover/RecipeSheet';
import { DealsStrip } from '@/components/discover/DealsStrip';
import { BasketTray } from '@/components/discover/BasketTray';
import { TurnstileGate } from '@/components/discover/TurnstileGate';
import { PlanSheet } from '@/components/plan/PlanSheet';
import { captureAttribution, trackAddToList, trackSearch, trackViewRecipe } from '@/lib/analytics';
import { searchRecipes, type DiscoverResult } from '@/lib/discover';
import { setQuery, toggleRecipe } from '@/lib/basket';
import { useBasket } from '@/lib/useBasket';

export const EXAMPLES = ['Rychlá večeře do 30 minut', 'Co uvařit z mletého masa', 'Mám doma brambory a vajíčka',
  'Něco s kuřecím masem', 'Lehčí jídla na hubnutí', 'Bez masa'];

export const Landing = () => {
  const [params, setParams] = useSearchParams();
  const basket = useBasket();
  const [text, setText] = useState(params.get('q') ?? '');
  const [query, setQ] = useState(params.get('q') ?? '');
  const [page, setPage] = useState(0);
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [challenge, setChallenge] = useState(false);
  const [limited, setLimited] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const [planOpen, setPlanOpen] = useState(false);

  useEffect(() => { captureAttribution(window.location.search); }, []);

  const run = useCallback(async (q: string, p = 0, token?: string) => {
    setLoading(true); setChallenge(false); setLimited(false);
    try {
      const r = await searchRecipes(q, p, token);
      setResult(r); setQ(q); setPage(p); setQuery(q);
      if (p === 0) trackSearch(q);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { code?: string } } };
      if (e.response?.data?.code === 'CHALLENGE_REQUIRED') { setQ(q); setPage(p); setChallenge(true); }
      else if (e.response?.status === 429) { setResult(null); setLimited(true); }
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { const q = params.get('q'); if (q) run(q); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = (q: string) => { const t = q.trim(); if (!t) return; setText(t); setParams({ q: t }, { replace: true }); run(t); };
  const toggle = (id: number) => { if (!basket.recipeIds.includes(id)) trackAddToList(id); toggleRecipe(id); };
  const open = (id: number) => { trackViewRecipe(id); setOpenId(id); };

  return (
    <div className="min-h-screen bg-paper font-body text-ink">
      <a href="#main-content" className="skip-to-content">Přejít na obsah</a>
      <PublicHeader />
      <main id="main-content" className="mx-auto max-w-[1080px] px-5">
        <section className="max-w-3xl pb-2 pt-8 sm:pt-12">
          <h1 className="font-display text-5xl font-extrabold leading-none tracking-tight sm:text-7xl">Co dnes uvařit?</h1>
          {/* EN: Type what you feel like or what you have at home. You'll see recipes right away, plus what's on sale right now. */}
          <p className="mb-6 mt-4 max-w-prose text-xl text-muted">Napiš, na co máš chuť nebo co máš doma. Hned uvidíš recepty i to, co je zrovna v akci.</p>
          <form onSubmit={(e) => { e.preventDefault(); submit(text); }} className="flex gap-2 rounded-2xl border-2 border-ink bg-white p-1.5">
            <label htmlFor="discover-q" className="sr-only">Co chceš uvařit</label>
            <input id="discover-q" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" maxLength={300}
              placeholder="Třeba: něco rychlého z kuřecích prsou" className="min-w-0 flex-1 bg-transparent px-3 py-3 text-lg outline-none" />
            <button type="submit" className="whitespace-nowrap rounded-xl bg-green px-5 font-bold text-white">Najít recepty</button>
          </form>
          <div className="mt-3.5 flex flex-wrap gap-2">
            {EXAMPLES.map((c) => (
              <button key={c} type="button" onClick={() => submit(c)}
                className="rounded-full border border-kraft bg-white px-3.5 py-1.5 text-[15px] hover:border-ink">{c}</button>
            ))}
          </div>
          {/* EN: Want the whole week sorted? Put a plan together for me */}
          <p className="mt-4 text-muted">Chceš mít jasno na celý týden?{' '}
            <button type="button" onClick={() => setPlanOpen(true)} className="font-semibold text-green underline underline-offset-2">Poskládej mi plán</button></p>
        </section>

        {challenge && <TurnstileGate onToken={(t) => run(query, page, t)} />}

        {/* EN: You've searched a lot today. Try again tomorrow. */}
        {limited && <p className="py-6">Dnes už jsi hledal hodně. Zkus to zase zítra.</p>}

        {(loading || result) && (
          <section aria-live="polite" className="pt-6">
            {loading && <p className="text-muted">Hledám ve sbírce…</p>}
            {result && !loading && (
              <>
                <p className="flex flex-wrap items-center gap-2 text-[15px] text-muted">
                  {result.exact && result.understood.length > 0 && <>Hledám: {result.understood.map((u) => (
                    <span key={u} className="rounded-full bg-green/10 px-3 py-1 font-semibold text-green">{u}</span>))}</>}
                  {!result.understood.length && result.exact && 'Vybrali jsme pár oblíbených receptů. Zkus napsat surovinu, třeba „z cukety“.'}
                  {!result.exact && 'Na tohle jsme ve sbírce nic přesného nenašli. Tady je, co je nejblíž.'}
                </p>
                {result.recipes.length === 0
                  // EN: We couldn't find anything for that. Try writing it differently, e.g. a single ingredient: "from potatoes" or "with rice".
                  ? <p className="py-6">Na tohle jsme nic nenašli. Zkus to napsat jinak, třeba jednu surovinu: „z brambor“ nebo „s rýží“.</p>
                  : (
                    <div className="my-4 grid grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-5">
                      {result.recipes.map((r) => (
                        <RecipeCard key={r.id} recipe={r} picked={basket.recipeIds.includes(r.id)} onToggle={toggle} onOpen={open} />))}
                    </div>
                  )}
                {result.has_more && (
                  <button type="button" onClick={() => run(query, page + 1)} className="rounded-xl border border-kraft bg-white px-4 py-3 font-semibold">
                    Ukaž mi něco jiného</button>
                )}
              </>
            )}
          </section>
        )}

        <BasketTray />
        <DealsStrip onPick={submit} />
      </main>

      {openId !== null && <RecipeSheet id={openId} picked={basket.recipeIds.includes(openId)} onToggle={toggle} onClose={() => setOpenId(null)} />}
      {planOpen && <PlanSheet understood={result?.understood ?? []} prompt={query} onClose={() => setPlanOpen(false)} />}
    </div>
  );
};

export default Landing;
```

Note: `PlanSheet` arrives in Task 8. Until then, temporarily stub it in the import as `const PlanSheet = (_: object) => null;`, or do Task 8 before this step. **Recommended order: do Task 8 before Task 6.**

The "Z naší sbírky" row is dropped from v1 (YAGNI). The deals strip and the chips already give a zero-typing start.

- [ ] **Step 4: Run the checks and confirm they pass**

Run: `npx vitest run src/pages/Landing.test.tsx && npx tsc --noEmit`
Expected: 4 passed. Then run `npm run test` for the whole suite. If an old Landing test asserts the removed copy (`grep -rn "Landing" src --include=*.test.tsx`), delete those assertions. They tested the page this task replaces.

- [ ] **Step 5: Commit**

```bash
git add src/pages/Landing.tsx src/pages/Landing.test.tsx
git commit -m "feat(landing): search-first landing page; recipes before signup"
```

---

### Task 7: Signup sheet and return to the list

**Files:**
- Create: `frontend/src/components/auth/SignupSheet.tsx`
- Modify: `frontend/src/pages/LoginSuccess.tsx:18`
- Test: `frontend/src/components/auth/SignupSheet.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/auth/SignupSheet.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SignupSheet } from './SignupSheet';

describe('SignupSheet', () => {
  it('leads with Google and reassures', () => {
    render(<MemoryRouter><SignupSheet thumbs={['/a.webp']} onClose={() => {}} /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Pokračovat přes Google/ })).toBeInTheDocument();
    expect(screen.getByText('Zdarma, bez karty. První 2 plány máš u nás zadarmo.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nebo e-mailem' })).toHaveAttribute('href', '/login?mode=register&next=/nakup');
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/components/auth/SignupSheet.test.tsx`
Expected: FAIL with `Cannot find module`.

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/auth/SignupSheet.tsx
// Signup only at the moment of keeping (spec 2026-11-03). The basket is
// already in localStorage; LoginSuccess sends the user back to /nakup.
import { Link } from 'react-router-dom';

export const RETURN_KEY = 'uvarto.return.v1';

export function SignupSheet({ thumbs, onClose }: { thumbs: string[]; onClose: () => void }) {
  const google = () => {
    try { localStorage.setItem(RETURN_KEY, '/nakup'); } catch { /* ignore */ }
    window.location.href = `${import.meta.env.VITE_API_URL || ''}/api/auth/google/login/`;
  };
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="signup-h" className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 sm:items-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex w-full max-w-[480px] flex-col gap-4 rounded-t-3xl bg-paper p-6 sm:rounded-3xl">
        <h2 id="signup-h" className="font-display text-3xl font-bold">Uložit si to</h2>
        {/* EN: So your picked recipes and shopping list don't get lost. */}
        <p>Ať ti vybrané recepty a nákupní seznam neutečou.</p>
        {thumbs.length > 0 && (
          <div className="flex gap-2">{thumbs.slice(0, 6).map((t) => (
            <img key={t} src={t} alt="" className="h-14 w-14 rounded-xl object-cover" />))}</div>
        )}
        <button type="button" onClick={google} className="flex w-full items-center justify-center gap-2.5 rounded-xl border border-kraft bg-white p-3.5 font-bold">
          Pokračovat přes Google
        </button>
        <Link to="/login?mode=register&next=/nakup" className="self-center font-semibold text-green underline">Nebo e-mailem</Link>
        <p className="text-center text-xs text-muted">Zdarma, bez karty. První 2 plány máš u nás zadarmo.</p>
        <button type="button" onClick={onClose} className="self-center text-muted underline">Teď ne</button>
      </div>
    </div>
  );
}
```

In `src/pages/LoginSuccess.tsx`, replace line 18:

```tsx
      navigate(getPendingPromo() ? '/pricing' : '/', { replace: true });
```

with:

```tsx
      const back = localStorage.getItem('uvarto.return.v1');
      localStorage.removeItem('uvarto.return.v1');
      navigate(getPendingPromo() ? '/pricing' : (back === '/nakup' ? '/nakup?vitej=1' : '/'), { replace: true });
```

Check `src/pages/Login.tsx` for an existing `next` query handling (`grep -n "next" src/pages/Login.tsx`). If there is none, add it: after a successful email login, `navigate(params.get('next') === '/nakup' ? '/nakup?vitej=1' : '/')`. Only the literal `/nakup` is allowed, so the page can't be used as an open redirect. Also honour `mode=register` by opening the registration tab, if the page has tabs.

- [ ] **Step 4: Run the checks and confirm they pass**

Run: `npx vitest run src/components/auth/SignupSheet.test.tsx && npx tsc --noEmit`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/components/auth/SignupSheet.tsx src/components/auth/SignupSheet.test.tsx src/pages/LoginSuccess.tsx src/pages/Login.tsx
git commit -m "feat(auth): keep-it signup sheet; Google and email return to the list"
```

---

### Task 8: Week plan sheet

**Files:**
- Create: `frontend/src/lib/planSheet.ts`
- Create: `frontend/src/components/plan/PlanSheet.tsx`
- Test: `frontend/src/lib/planSheet.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/lib/planSheet.test.ts
import { describe, it, expect } from 'vitest';
import { countsFor, goalPrompt } from './planSheet';

describe('plan sheet mapping', () => {
  it('maps the count answer onto pool counts', () => {
    expect(countsFor('5 večeří')).toEqual({ breakfasts: 0, lunches: 0, dinners: 5, small_meals: 0, snacks: 0 });
    expect(countsFor('5 obědů a 5 večeří')).toEqual({ breakfasts: 0, lunches: 5, dinners: 5, small_meals: 0, snacks: 0 });
    expect(countsFor('Nastavím si sám')).toBeNull();
  });

  it('builds the prompt from the goal chip and the search', () => {
    expect(goalPrompt('Chci zhubnout', 'kuřecí prsa')).toBe('Chci zhubnout. kuřecí prsa');
    expect(goalPrompt(null, '')).toBe('Jen ať nemusím vymýšlet');
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/lib/planSheet.test.ts`
Expected: FAIL with `Cannot find module`.

- [ ] **Step 3: Implement the mapping**

```ts
// frontend/src/lib/planSheet.ts
export const GOALS = ['Chci zhubnout', 'Vařím dopředu do krabiček', 'Vařím pro rodinu', 'Jen ať nemusím vymýšlet'] as const;
export const COUNT_OPTIONS = ['5 večeří', '5 obědů a 5 večeří', 'Nastavím si sám'] as const;
type Counts = { breakfasts: number; lunches: number; dinners: number; small_meals: number; snacks: number };
const ZERO: Counts = { breakfasts: 0, lunches: 0, dinners: 0, small_meals: 0, snacks: 0 };

export function countsFor(answer: string): Counts | null {
  if (answer === '5 večeří') return { ...ZERO, dinners: 5 };
  if (answer === '5 obědů a 5 večeří') return { ...ZERO, lunches: 5, dinners: 5 };
  return null;
}

export function goalPrompt(goal: string | null, search: string): string {
  return [goal, search.trim()].filter(Boolean).join('. ') || 'Jen ať nemusím vymýšlet';
}
```

- [ ] **Step 4: Implement the sheet**

```tsx
// frontend/src/components/plan/PlanSheet.tsx
// Two questions instead of country, city and five steppers (spec 2026-11-03).
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '@/lib/api';
import { isAccessTokenValid } from '@/lib/auth';
import { readBasket } from '@/lib/basket';
import { trackPlanStarted } from '@/lib/analytics';
import { COUNT_OPTIONS, GOALS, countsFor, goalPrompt } from '@/lib/planSheet';
import { SignupSheet } from '@/components/auth/SignupSheet';

type Props = { understood: string[]; prompt: string; onClose: () => void };

export function PlanSheet({ understood, prompt, onClose }: Props) {
  const navigate = useNavigate();
  const [goal, setGoal] = useState<string | null>(null);
  const [count, setCount] = useState<string>('5 večeří');
  const [busy, setBusy] = useState(false);
  const [needSignup, setNeedSignup] = useState(false);
  const signedIn = isAccessTokenValid() || !!localStorage.getItem('refresh_token');

  const build = async () => {
    const counts = countsFor(count);
    const text = goalPrompt(goal, prompt);
    if (!counts) { navigate(`/create?prompt=${encodeURIComponent(text)}`); return; }
    if (!signedIn) { setNeedSignup(true); return; }
    setBusy(true);
    trackPlanStarted();
    try {
      const res = await api.post('/goals/', { prompt: text, ...counts, pinned_recipe_ids: readBasket().recipeIds });
      navigate(`/plan/${res.data.data.goal_id ?? res.data.data.id}`);
    } finally { setBusy(false); }
  };

  if (needSignup) return <SignupSheet thumbs={[]} onClose={onClose} />;
  const chip = (value: string, on: boolean, set: () => void) => (
    <button key={value} type="button" aria-pressed={on} onClick={set}
      className={`rounded-xl border px-3.5 py-2.5 ${on ? 'border-2 border-green bg-green/10 font-semibold' : 'border-kraft bg-white'}`}>{value}</button>
  );
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="plan-h" className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 sm:items-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="flex w-full max-w-[600px] flex-col gap-4 rounded-t-3xl bg-paper p-6 sm:rounded-3xl">
        <h2 id="plan-h" className="font-display text-3xl font-bold">Plán na celý týden</h2>
        {readBasket().recipeIds.length > 0 && <p>Tvoje vybraná jídla v plánu zůstanou.</p>}
        <p className="font-display text-lg font-bold">O co ti jde?</p>
        <div className="flex flex-wrap gap-2">{GOALS.map((g) => chip(g, goal === g, () => setGoal(goal === g ? null : g)))}</div>
        <p className="font-display text-lg font-bold">Kolik jídel chceš mít připravených?</p>
        <div className="flex flex-wrap gap-2">{COUNT_OPTIONS.map((c) => chip(c, count === c, () => setCount(c)))}</div>
        {understood.length > 0 && <p className="text-sm text-muted">Z hledání si bereme: {understood.join(', ')}</p>}
        <button type="button" disabled={busy} onClick={build} className="w-full rounded-xl bg-green p-3.5 text-[17px] font-bold text-white disabled:opacity-60">
          Sestavit můj plán</button>
        {/* EN: Collection recipes are instant. What we don't have, Uvařto writes, which takes a few minutes. Uses 1 of your 2 free plans. */}
        <p className="text-xs text-muted">Recepty ze sbírky jsou hned. Co ve sbírce nemáme, Uvařto dopíše, to trvá pár minut. Spotřebuje se 1 ze 2 plánů zdarma.</p>
      </div>
    </div>
  );
}
```

Check the goal-create response shape: `DietaryGoalCreateView` returns `data.goal_id` for drafts. Read the final-synthesis success `Response` in `diet_planner/views.py` (`grep -n "goal_id\|\"id\"" diet_planner/views.py | head`) and keep whichever key it returns. The `??` above covers both. Also check that `isAccessTokenValid` is exported from `src/lib/auth.ts`. `App.tsx` already imports it.

- [ ] **Step 5: Run the checks and confirm they pass**

Run: `npx vitest run src/lib/planSheet.test.ts && npx tsc --noEmit`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add src/lib/planSheet.ts src/lib/planSheet.test.ts src/components/plan/PlanSheet.tsx
git commit -m "feat(plan): two-question week plan sheet with picked dishes pinned"
```

---

### Task 9: Shopping list page, routes, no forced onboarding, simpler CreatePlan

**Files:**
- Create: `frontend/src/pages/ShoppingList.tsx`
- Test: `frontend/src/pages/ShoppingList.test.tsx`
- Modify: `frontend/src/App.tsx` (route list near line 88; `AuthenticatedHome` line 63)
- Modify: `frontend/src/entry-server.tsx` (route list near line 30)
- Modify: `frontend/src/pages/CreatePlan.tsx` (lines 46-47, 111, 205-240 country/city block)

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/ShoppingList.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/discover';
import { toggleRecipe, readBasket } from '@/lib/basket';
import { ShoppingList } from './ShoppingList';

const lines = [
  { name: 'česnek', canonical: 'garlic', amount: 3, unit: 'stroužky', needed_by: 2, recipe_ids: [1, 2],
    deal: { canonical: 'garlic', shop: 'Tesco', display_name: 'Česnek', valid_until: '2026-11-04T05:59:59+00:00' } },
  { name: 'rýže', canonical: 'rice', amount: 200, unit: 'g', needed_by: 1, recipe_ids: [1], deal: null },
];

const renderPage = (path = '/nakup') => render(
  <QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><ShoppingList /></MemoryRouter></QueryClientProvider>);

describe('ShoppingList', () => {
  beforeEach(() => { localStorage.clear(); toggleRecipe(1); toggleRecipe(2); });

  it('puts deals first and marks what I have at home', async () => {
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Nákup na 2 jídla' })).toBeInTheDocument();
    expect(screen.getByText('Tento týden v akci')).toBeInTheDocument();
    expect(screen.getByText(/V akci: Tesco, do 4\. 11\./)).toBeInTheDocument();
    expect(screen.getByText(/do 2 jídel/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole('button', { name: 'mám doma' })[0]);
    expect(readBasket().atHome).toEqual(['garlic|stroužky']);
  });

  it('opens the signup sheet when an anonymous visitor saves', async () => {
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Uložit si to' }));
    expect(screen.getByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/pages/ShoppingList.test.tsx`
Expected: FAIL with `Cannot find module`.

- [ ] **Step 3: Implement the page**

```tsx
// frontend/src/pages/ShoppingList.tsx
// /nakup: one list for the picked dishes, anonymous until "Uložit si to".
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { SignupSheet } from '@/components/auth/SignupSheet';
import { PlanSheet } from '@/components/plan/PlanSheet';
import { dishesWord } from '@/components/discover/BasketTray';
import { composeList, formatAmount, formatDealDate, type ListLine } from '@/lib/discover';
import { attachBasketAfterLogin, setPeople, toggleAtHome, type AttachResult } from '@/lib/basket';
import { useBasket } from '@/lib/useBasket';
import { isAccessTokenValid } from '@/lib/auth';

export function ShoppingList() {
  const basket = useBasket();
  const [params] = useSearchParams();
  const [signup, setSignup] = useState(false);
  const [plan, setPlan] = useState(false);
  const [saved, setSaved] = useState<AttachResult | null>(null);
  const signedIn = isAccessTokenValid() || !!localStorage.getItem('refresh_token');
  const ids = basket.recipeIds;
  const { data } = useQuery({ queryKey: ['compose', ids, basket.people], queryFn: () => composeList(ids, basket.people), enabled: ids.length > 0 });

  useEffect(() => { if (signedIn && params.get('vitej') === '1') attachBasketAfterLogin().then(setSaved); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async () => { if (!signedIn) { setSignup(true); return; } setSaved(await attachBasketAfterLogin()); };
  const key = (l: ListLine) => `${l.canonical}|${l.unit}`;
  const row = (l: ListLine) => {
    const home = basket.atHome.includes(key(l));
    return (
      <div key={key(l)} className={`grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-kraft py-2.5 ${home ? 'opacity-45' : ''}`}>
        <input type="checkbox" id={`l-${key(l)}`} className="h-5 w-5 accent-green" />
        <label htmlFor={`l-${key(l)}`}>
          <span className={home ? 'line-through' : ''}>{l.name}</span>{' '}
          <span className="text-sm text-muted">{formatAmount(l.amount, l.unit)}</span>
          <small className="block text-[13px] text-muted">
            {l.deal ? `V akci: ${l.deal.shop}, do ${formatDealDate(l.deal.valid_until)}` : ''}
            {l.deal && l.needed_by > 1 ? ' · ' : ''}{l.needed_by > 1 ? `do ${l.needed_by} jídel` : ''}
          </small>
        </label>
        <button type="button" onClick={() => toggleAtHome(key(l))} className="rounded-full border border-kraft px-2.5 py-1 text-[13px]">mám doma</button>
      </div>
    );
  };
  const lines = data?.lines ?? [];
  const deals = lines.filter((l) => l.deal);
  const rest = lines.filter((l) => !l.deal);

  return (
    <div className="min-h-screen bg-paper font-body text-ink">
      <PublicHeader />
      <main className="mx-auto max-w-[760px] px-5 pb-16">
        <Link to="/" className="font-semibold text-green underline">← Zpět k receptům</Link>
        {saved === 'saved' && (
          <div className="mt-4 rounded-2xl border border-kraft bg-white p-4">
            {/* EN: Hi, welcome to Uvařto. Your picked recipes are saved. Want to put a whole week together around them? */}
            <p className="font-display text-2xl font-bold">Ahoj, vítej v Uvařto.</p>
            <p className="mt-1">Tvoje vybrané recepty jsou uložené. Chceš k nim dát dohromady celý týden?</p>
            <button type="button" onClick={() => setPlan(true)} className="mt-3 rounded-xl bg-green px-4 py-2.5 font-bold text-white">Jo, poskládej mi týden</button>
          </div>
        )}
        {saved === 'limit' && (
          <div className="mt-4 rounded-2xl border border-kraft bg-white p-4">
            <p>Tento měsíc máš 3 seznamy za sebou. S předplatným bez omezení.</p>
            <Link to="/pricing" className="mt-2 inline-block font-semibold text-green underline">Podívat se na předplatné</Link>
          </div>
        )}
        <h1 className="mt-3 font-display text-4xl font-bold">Nákup na {ids.length} {dishesWord(ids.length)}</h1>
        {ids.length === 0 ? <p className="mt-4">Zatím tu nic není. <Link to="/" className="text-green underline">Najdi si recepty</Link>.</p> : (
          <>
            <div className="mt-3 flex items-center gap-3">
              <span>Pro kolik lidí</span>
              <button type="button" aria-label="Méně lidí" onClick={() => setPeople(basket.people - 1)} className="h-9 w-9 rounded-full border border-kraft bg-white">−</button>
              <span className="w-6 text-center tabular-nums" aria-live="polite">{basket.people}</span>
              <button type="button" aria-label="Více lidí" onClick={() => setPeople(basket.people + 1)} className="h-9 w-9 rounded-full border border-kraft bg-white">+</button>
            </div>
            <p className="mt-2 text-[15px] text-muted">Co máš doma, odškrtni tlačítkem „mám doma“.</p>
            {deals.length > 0 && <><h2 className="mt-5 text-[15px] font-semibold text-muted">Tento týden v akci</h2>{deals.map(row)}</>}
            <h2 className="mt-5 text-[15px] font-semibold text-muted">Ostatní</h2>{rest.map(row)}
            <div className="mt-6 grid max-w-[460px] gap-2.5">
              {saved !== 'saved' && <button type="button" onClick={save} className="rounded-xl bg-green p-3.5 text-[17px] font-bold text-white">Uložit si to</button>}
              <button type="button" onClick={() => setPlan(true)} className="rounded-xl border border-kraft bg-white p-3 font-semibold">Udělat z toho celý týden</button>
            </div>
          </>
        )}
      </main>
      {signup && <SignupSheet thumbs={(data?.recipes ?? []).map((r) => r.image_url)} onClose={() => setSignup(false)} />}
      {plan && <PlanSheet understood={[]} prompt={basket.query} onClose={() => setPlan(false)} />}
    </div>
  );
}

export default ShoppingList;
```

- [ ] **Step 4: Routes and onboarding**

In `src/App.tsx`:
- Import `ShoppingList` with the same import style as `RecipeIndexPage`.
- Add `<Route path="/nakup" element={<ShoppingList />} />` after the `/recepty/:id/:slug` route.
- Delete this line in `AuthenticatedHome`:

```tsx
  if (profile && !profile.onboarding_completed) return <Navigate to="/onboarding" replace />;
```

Remove the `Navigate` import if nothing else uses it (`tsc` will tell you).

In `src/entry-server.tsx`, add the same `/nakup` route and import. Memory note: any new public page must be registered in BOTH files, or it prerenders as an empty shell.

- [ ] **Step 5: CreatePlan without country and city**

In `src/pages/CreatePlan.tsx`:
- Line 111: change `return formData.prompt.trim().length > 0 && formData.city.trim().length > 0;` to `return formData.prompt.trim().length > 0;`.
- Delete the JSX block that renders the "Země" and "Město" fields (the two `<label>`s near lines 210 and 225, with their inputs and the wrapping grid).
- Read an initial `prompt` from the URL, used by PlanSheet's "Nastavím si sám". In the existing `useState` initialiser for `formData`, set `prompt: new URLSearchParams(window.location.search).get('prompt') ?? ''`.
- Leave `country: 'CZ'` and `city: ''` in the state; the backend now defaults both.

Run `npx vitest run src/pages` and `grep -rn "Město\|Země" src/pages/CreatePlan*` to confirm nothing still renders them.

- [ ] **Step 6: Run the checks and confirm they pass**

Run: `npx vitest run src/pages/ShoppingList.test.tsx && npm run test && npx tsc --noEmit`
Expected: all pass. Any existing test that asserts the onboarding redirect or the city field must be updated to the new behaviour (no redirect, no city field), with a comment citing spec 2026-11-03.

- [ ] **Step 7: Commit**

```bash
git add src/pages/ShoppingList.tsx src/pages/ShoppingList.test.tsx src/App.tsx src/entry-server.tsx src/pages/CreatePlan.tsx
git commit -m "feat(list): /nakup combined list; no forced onboarding; plan form without city"
```

---

### Task 10: Landing meta, e2e smoke and build check

**Files:**
- Modify: `frontend/prerender.mjs` (the `/` route entry, lines 23-29)
- Modify: `llm_diet_planner_project/views.py`, only if it holds landing meta (`grep -n "Jídelníček na míru" llm_diet_planner_project/views.py frontend/index.html`)
- Modify: `frontend/index.html` (`<title>`, `og:title`, `twitter:title`, description)
- Modify: `e2e/tests/smoke.spec.ts`

- [ ] **Step 1: New landing meta**

In `prerender.mjs`, replace the `/` entry's `title`, `description` and EN comment with:

```js
    title: 'Co dnes uvařit? Recepty a co je v akci | Uvařto',
    // EN: Type what you feel like or what you have at home. You'll see recipes right away, with a shopping list and which ingredients are on sale this week.
    description: 'Napiš, na co máš chuť nebo co máš doma. Hned uvidíš recepty, nákupní seznam a které suroviny jsou tento týden v akci.',
```

Apply the same title and description to `frontend/index.html`: `<title>`, `og:title`, `twitter:title`, plus `meta name="description"` / `og:description` if present. Do the same for any landing meta in the Django SSR view found by the grep.

- [ ] **Step 2: e2e smoke**

In `e2e/tests/smoke.spec.ts`, replace the wordmark assertion block (lines 18-19) with:

```ts
    // Brand wordmark: "uvařto." and the search-first hero (spec 2026-11-03)
    await expect(page.getByText(/uvařto/i).first()).toBeVisible();
    await expect(page.getByRole('heading', { level: 1, name: 'Co dnes uvařit?' })).toBeVisible();
    await expect(page.getByLabel('Co chceš uvařit')).toBeVisible();
```

- [ ] **Step 3: Build and verify the Tailwind classes made it in**

Run: `cd frontend && npm run build` (on the 2 GB dev droplet this can run out of memory; if it does, let CI build it and verify on the PR).
Then run: `grep -o "bg-yellow-300\|bg-green\\\\/10\|opacity-45" dist/assets/*.css | sort -u`.
Expected: each class is found. Any missing class means Tailwind dropped it. Swap `opacity-45` for `opacity-50` if needed, and recheck.

- [ ] **Step 4: Full frontend gate**

Run: `npm run test && npx tsc --noEmit && npx eslint src/lib/basket.ts src/lib/discover.ts src/lib/planSheet.ts src/lib/useBasket.ts src/components/discover src/components/auth/SignupSheet.tsx src/components/plan/PlanSheet.tsx src/pages/Landing.tsx src/pages/ShoppingList.tsx`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/prerender.mjs frontend/index.html e2e/tests/smoke.spec.ts llm_diet_planner_project/views.py
git commit -m "feat(seo): search-first landing meta; smoke covers the new hero"
```

---

## After both plans

1. Open one PR `feat/uvarto-launch` → `develop` (rename + backend + frontend). CI must be green.
2. Owner sets the DO env: `CACHE_URL` (the existing Redis URL, ideally a separate db index such as `/1`), `DISCOVER_DAILY_LLM_BUDGET`, `TURNSTILE_SITE_KEY` (also as `VITE_TURNSTILE_SITE_KEY` at build) and `TURNSTILE_SECRET_KEY`.
3. Deploy (the owner runs the prod push). After it is ACTIVE, the owner runs the `recategorize_recipe_images` dry run, reviews it, then runs `--apply`.
4. Run `/qa-prod` with the 28 real-demand prompts as the search set. On mobile, check: chip → add 2 → list → Google signup → saved welcome → "5 večeří" plan.
