import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/ui/Toast';
import { Dashboard } from './Dashboard';
import { api } from '@/lib/api';

vi.mock('@/lib/api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));
vi.mock('@/components/layout/MainLayout', () => ({
  MainLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/lib/billing', () => ({
  fetchBillingMe: vi.fn().mockResolvedValue(null),
  quotaHeadline: () => '',
}));

const GOALS = [
  {
    id: 1, status: 'completed', prompt: 'Pool plan', city: 'Praha', created_at: '2026-09-01T00:00:00Z',
    is_pool: true, counts: { breakfast: 0, lunch: 0, dinner: 3, small_meal: 0, snack: 1 },
  },
  {
    id: 2, status: 'completed', prompt: 'Legacy plan', city: 'Praha', created_at: '2026-09-01T00:00:00Z',
    is_pool: false, num_days: 7,
  },
];

describe('Dashboard badges', () => {
  it('shows meal count for pool goals and days for legacy goals', async () => {
    vi.mocked(api.get).mockImplementation((url: string) =>
      Promise.resolve({ data: { data: url.includes('/goals/list/') ? GOALS : {} } }),
    );
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ToastProvider>
          <MemoryRouter><Dashboard /></MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    );
    expect(await screen.findByText('4 jídla')).toBeInTheDocument();
    expect(screen.getByText('7 dní')).toBeInTheDocument();
  });
});
