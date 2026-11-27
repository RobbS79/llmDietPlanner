import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RecipeCard } from './RecipeCard';

const card = { id: 3, slug: 's', name: 'Losos s medovo-česnekovou omáčkou z hnědého másla', image_url: '/x.webp',
  minutes: 20, kcal: null, deals: { matched: 1, total: 6, names: ['česnek'], items: [] } };

describe('RecipeCard', () => {
  it('shows time, hides unknown kcal, shows the deals badge', () => {
    render(<RecipeCard recipe={card} picked={false} onToggle={() => {}} onOpen={() => {}} />);
    expect(screen.getByText('20 min')).toBeInTheDocument();
    expect(screen.queryByText(/kcal/)).toBeNull();
    expect(screen.getByText('V akci: česnek')).toBeInTheDocument();
  });

  it('toggles and opens', async () => {
    const onToggle = vi.fn(); const onOpen = vi.fn();
    render(<RecipeCard recipe={card} picked={false} onToggle={onToggle} onOpen={onOpen} />);
    await userEvent.click(screen.getByRole('button', { name: 'Chci tohle' }));
    expect(onToggle).toHaveBeenCalledWith(3);
    await userEvent.click(screen.getByRole('button', { name: card.name }));
    expect(onOpen).toHaveBeenCalledWith(3);
  });

  it('says it is in the list when picked', () => {
    render(<RecipeCard recipe={card} picked onToggle={() => {}} onOpen={() => {}} />);
    expect(screen.getByRole('button', { name: 'V seznamu ✓' })).toHaveAttribute('aria-pressed', 'true');
  });
});
