import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/ui/Toast';
import { RecipePage } from './RecipePage';
import { api } from '@/lib/api';
import { replaceRecipe } from '@/lib/replaceRecipe';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/replaceRecipe', () => ({ replaceRecipe: vi.fn() }));
vi.mock('@/lib/pricing', () => ({ getRecipeDeals: () => null, getShoppingList: () => [] }));
vi.mock('@/lib/food-image', () => ({ getFoodImageUrl: () => '' }));

const MEAL_ID = '12:1:lunch:0';
const RECIPE = {
  name: 'Kuře s rýží', description: '', ingredients: [],
  instructions: ['Uvař.'], servings: 1, nutritional_info: {}, source_url: '',
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
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
  return { invalidateSpy };
}

async function openPanelAndSubmit(hint?: string) {
  await userEvent.click(await screen.findByRole('button', { name: 'Vyměnit recept' }));
  const box = await screen.findByLabelText('Na co máte chuť? (nepovinné)');
  if (hint) await userEvent.type(box, hint);
  await userEvent.click(screen.getByRole('button', { name: 'Vyměnit' }));
}

describe('RecipePage replace-recipe panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: { data: RECIPE } });
  });

  it('swaps with a hint and shows the success toast', async () => {
    vi.mocked(replaceRecipe).mockResolvedValue({
      replaced: true, hint_matched: true, recipe: { ...RECIPE, name: 'Kuřecí salát' },
    });
    const { invalidateSpy } = renderPage();
    await openPanelAndSubmit('něco s kuřecím');

    expect(replaceRecipe).toHaveBeenCalledWith(MEAL_ID, 'něco s kuřecím');
    expect(await screen.findByText('Recept byl vyměněn.')).toBeInTheDocument();
    // Both the plan AND the cooked-state query must refresh, else the swapped
    // meal can show a stale "Uvařeno" badge back on the plan.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['plan', '12'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['mealInstances', '12'] });
  });

  it('submits with an empty hint when the box is left blank', async () => {
    vi.mocked(replaceRecipe).mockResolvedValue({
      replaced: true, hint_matched: null, recipe: { ...RECIPE, name: 'Guláš' },
    });
    renderPage();
    await openPanelAndSubmit();

    expect(replaceRecipe).toHaveBeenCalledWith(MEAL_ID, '');
    expect(await screen.findByText('Recept byl vyměněn.')).toBeInTheDocument();
  });

  it('shows the fallback notice when the hint did not match', async () => {
    vi.mocked(replaceRecipe).mockResolvedValue({
      replaced: true, hint_matched: false, recipe: { ...RECIPE, name: 'Guláš' },
    });
    renderPage();
    await openPanelAndSubmit('něco s tofu');

    expect(await screen.findByText(
      'Nenašli jsme recept přesně podle přání, vybrali jsme jinou variantu.',
    )).toBeInTheDocument();
    // Exactly one toast — not stacked on top of a generic green success.
    expect(screen.queryByText('Recept byl vyměněn.')).not.toBeInTheDocument();
  });

  it('keeps the panel open with a message when there is no alternative', async () => {
    vi.mocked(replaceRecipe).mockResolvedValue({ replaced: false, reason: 'no_alternatives' });
    renderPage();
    await openPanelAndSubmit();

    expect(await screen.findByText('Pro tento typ jídla teď nemáme jinou alternativu.')).toBeInTheDocument();
    // Panel stays open so the user can retry.
    expect(screen.getByLabelText('Na co máte chuť? (nepovinné)')).toBeInTheDocument();
  });

  it('shows an error toast when the request fails', async () => {
    vi.mocked(replaceRecipe).mockRejectedValue(new Error('network'));
    renderPage();
    await openPanelAndSubmit();

    expect(await screen.findByText('Výměna se nezdařila, zkuste to prosím znovu.')).toBeInTheDocument();
  });
});
