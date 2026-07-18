import { describe, it, expect, vi, beforeEach } from 'vitest';
import { api } from '@/lib/api';
import { refinePreview, refineAccept } from './refineRecipe';

vi.mock('@/lib/api', () => ({ api: { post: vi.fn() } }));

describe('refineRecipe client', () => {
  beforeEach(() => vi.clearAllMocks());

  it('refinePreview posts messages + rejected ids and unwraps data', async () => {
    const payload = { candidate: null, question: null, hint_matched: false, reason: 'no_alternatives' };
    vi.mocked(api.post).mockResolvedValue({ data: { data: payload } });

    const messages = [{ role: 'user' as const, text: 'něco lehčího' }];
    const result = await refinePreview('12:1:lunch:0', messages, [7]);

    expect(api.post).toHaveBeenCalledWith('/recipes/12:1:lunch:0/refine/', {
      messages, rejected_ids: [7],
    });
    expect(result).toEqual(payload);
  });

  it('refineAccept posts the accept id and unwraps data', async () => {
    const payload = { replaced: true, recipe: { name: 'Guláš' } };
    vi.mocked(api.post).mockResolvedValue({ data: { data: payload } });

    const result = await refineAccept('12:1:lunch:0', 99);

    expect(api.post).toHaveBeenCalledWith('/recipes/12:1:lunch:0/refine/', { accept: 99 });
    expect(result).toEqual(payload);
  });
});
