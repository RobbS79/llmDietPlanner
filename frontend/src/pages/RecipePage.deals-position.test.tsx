import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/ui/Toast';
import { RecipePage } from './RecipePage';
import { api } from '@/lib/api';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/refineRecipe', () => ({ refinePreview: vi.fn(), refineAccept: vi.fn() }));
vi.mock('@/lib/pricing', () => ({
  getRecipeDeals: (r: any) => (r?.deals && r.deals.matched > 0 ? r.deals : null),
  getShoppingList: () => null,
}));
vi.mock('@/lib/food-image', () => ({ getFoodImageUrl: () => '' }));

const MEAL_ID = '12:1:lunch:0';
const RECIPE = {
  name: 'Kuře s rýží', description: '', ingredients: [],
  instructions: ['Uvař.'], servings: 1, nutritional_info: {}, source_url: '',
  deals: {
    matched: 2,
    total: 5,
    deals: [
      { canonical: 'mleko', display_name: 'Mléko', shop: 'Lidl', source_url: 'https://example.test/mleko' },
    ],
  },
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/plan/12/recept/${MEAL_ID}`]}>
          <Routes>
            <Route path="/plan/:id/recept/:mealId" element={<RecipePage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe('RecipePage deal headline position', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: { data: RECIPE } });
  });

  it('shows the deal headline before the refine invite card', async () => {
    renderPage();
    const headline = await screen.findByText('2 z 5 surovin ve slevě tento týden');
    const refineCta = await screen.findByRole('button', { name: /Poradit se s kuchařkou/ });

    // DOCUMENT_POSITION_FOLLOWING (4): refineCta comes after headline in page order.
    expect(headline.compareDocumentPosition(refineCta) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows the deal headline after the recipe title', async () => {
    renderPage();
    const headline = await screen.findByText('2 z 5 surovin ve slevě tento týden');
    const title = await waitFor(() => screen.getByRole('heading', { level: 1 }));

    expect(title.compareDocumentPosition(headline) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
