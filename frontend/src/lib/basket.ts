// frontend/src/lib/basket.ts
// The visitor's picks before signup (spec 2026-11-03). Lives in localStorage so
// the Google round-trip and email verification never lose it.
import { api } from './api';
import { BASKET_KEY } from './storageKeys';

export { BASKET_KEY };
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
