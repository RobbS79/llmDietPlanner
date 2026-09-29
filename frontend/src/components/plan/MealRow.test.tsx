import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MealRow } from './MealRow';

const entry = {
  slot: 'dinner', key: 'dinner:1', label: 'Večeře', isMain: true,
  meal: { name: 'Svíčková', meal_identifier: '151:dinner:1', preparation_time: 90, description: 'Klasika.',
          nutritional_info: { calories: '650' } },
  mealId: '151:dinner:1',
};

describe('MealRow', () => {
  it('main variant renders card with kcal, time, cooked toggle and chat', async () => {
    const onOpen = vi.fn(); const onToggleCooked = vi.fn();
    render(<MealRow entry={entry} variant="main" isCooked={false} onOpen={onOpen} onToggleCooked={onToggleCooked} />);
    expect(screen.getByTestId('main-151:dinner:1')).toHaveAttribute('data-cooked', 'false');
    expect(screen.getByText('650 kcal')).toBeInTheDocument();
    expect(screen.getByText(/90 min/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /Označit jako uvařené/ }));
    expect(onToggleCooked).toHaveBeenCalledWith('151:dinner:1', true, 'Svíčková');
    await userEvent.click(screen.getByRole('button', { name: /Nesedí/ }));
    expect(onOpen).toHaveBeenCalledWith('151:dinner:1', true);
  });

  it('small variant renders a compact row that opens the recipe', async () => {
    const onOpen = vi.fn();
    render(<ul><MealRow entry={{ ...entry, slot: 'snack', isMain: false, label: 'Snack' }} variant="small" isCooked onOpen={onOpen} onToggleCooked={vi.fn()} /></ul>);
    expect(screen.getByTestId('small-151:dinner:1')).toHaveAttribute('data-cooked', 'true');
    await userEvent.click(screen.getByRole('button'));
    expect(onOpen).toHaveBeenCalledWith('151:dinner:1', false);
  });

  it('main variant when cooked shows Uvařeno and toggles back to not cooked', async () => {
    const onToggleCooked = vi.fn();
    render(<MealRow entry={entry} variant="main" isCooked onOpen={vi.fn()} onToggleCooked={onToggleCooked} />);
    await userEvent.click(screen.getByRole('button', { name: /Uvařeno/ }));
    expect(onToggleCooked).toHaveBeenCalledWith('151:dinner:1', false, 'Svíčková');
  });

  it('small variant with zero kcal renders no kcal text', () => {
    const zero = { ...entry, slot: 'snack', isMain: false, meal: { ...entry.meal, nutritional_info: { calories: 0 } } };
    render(<ul><MealRow entry={zero} variant="small" isCooked={false} onOpen={vi.fn()} onToggleCooked={vi.fn()} /></ul>);
    expect(screen.queryByText(/kcal/)).not.toBeInTheDocument();
  });
});
