import { describe, it, expect, vi, afterEach } from 'vitest';
import { api } from './api';
import { searchRecipes, dealBadge, formatDealDate } from './discover';

describe('discover client', () => {
  afterEach(() => vi.restoreAllMocks());

  it('posts the query and unwraps data', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({ data: { data: { recipes: [], understood: [], exact: true, fallback: false, medical_note: false, has_more: false } } } as never);
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
