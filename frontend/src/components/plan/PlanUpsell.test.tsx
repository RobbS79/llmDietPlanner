import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { PlanUpsell } from './PlanUpsell';

const billingMe = vi.fn();
vi.mock('@/lib/billing', () => ({ fetchBillingMe: () => billingMe() }));

const mount = () => render(<MemoryRouter><PlanUpsell /></MemoryRouter>);

describe('PlanUpsell', () => {
  beforeEach(() => { billingMe.mockReset(); });

  it('tells a free user how many free plans are left and what Standard adds', async () => {
    billingMe.mockResolvedValue({ subscription: null, free_generations_remaining: 1 });
    mount();
    expect(await screen.findByText(/Máš ještě 1 plán zdarma\./)).toBeInTheDocument();
    expect(screen.getByText(/Standard za 99 Kč měsíčně/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Podívat se na předplatné' })).toHaveAttribute('href', '/pricing');
  });

  it('uses Czech plurals for the remaining count', async () => {
    billingMe.mockResolvedValue({ subscription: null, free_generations_remaining: 3 });
    mount();
    expect(await screen.findByText(/Máš ještě 3 plány zdarma\./)).toBeInTheDocument();
  });

  it('says so plainly when the free plans are used up', async () => {
    billingMe.mockResolvedValue({ subscription: null, free_generations_remaining: 0 });
    mount();
    expect(await screen.findByText(/Plány zdarma už máš vyčerpané\./)).toBeInTheDocument();
  });

  it('shows nothing to subscribers', async () => {
    billingMe.mockResolvedValue({ subscription: { entitled: true }, free_generations_remaining: 0 });
    const { container } = mount();
    await Promise.resolve(); await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });

  it('shows nothing when billing cannot be loaded', async () => {
    billingMe.mockImplementation(() => Promise.reject(new Error('500')));
    const { container } = mount();
    await Promise.resolve(); await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
