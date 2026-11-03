import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PlanSheet } from './PlanSheet';

const post = vi.fn();
vi.mock('@/lib/api', () => ({ api: { post: (u: string, b: unknown) => post(u, b) } }));

const mount = () => render(
  <MemoryRouter>
    <Routes>
      <Route path="/" element={<PlanSheet understood={[]} prompt="" onClose={() => {}} />} />
      <Route path="/plan/:id" element={<div>PLAN PAGE</div>} />
    </Routes>
  </MemoryRouter>,
);

describe('PlanSheet', () => {
  beforeEach(() => { localStorage.clear(); post.mockReset(); });

  it('asks for signup when signed out', async () => {
    mount();
    await userEvent.click(screen.getByRole('button', { name: 'Sestavit můj plán' }));
    expect(screen.getByRole('heading', { name: 'Uložit si to' })).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('posts pool counts and opens the new plan by goal_id', async () => {
    localStorage.setItem('refresh_token', 'r');
    post.mockResolvedValue({ data: { data: { goal_id: 42 } } });
    mount();
    await userEvent.click(screen.getByRole('button', { name: 'Sestavit můj plán' }));
    expect(await screen.findByText('PLAN PAGE')).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/goals/', expect.objectContaining({ dinners: 5, lunches: 0, prompt: 'Jen ať nemusím vymýšlet' }));
  });

  it('shows the server error text instead of failing silently', async () => {
    localStorage.setItem('refresh_token', 'r');
    post.mockRejectedValue({ response: { status: 403, data: { code: 'EMAIL_NOT_VERIFIED', error: 'Potvrď prosím e-mail.' } } });
    mount();
    await userEvent.click(screen.getByRole('button', { name: 'Sestavit můj plán' }));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Potvrď prosím e-mail.'));
  });
});
