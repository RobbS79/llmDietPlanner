// frontend/src/pages/Landing.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import * as analytics from '@/lib/analytics';
import * as apiMod from '@/lib/api';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/discover';
import { readBasket, setQuery, toggleRecipe } from '@/lib/basket';
import { Landing } from './Landing';

const card = (id: number, name: string) => ({ id, slug: String(id), name, image_url: '/x.webp', minutes: 20, kcal: 500,
  deals: { matched: 0, total: 3, names: [], items: [] } });

const result = (over: Partial<client.DiscoverResult>): client.DiscoverResult => ({
  understood: [], exact: true, fallback: false, medical_note: false, has_more: false, recipes: [], ...over });

const renderLanding = (path = '/') => render(
  <QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={[path]}><Landing /></MemoryRouter></QueryClientProvider>);
const jwt = () => `h.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 600 }))}.s`;

describe('Landing', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.spyOn(client, 'getWeekDeals').mockResolvedValue([]);
  });

  it('asks the question and offers the plan path', () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue(result({}));
    renderLanding();
    expect(screen.getByRole('heading', { level: 1, name: 'Co dnes uvařit?' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Poskládej mi plán' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Přejít na obsah' })).toBeInTheDocument();
    expect(screen.queryByText(/300\+/)).toBeNull();
  });

  it('searches, shows what it understood, and adds to the basket', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue(result({ understood: ['kuřecí prsa'],
      recipes: [card(1, 'Kuře s rýží'), card(2, 'Kuřecí parmigiana')] }));
    renderLanding();
    await userEvent.type(screen.getByLabelText('Co chceš uvařit'), 'kuřecí prsa');
    await userEvent.click(screen.getByRole('button', { name: 'Najít recepty' }));
    expect(await screen.findByText('Kuře s rýží')).toBeInTheDocument();
    expect(screen.getByText('kuřecí prsa', { selector: 'span' })).toBeInTheDocument();
    expect(screen.queryByText(/ne zdravotní rada/)).toBeNull();
    await userEvent.click(screen.getAllByRole('button', { name: 'Chci tohle' })[0]);
    expect(readBasket().recipeIds).toEqual([1]);
    expect(screen.getByRole('button', { name: 'Nákupní seznam' })).toBeInTheDocument();
  });

  it('says so when nothing in the collection meets the restrictions', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue(result({ understood: ['bez masa'], exact: false }));
    renderLanding();
    await userEvent.click(screen.getByRole('button', { name: 'Bez masa' }));
    expect(await screen.findByText(/Na tohle jsme nic nenašli/)).toBeInTheDocument();
    expect(screen.queryByText(/hledání dost/)).toBeNull();
  });

  it('is honest when nothing matched exactly', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue(result({ understood: ['kachna'], exact: false, recipes: [card(3, 'Guláš')] }));
    renderLanding();
    await userEvent.click(screen.getByRole('button', { name: 'Bez masa' }));
    expect(await screen.findByText(/nic přesného nenašli/)).toBeInTheDocument();
  });

  it('shows the medical note when the request mentions an illness', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue(result({ understood: ['cukrovka'], medical_note: true,
      recipes: [card(4, 'Pečená zelenina')] }));
    renderLanding();
    await userEvent.type(screen.getByLabelText('Co chceš uvařit'), 'jídla při cukrovce');
    await userEvent.click(screen.getByRole('button', { name: 'Najít recepty' }));
    expect(await screen.findByText(
      'Uvařto je pomocník do kuchyně, ne zdravotní rada. Jídelníček při nemoci probírej s lékařem.')).toBeInTheDocument();
  });

  it('tells the visitor to come back tomorrow on 429', async () => {
    vi.spyOn(client, 'searchRecipes').mockRejectedValue({ response: { status: 429, data: {} } });
    renderLanding();
    await userEvent.click(screen.getByRole('button', { name: 'Bez masa' }));
    expect(await screen.findByText('Na dnešek už je hledání dost. Zkus to zase zítra.')).toBeInTheDocument();
  });

  it('says something went wrong on any other search failure', async () => {
    vi.spyOn(client, 'searchRecipes').mockRejectedValue({ response: { status: 500, data: {} } });
    renderLanding();
    await userEvent.click(screen.getByRole('button', { name: 'Bez masa' }));
    expect(await screen.findByText('Něco se nepovedlo. Zkus to prosím znovu.')).toBeInTheDocument();
  });

  it('tells Meta where a search came from, never what was typed', async () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue(result({}));
    const search = vi.spyOn(analytics, 'trackSearch');
    renderLanding();
    await userEvent.click(screen.getByRole('button', { name: 'Lehčí jídla na hubnutí' }));
    await userEvent.type(screen.getByLabelText('Co chceš uvařit'), '{selectall}cukrovka');
    await userEvent.click(screen.getByRole('button', { name: 'Najít recepty' }));
    expect(search.mock.calls).toEqual([['chip'], ['typed']]);
  });

  it('reopens the plan sheet after login with the search from the basket', async () => {
    localStorage.setItem('access_token', jwt());
    setQuery('kuřecí prsa na víkend');
    toggleRecipe(5);
    vi.spyOn(apiMod.api, 'get').mockResolvedValue({ data: { subscription: null } });
    const post = vi.spyOn(apiMod.api, 'post').mockResolvedValue({ status: 201, data: { data: { goal_id: 9 } } });
    renderLanding('/hledat?plan=1');
    expect(await screen.findByRole('heading', { name: 'Plán na celý týden' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Sestavit můj plán' }));
    expect(post).toHaveBeenCalledWith('/goals/', expect.objectContaining({ prompt: 'kuřecí prsa na víkend', pinned_recipe_ids: [5] }));
  });

  it('does not open the plan sheet from the URL when signed out', () => {
    vi.spyOn(client, 'searchRecipes').mockResolvedValue(result({}));
    renderLanding('/hledat?plan=1');
    expect(screen.queryByRole('heading', { name: 'Plán na celý týden' })).toBeNull();
  });
});
