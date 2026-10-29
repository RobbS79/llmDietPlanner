import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PublicRecipePage } from './PublicRecipePage';
import { api } from '@/lib/api';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/pricing', () => ({ getRecipeDeals: () => null, getShoppingList: () => [] }));

const RECIPE = {
  name: 'Pečený losos s brokolicí a batáty', description: '', ingredients: [],
  instructions: ['Upečte.'], servings: 1, nutritional_info: {},
  food_category: 'ryba',
  image_url: '/static/food-images/dishes/peceny-losos-s-brokolici-a-bataty.webp',
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/recepty/12/peceny-losos-s-brokolici-a-bataty']}>
        <Routes>
          <Route path="/recepty/:id/:slug?" element={<PublicRecipePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const schema = () =>
  JSON.parse(document.getElementById('recipe-schema')?.textContent || 'null');

// Search Console 2026-10-29: Google renders JS and read THIS schema, which had
// no image -> "Missing field image" (critical) on every public recipe.
describe('PublicRecipePage Recipe JSON-LD', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.getElementById('recipe-schema')?.remove();
  });

  it('includes the hero image as an absolute URL', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { data: RECIPE } });
    renderPage();
    await waitFor(() => expect(schema()).not.toBeNull());
    expect(schema().image).toBe(
      `${window.location.origin}/static/food-images/dishes/peceny-losos-s-brokolici-a-bataty.webp`,
    );
  });

  it('falls back to the category image when the recipe has no image_url', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { data: { ...RECIPE, image_url: '' } } });
    renderPage();
    await waitFor(() => expect(schema()).not.toBeNull());
    expect(schema().image).toBe(`${window.location.origin}/static/food-images/ryba.webp`);
  });
});
