import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CreatePlan } from './CreatePlan';

const post = vi.fn<(url: string, body: unknown) => Promise<unknown>>(() => Promise.resolve({ data: { data: { goal_id: 9 } } }));
vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn((url: string) => {
      if (url === '/goals/list/') return Promise.resolve({ data: { data: [
        { id: 3, status: 'completed', prompt: 'starý', city: 'Brno', country: 'CZ', language_code: 'cs',
          breakfasts: 1, lunches: 2, dinners: 3, small_meals: 0, snacks: 4, counts: { breakfast: 1, lunch: 2, dinner: 3, small_meal: 0, snack: 4 } },
        { id: 4, status: 'completed', prompt: 'legacy', city: 'Ostrava', country: 'CZ', language_code: 'cs', num_days: 7,
          breakfasts: 0, lunches: 0, dinners: 0, small_meals: 0, snacks: 0, counts: { breakfast: 0, lunch: 0, dinner: 0, small_meal: 0, snack: 0 } },
      ] } });
      return Promise.resolve({ data: { data: { dietary_preferences: {} } } });
    }),
    post: (url: string, body: unknown) => post(url, body),
  },
}));
vi.mock('@/components/layout/MainLayout', () => ({ MainLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/ProtocolUpload', () => ({ ProtocolUpload: () => null }));

const mount = () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><MemoryRouter><CreatePlan /></MemoryRouter></QueryClientProvider>);
};

describe('CreatePlan (pool)', () => {
  beforeEach(() => post.mockClear());

  it('defaults to the working-week preset and submits counts, no day fields', async () => {
    mount();
    await userEvent.type(screen.getByPlaceholderText(/Vysoko proteinová/), 'večeře');
    await userEvent.type(screen.getByPlaceholderText('např. Praha'), 'Praha');
    await userEvent.click(screen.getAllByRole('button', { name: /Další krok/ })[0]);
    expect(screen.getByLabelText('Snídaně')).toHaveValue(5);
    expect(screen.getByLabelText('Drobné snacky')).toHaveValue(0);
    await userEvent.click(screen.getAllByRole('button', { name: /Vygenerovat/ })[0]);
    const body = post.mock.calls[0][1] as Record<string, unknown>;
    expect(body).toMatchObject({ breakfasts: 5, lunches: 5, dinners: 5, small_meals: 5, snacks: 0 });
    expect(body).not.toHaveProperty('num_days');
    expect(body).not.toHaveProperty('breakfast');
  });

  it('presets and steppers change counts; all-zero blocks submit', async () => {
    mount();
    await userEvent.type(screen.getByPlaceholderText(/Vysoko proteinová/), 'x');
    await userEvent.type(screen.getByPlaceholderText('např. Praha'), 'Praha');
    await userEvent.click(screen.getAllByRole('button', { name: /Další krok/ })[0]);
    await userEvent.click(screen.getByRole('button', { name: 'Víkend' }));
    expect(screen.getByLabelText('Večeře')).toHaveValue(2);
    await userEvent.click(screen.getByRole('button', { name: 'Více: Večeře' }));
    expect(screen.getByLabelText('Večeře')).toHaveValue(3);
    for (const label of ['Snídaně', 'Obědy', 'Večeře', 'Svačiny', 'Drobné snacky']) {
      await userEvent.clear(screen.getByLabelText(label));
      await userEvent.type(screen.getByLabelText(label), '0');
    }
    expect(screen.getAllByRole('button', { name: /Vygenerovat/ })[0]).toBeDisabled();
    expect(screen.getByText(/Vyberte alespoň jedno jídlo/)).toBeInTheDocument();
  });

  it('prefills counts from a previous goal', async () => {
    mount();
    await userEvent.click(await screen.findByRole('button', { name: /Brno · 10 jídel/ }));
    await userEvent.type(screen.getByPlaceholderText('např. Praha'), 'x');
    await userEvent.click(screen.getAllByRole('button', { name: /Další krok/ })[0]);
    expect(screen.getByLabelText('Drobné snacky')).toHaveValue(4);
    expect(screen.getByLabelText('Obědy')).toHaveValue(2);
  });

  it('legacy goal chip shows its day count instead of 0 meals', async () => {
    mount();
    expect(await screen.findByRole('button', { name: /Ostrava · 7 dní/ })).toBeInTheDocument();
  });
});
