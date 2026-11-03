// frontend/src/pages/ShoppingList.test.tsx
import { StrictMode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/discover';
import * as basketLib from '@/lib/basket';
import { toggleRecipe, readBasket, clearBasket } from '@/lib/basket';
import { ShoppingList } from './ShoppingList';

const lines = [
  { name: 'česnek', canonical: 'garlic', amount: 3, unit: 'stroužky', needed_by: 2, recipe_ids: [1, 2],
    deal: { canonical: 'garlic', shop: 'Tesco', display_name: 'Česnek', valid_until: '2026-11-04T05:59:59+00:00' } },
  { name: 'rýže', canonical: 'rice', amount: 200, unit: 'g', needed_by: 1, recipe_ids: [1], deal: null },
];

const renderPage = (path = '/nakup', strict = false) => {
  const tree = <QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><ShoppingList /></MemoryRouter></QueryClientProvider>;
  return render(strict ? <StrictMode>{tree}</StrictMode> : tree);
};

describe('ShoppingList', () => {
  beforeEach(() => { localStorage.clear(); clearBasket(); toggleRecipe(1); toggleRecipe(2); });
  afterEach(() => { vi.restoreAllMocks(); });

  it('puts deals first and marks what I have at home', async () => {
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    renderPage();
    expect(await screen.findByRole('heading', { name: 'Nákup na 2 jídla' })).toBeInTheDocument();
    expect(await screen.findByText('Tento týden v akci')).toBeInTheDocument(); // after the list loads
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

  it('welcomes a user back from signup and keeps showing the saved dishes after the basket clears', async () => {
    localStorage.setItem('refresh_token', 'r');
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    // The real attach clears the basket on success; mirror that.
    const attach = vi.spyOn(basketLib, 'attachBasketAfterLogin').mockImplementation(async () => { clearBasket(); return 'saved'; });
    renderPage('/nakup?vitej=1', true);
    expect(await screen.findByText('Ahoj, vítej v Uvařto.')).toBeInTheDocument();
    expect(attach).toHaveBeenCalledTimes(1); // Strict Mode double effect must not attach twice
    expect(readBasket().recipeIds).toEqual([]);
    expect(screen.getByRole('heading', { name: 'Nákup na 2 jídla' })).toBeInTheDocument();
    expect(await screen.findByText('česnek')).toBeInTheDocument();
    expect(screen.queryByText(/Zatím tu nic není/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Uložit si to' })).not.toBeInTheDocument();
  });

  it('shows the monthly limit when the free saved lists are used up', async () => {
    localStorage.setItem('refresh_token', 'r');
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    vi.spyOn(basketLib, 'attachBasketAfterLogin').mockResolvedValue('limit');
    renderPage('/nakup?vitej=1');
    expect(await screen.findByText('Tento měsíc už máš uložené 3 seznamy. S předplatným bez omezení.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Nákup na 2 jídla' })).toBeInTheDocument();
  });
});
