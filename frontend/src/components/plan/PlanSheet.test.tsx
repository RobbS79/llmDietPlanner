import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import axios from 'axios';
import * as analytics from '@/lib/analytics';
import { toggleRecipe } from '@/lib/basket';
import { PlanSheet } from './PlanSheet';

const post = vi.fn();
vi.mock('@/lib/api', () => ({ api: { post: (u: string, b: unknown) => post(u, b) } }));
const billingMe = vi.fn();
vi.mock('@/lib/billing', () => ({ fetchBillingMe: () => billingMe() }));

const jwt = () => `h.${btoa(JSON.stringify({ exp: Date.now() / 1000 + 600 }))}.s`;
const signIn = () => localStorage.setItem('access_token', jwt());

const mount = (props: Partial<Parameters<typeof PlanSheet>[0]> = {}) => render(
  <MemoryRouter>
    <Routes>
      <Route path="/" element={<PlanSheet understood={[]} prompt="" onClose={() => {}} {...props} />} />
      <Route path="/plan/:id" element={<div>PLAN PAGE</div>} />
    </Routes>
  </MemoryRouter>,
);
const build = () => userEvent.click(screen.getByRole('button', { name: 'Sestavit můj plán' }));

describe('PlanSheet', () => {
  beforeEach(() => {
    localStorage.clear(); post.mockReset(); billingMe.mockReset();
    billingMe.mockResolvedValue({ subscription: null, free_generations_remaining: 2 });
  });
  afterEach(() => { vi.restoreAllMocks(); });

  it('asks for signup when signed out, returning to the plan sheet after login', async () => {
    mount();
    await build();
    expect(screen.getByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Nebo e-mailem' })).toHaveAttribute('href', '/login?mode=register&next=%2Fhledat%3Fplan%3D1');
    expect(post).not.toHaveBeenCalled();
  });

  it('asks for signup instead of posting when the session is dead', async () => {
    localStorage.setItem('refresh_token', 'dead');
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('401'));
    mount();
    await build();
    expect(await screen.findByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('posts pool counts and opens the new plan by goal_id', async () => {
    signIn();
    const lead = vi.spyOn(analytics, 'trackPlanStarted');
    post.mockResolvedValue({ status: 201, data: { data: { goal_id: 42 } } });
    mount();
    await build();
    expect(await screen.findByText('PLAN PAGE')).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/goals/', expect.objectContaining({ dinners: 5, lunches: 0, prompt: 'Jen ať nemusím vymýšlet' }));
    expect(lead).toHaveBeenCalledTimes(1);
  });

  it('pins the given ids instead of the basket', async () => {
    signIn();
    toggleRecipe(99);
    post.mockResolvedValue({ status: 201, data: { data: { goal_id: 42 } } });
    mount({ pinnedIds: [3, 4] });
    expect(screen.getByText('Tvoje vybraná jídla v plánu zůstanou.')).toBeInTheDocument();
    await build();
    await screen.findByText('PLAN PAGE');
    expect(post).toHaveBeenCalledWith('/goals/', expect.objectContaining({ pinned_recipe_ids: [3, 4] }));
  });

  it('shows the server error text instead of failing silently, and does not count a lead', async () => {
    signIn();
    const lead = vi.spyOn(analytics, 'trackPlanStarted');
    post.mockRejectedValue({ response: { status: 403, data: { code: 'EMAIL_NOT_VERIFIED', error: 'Potvrď prosím e-mail.' } } });
    mount();
    await build();
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Potvrď prosím e-mail.'));
    expect(lead).not.toHaveBeenCalled();
  });

  it('closes on Escape', async () => {
    const onClose = vi.fn();
    mount({ onClose });
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('mentions the free plan allowance only to free users', async () => {
    mount();
    expect(screen.getByText(/Spotřebuje se 1 ze 2 plánů zdarma/)).toBeInTheDocument();
  });

  it('hides the free plan allowance from subscribers', async () => {
    signIn();
    billingMe.mockResolvedValue({ subscription: { entitled: true }, free_generations_remaining: 0 });
    mount();
    await waitFor(() => expect(billingMe).toHaveBeenCalled());
    expect(screen.queryByText(/Spotřebuje se 1 ze 2 plánů zdarma/)).toBeNull();
    expect(screen.getByText(/Recepty ze sbírky jsou hned/)).toBeInTheDocument();
  });
});
