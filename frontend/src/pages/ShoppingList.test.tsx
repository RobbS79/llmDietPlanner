// frontend/src/pages/ShoppingList.test.tsx
import { StrictMode } from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/discover';
import * as basketLib from '@/lib/basket';
import * as apiMod from '@/lib/api';
import axios from 'axios';
import { toggleRecipe, readBasket, clearBasket } from '@/lib/basket';
import { ShoppingList } from './ShoppingList';

const lines = [
  { name: 'česnek', canonical: 'garlic', amount: 3, unit: 'stroužky', needed_by: 2, recipe_ids: [1, 2],
    deal: { canonical: 'garlic', shop: 'Tesco', display_name: 'Česnek', valid_until: '2026-11-04T05:59:59+00:00' } },
  { name: 'rýže', canonical: 'rice', amount: 200, unit: 'g', needed_by: 1, recipe_ids: [1], deal: null },
];

const jwt = () => `h.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 600 }))}.s`;
const signIn = () => localStorage.setItem('access_token', jwt());

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
    const home = screen.getByRole('button', { name: 'česnek: mám doma' });
    expect(home).toHaveAttribute('aria-pressed', 'false');
    await userEvent.click(home);
    expect(readBasket().atHome).toEqual(['garlic|stroužky']);
    expect(screen.getByRole('button', { name: 'česnek: mám doma' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens the signup sheet when an anonymous visitor saves', async () => {
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Uložit si to' }));
    expect(screen.getByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
  });

  it('links back to the search, which works signed in too', async () => {
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    renderPage();
    expect(screen.getByRole('link', { name: '← Zpět k receptům' })).toHaveAttribute('href', '/hledat');
  });

  it('welcomes a user back from signup and keeps showing the saved dishes after the basket clears', async () => {
    signIn();
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
    signIn();
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    vi.spyOn(basketLib, 'attachBasketAfterLogin').mockResolvedValue('limit');
    renderPage('/nakup?vitej=1');
    expect(await screen.findByText('Tento měsíc už máš uložené 3 seznamy. S předplatným bez omezení.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Nákup na 2 jídla' })).toBeInTheDocument();
  });

  it('keeps the basket and says so when saving fails', async () => {
    signIn();
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    vi.spyOn(basketLib, 'attachBasketAfterLogin').mockResolvedValue('error');
    renderPage('/nakup?vitej=1');
    expect(await screen.findByText('Uložení se nepovedlo. Zkus to prosím znovu.')).toBeInTheDocument();
    expect(readBasket().recipeIds).toEqual([1, 2]);
    expect(screen.getByRole('button', { name: 'Uložit si to' })).toBeEnabled();
    // Still rendering from the basket: a change goes to the basket, not a snapshot.
    await userEvent.click(screen.getByRole('button', { name: 'Více lidí' }));
    expect(readBasket().people).toBe(3);
  });

  it('saves once on a double click', async () => {
    signIn();
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    let finish: (v: unknown) => void = () => {};
    const post = vi.spyOn(apiMod.api, 'post').mockImplementation(() => new Promise((r) => { finish = r; }));
    renderPage();
    const save = await screen.findByRole('button', { name: 'Uložit si to' });
    await userEvent.click(save);
    await userEvent.click(save);
    expect(save).toBeDisabled();
    expect(post).toHaveBeenCalledTimes(1);
    finish({ status: 201, data: {} });
    expect(await screen.findByText('Ahoj, vítej v Uvařto.')).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('asks to sign in again instead of saving when the session is dead', async () => {
    localStorage.setItem('refresh_token', 'dead');
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('401'));
    const attach = vi.spyOn(basketLib, 'attachBasketAfterLogin');
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: 'Uložit si to' }));
    expect(await screen.findByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
    expect(attach).not.toHaveBeenCalled();
    expect(readBasket().recipeIds).toEqual([1, 2]);
  });

  it('the welcome plan keeps the dishes that were just saved', async () => {
    signIn();
    vi.spyOn(client, 'composeList').mockResolvedValue({ recipes: [], lines });
    vi.spyOn(basketLib, 'attachBasketAfterLogin').mockImplementation(async () => { clearBasket(); return 'saved'; });
    vi.spyOn(apiMod.api, 'get').mockResolvedValue({ data: { subscription: null } });
    const post = vi.spyOn(apiMod.api, 'post').mockResolvedValue({ status: 201, data: { data: { goal_id: 7 } } });
    renderPage('/nakup?vitej=1');
    await userEvent.click(await screen.findByRole('button', { name: 'Jo, poskládej mi týden' }));
    expect(screen.getByText('Tvoje vybraná jídla v plánu zůstanou.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Sestavit můj plán' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/goals/', expect.objectContaining({ pinned_recipe_ids: [1, 2] })));
  });
});
