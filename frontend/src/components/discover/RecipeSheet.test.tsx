// frontend/src/components/discover/RecipeSheet.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import * as client from '@/lib/discover';
import { RecipeSheet } from './RecipeSheet';

const sheet = { id: 1, slug: 's', name: 'Kulajda', image_url: '/k.webp', minutes: 55, kcal: 584,
  deals: { matched: 1, total: 9, names: ['česnek'], items: [{ canonical: 'garlic', shop: 'Tesco', display_name: 'Česnek', valid_until: '2026-11-04T05:59:59+00:00' }] },
  macros: { protein: 18, carbs: 40, fat: 30 }, source: { name: 'Toprecepty.cz', url: 'https://t.cz' },
  ingredients: [{ name: 'česnek', canonical: 'garlic', quantity: 1, unit: 'stroužky' }],
  steps: ['a', 'b', 'c', 'd'] };

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);

describe('RecipeSheet', () => {
  it('shows macros, source, deal line, first two steps', async () => {
    vi.spyOn(client, 'getRecipeSheet').mockResolvedValue(sheet);
    wrap(<RecipeSheet id={1} picked={false} onToggle={() => {}} onClose={() => {}} />);
    expect(await screen.findByText('Kulajda')).toBeInTheDocument();
    expect(screen.getByText(/B 18 g · S 40 g · T 30 g/)).toBeInTheDocument();
    expect(screen.getByText('Podle receptu z Toprecepty.cz')).toBeInTheDocument();
    expect(screen.getByText(/česnek \(Tesco do 4\. 11\.\)/)).toBeInTheDocument();
    expect(screen.getByText('… a dalších 2 kroků')).toBeInTheDocument();
  });

  it('shows macros even when a value is 0', async () => {
    vi.spyOn(client, 'getRecipeSheet').mockResolvedValue({ ...sheet, macros: { protein: 0, carbs: 40, fat: 0 } });
    wrap(<RecipeSheet id={1} picked={false} onToggle={() => {}} onClose={() => {}} />);
    expect(await screen.findByText(/B 0 g · S 40 g · T 0 g/)).toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    vi.spyOn(client, 'getRecipeSheet').mockResolvedValue(sheet);
    const onClose = vi.fn();
    wrap(<RecipeSheet id={1} picked={false} onToggle={() => {}} onClose={onClose} />);
    await screen.findByText('Kulajda');
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });

  it('moves focus to the close button and returns it to the opener', async () => {
    vi.spyOn(client, 'getRecipeSheet').mockResolvedValue(sheet);
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();
    const { unmount } = wrap(<RecipeSheet id={1} picked={false} onToggle={() => {}} onClose={() => {}} />);
    await screen.findByText('Kulajda');
    expect(screen.getByRole('button', { name: 'Zavřít' })).toHaveFocus();
    unmount();
    expect(opener).toHaveFocus();
    opener.remove();
  });
});
