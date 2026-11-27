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
