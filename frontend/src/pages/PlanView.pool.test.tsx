import type { ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/ui/Toast';
import { PlanView } from './PlanView';

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn((url: string) => {
      if (url.endsWith('/task-status/')) return Promise.resolve({ data: { data: { goal_status: 'completed' } } });
      if (url.endsWith('/meal-instances/')) return Promise.resolve({ data: { data: [{ meal_identifier: '151:dinner:0', is_cooked: true }] } });
      return Promise.resolve({ data: { data: {
        id: 151, city: 'Praha', language_code: 'cs', prompt: 'večeře', is_pool: true,
        counts: { breakfast: 0, lunch: 0, dinner: 3, small_meal: 0, snack: 1 },
        dietary_plan: {
          days: [], shortfall: { dinner: 1 },
          meals: [
            { slot: 'dinner', index: 0, name: 'Guláš', meal_identifier: '151:dinner:0', nutritional_info: { calories: 600 } },
            { slot: 'dinner', index: 1, name: 'Řízek', meal_identifier: '151:dinner:1', nutritional_info: { calories: 700 } },
            { slot: 'snack', index: 0, name: 'Jablko', meal_identifier: '151:snack:0', nutritional_info: { calories: 80 } },
          ],
        },
      } } });
    }),
    patch: vi.fn(),
  },
}));
vi.mock('@/components/layout/MainLayout', () => ({ MainLayout: ({ children }: { children: ReactNode }) => <div>{children}</div> }));
vi.mock('@/components/ads/AdRail', () => ({ AdRail: () => null }));

describe('PlanView (pool)', () => {
  it('renders slot sections, counts summary, cooked counter and shortfall', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/plan/151']}>
            <Routes><Route path="/plan/:id" element={<PlanView />} /></Routes>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('3 večeře · 1 snack')).toBeInTheDocument();
    expect(document.getElementById('slot-dinner')).not.toBeNull();
    expect(document.getElementById('slot-snack')).not.toBeNull();
    expect(screen.getByText('Večeře · 2 z 3')).toBeInTheDocument();
    expect(screen.getByText('1/3')).toBeInTheDocument();          // Uvařeno stat
    expect(screen.getByText('650')).toBeInTheDocument();          // avg kcal per main
    expect(screen.queryByText(/Den 1/)).toBeNull();
  });
});
