import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DealsStrip } from './DealsStrip';

vi.mock('@/lib/discover', async (orig) => ({
  ...(await orig<typeof import('@/lib/discover')>()),
  getWeekDeals: async () => [{
    canonical: 'cream', name: 'Smetana ke šlehání 250 g', shop: 'Lidl',
    valid_until: '2026-12-04T23:59:00+00:00',
  }],
}));

describe('DealsStrip', () => {
  it('shows the full deal name, not the first two words', async () => {
    const client = new QueryClient();
    render(<QueryClientProvider client={client}><DealsStrip onPick={vi.fn()} /></QueryClientProvider>);
    expect(await screen.findByText('Smetana ke šlehání 250 g')).toBeTruthy();
  });
});
