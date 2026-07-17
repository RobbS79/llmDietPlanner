import { describe, it, expect, vi, beforeEach } from 'vitest';
import { replaceRecipe } from './replaceRecipe';
import { api } from './api';

vi.mock('./api', () => ({ api: { post: vi.fn() } }));

describe('replaceRecipe', () => {
  beforeEach(() => vi.clearAllMocks());

  it('POSTs the hint to the replace endpoint and returns the data payload', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { status: 'success', data: { replaced: true, hint_matched: null, recipe: { name: 'Guláš' } } },
    });
    const result = await replaceRecipe('12:1:lunch:0', 'něco s kuřecím');
    expect(api.post).toHaveBeenCalledWith('/recipes/12:1:lunch:0/replace/', { hint: 'něco s kuřecím' });
    expect(result.replaced).toBe(true);
    expect(result.hint_matched).toBeNull();
    expect(result.recipe?.name).toBe('Guláš');
  });

  it('surfaces replaced:false with a reason and no recipe', async () => {
    vi.mocked(api.post).mockResolvedValue({
      data: { status: 'success', data: { replaced: false, reason: 'no_alternatives' } },
    });
    const result = await replaceRecipe('12:1:lunch:0', '');
    expect(result.replaced).toBe(false);
    expect(result.reason).toBe('no_alternatives');
    expect(result.recipe).toBeUndefined();
  });
});
