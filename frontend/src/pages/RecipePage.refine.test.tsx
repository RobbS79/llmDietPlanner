import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/ui/Toast';
import { RecipePage } from './RecipePage';
import { api } from '@/lib/api';
import { refinePreview, refineAccept } from '@/lib/refineRecipe';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/lib/refineRecipe', () => ({ refinePreview: vi.fn(), refineAccept: vi.fn() }));
vi.mock('@/lib/pricing', () => ({ getRecipeDeals: () => null, getShoppingList: () => [] }));
vi.mock('@/lib/food-image', () => ({ getFoodImageUrl: () => '' }));

const MEAL_ID = '12:1:lunch:0';
const RECIPE = {
  name: 'Kuře s rýží', description: '', ingredients: [],
  instructions: ['Uvař.'], servings: 1, nutritional_info: {}, source_url: '',
};
const CANDIDATE = {
  curated_recipe_id: 7, name: 'Kuřecí salát', description: '',
  food_category: '', preparation_time: 15, calories: 420, why: null,
};

function renderPage(entry = `/plan/12/recept/${MEAL_ID}`) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/plan/:id/recept/:mealId" element={<RecipePage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
  return { qc, invalidateSpy };
}

describe('RecipePage refine chat integration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.get).mockResolvedValue({ data: { data: RECIPE } });
  });

  it('opens the chat from the invite card CTA', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /Poradit se s kuchařkou/ }));
    expect(screen.getByPlaceholderText('Napište, na co máte chuť…')).toBeInTheDocument();
  });

  it('an intent chip opens the chat AND sends itself as the first message', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: true,
    });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Chci něco rychlejšího' }));

    expect(await screen.findByPlaceholderText('Napište, na co máte chuť…')).toBeInTheDocument();
    expect(refinePreview).toHaveBeenCalledWith(
      MEAL_ID, [{ role: 'user', text: 'Chci něco rychlejšího' }], [],
    );
  });

  it('?chat=1 opens the chat on arrival (plan deep link)', async () => {
    renderPage(`/plan/12/recept/${MEAL_ID}?chat=1`);
    expect(await screen.findByPlaceholderText('Napište, na co máte chuť…')).toBeInTheDocument();
    // No message sent — the deep link opens the conversation, it doesn't guess
    // what the user dislikes.
    expect(refinePreview).not.toHaveBeenCalled();
  });

  it('an accepted swap updates caches and closes the chat', async () => {
    vi.mocked(refinePreview).mockResolvedValue({
      candidate: CANDIDATE, question: null, hint_matched: true,
    });
    vi.mocked(refineAccept).mockResolvedValue({
      replaced: true, recipe: { ...RECIPE, name: 'Kuřecí salát' },
    });
    const { qc, invalidateSpy } = renderPage();
    await userEvent.click(await screen.findByRole('button', { name: /Poradit se s kuchařkou/ }));
    await userEvent.type(
      screen.getByPlaceholderText('Napište, na co máte chuť…'), 'něco s kuřecím',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Odeslat' }));
    await userEvent.click(await screen.findByRole('button', { name: 'Použít tento recept' }));

    expect(await screen.findByText(/Hotovo — místo „Kuře s rýží“ máte teď „Kuřecí salát“\./))
      .toBeInTheDocument();
    expect((qc.getQueryData(['recipe', MEAL_ID]) as any).name).toBe('Kuřecí salát');
    // Both the plan AND the cooked-state query must refresh, else the swapped
    // meal can show a stale "Uvařeno" badge back on the plan.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['plan', '12'] });
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['mealInstances', '12'] });
    // Chat panel closed after accept.
    expect(screen.queryByPlaceholderText('Napište, na co máte chuť…')).toBeNull();
  });

  describe('undoing a swap', () => {
    async function swap(previous: { curated_recipe_id: number; name: string } | null) {
      vi.mocked(refinePreview).mockResolvedValue({
        candidate: CANDIDATE, question: null, hint_matched: true,
      });
      vi.mocked(refineAccept).mockResolvedValue({
        replaced: true, recipe: { ...RECIPE, name: 'Kuřecí salát' }, previous,
      });
      const rendered = renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Poradit se s kuchařkou/ }));
      await userEvent.type(
        screen.getByPlaceholderText('Napište, na co máte chuť…'), 'něco s kuřecím',
      );
      await userEvent.click(screen.getByRole('button', { name: 'Odeslat' }));
      await userEvent.click(await screen.findByRole('button', { name: 'Použít tento recept' }));
      return rendered;
    }

    it('offers the way back and commits the previous recipe id', async () => {
      const { qc } = await swap({ curated_recipe_id: 3, name: 'Kuře s rýží' });
      vi.mocked(refineAccept).mockResolvedValue({
        replaced: true, recipe: { ...RECIPE, name: 'Kuře s rýží' }, previous: null,
      });

      await userEvent.click(await screen.findByRole('button', { name: 'Vrátit původní recept' }));

      expect(refineAccept).toHaveBeenLastCalledWith(MEAL_ID, 3);
      expect((qc.getQueryData(['recipe', MEAL_ID]) as any).name).toBe('Kuře s rýží');
      expect(await screen.findByText('Vrátili jsme původní recept.')).toBeInTheDocument();
      // Banner is gone once the swap is undone — nothing left to undo.
      expect(screen.queryByRole('button', { name: 'Vrátit původní recept' })).toBeNull();
    });

    it('hides undo when the replaced meal had no corpus recipe to go back to', async () => {
      await swap(null);
      expect(await screen.findByText(/máte teď „Kuřecí salát“/)).toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Vrátit původní recept' })).toBeNull();
    });

    it('the confirmation persists instead of vanishing like a toast', async () => {
      await swap({ curated_recipe_id: 3, name: 'Kuře s rýží' });
      const banner = await screen.findByRole('status');
      // Four seconds is not long enough to read a new recipe and change your
      // mind, so this must still be on screen well past a toast's lifetime.
      await new Promise((r) => setTimeout(r, 4_500));
      expect(banner).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Vrátit původní recept' })).toBeInTheDocument();
    });
  });
});
