import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Pricing } from './Pricing';

vi.mock('@/lib/promo', async (orig) => ({ ...(await orig<typeof import('@/lib/promo')>()), getPendingPromo: () => null }));

const mount = (path = '/pricing') => render(<MemoryRouter initialEntries={[path]}><Pricing /></MemoryRouter>);
const card = (name: string) => screen.getByRole('heading', { name, level: 2 }).closest('div.rounded-3xl') as HTMLElement;

describe('Pricing', () => {
  it('states only the limits the product enforces', () => {
    mount();
    expect(within(card('Zdarma')).getByText('2 plány zdarma')).toBeInTheDocument();
    expect(within(card('Zdarma')).getByText('3 uložené nákupní seznamy měsíčně')).toBeInTheDocument();
    expect(within(card('Standard')).getByText('7 plánů měsíčně')).toBeInTheDocument();
    expect(within(card('Standard')).getByText('Nákupní seznamy bez omezení')).toBeInTheDocument();
    expect(within(card('Premium')).getByText('30 plánů měsíčně')).toBeInTheDocument();
    expect(within(card('Premium')).getByText('Nákupní seznamy bez omezení')).toBeInTheDocument();
    expect(screen.queryByText(/úprav/)).toBeNull();
  });

  it('shows deals as free on every tier, never as a paid extra or a price', () => {
    mount();
    for (const name of ['Zdarma', 'Standard', 'Premium']) {
      expect(within(card(name)).getByText('Co je zrovna v akci')).toBeInTheDocument();
    }
    expect(screen.queryByText(/Akční ceny/)).toBeNull();
    expect(screen.queryByText(/ušetř|šetřit|úspor/i)).toBeNull();
  });

  it('explains the visit when the plan limit sent them here', () => {
    mount('/pricing?reason=quota');
    expect(screen.getByRole('status')).toHaveTextContent('Další plán už se do tvého tarifu nevejde.');
  });

  it('says nothing extra on a normal visit', () => {
    mount();
    expect(screen.queryByRole('status')).toBeNull();
  });
});
