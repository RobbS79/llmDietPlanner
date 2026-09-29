import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { SlotSection } from './SlotSection';

const section = {
  slot: 'dinner' as const, label: 'Večeře', isMain: true,
  entries: [
    { slot: 'dinner', key: 'dinner:0', label: 'Večeře', isMain: true, mealId: '151:dinner:0',
      meal: { name: 'Guláš', meal_identifier: '151:dinner:0', nutritional_info: { calories: 600 } } },
    { slot: 'dinner', key: 'dinner:1', label: 'Večeře', isMain: true, mealId: '151:dinner:1',
      meal: { name: 'Řízek', meal_identifier: '151:dinner:1', nutritional_info: { calories: 700 } } },
  ],
};

describe('SlotSection', () => {
  it('renders an anchored heading with the count and one row per meal', () => {
    render(<SlotSection section={section} requested={2} cookedSet={new Set(['151:dinner:1'])} onOpen={vi.fn()} onToggleCooked={vi.fn()} />);
    const sec = document.getElementById('slot-dinner')!;
    expect(within(sec).getByRole('heading', { level: 2 })).toHaveTextContent('Večeře · 2');
    expect(within(sec).getAllByTestId(/^main-/)).toHaveLength(2);
    expect(within(sec).getByText('1/2 uvařeno')).toBeInTheDocument();
  });

  it('shows "x z y" when the corpus came up short', () => {
    render(<SlotSection section={section} requested={5} cookedSet={new Set()} onOpen={vi.fn()} onToggleCooked={vi.fn()} />);
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Večeře · 2 z 5');
    expect(screen.getByText(/Našli jsme jen 2 z 5/)).toBeInTheDocument();
  });

  it('renders small-meal sections as compact rows', () => {
    const s = { ...section, slot: 'snack' as const, label: 'Snacky', isMain: false };
    render(<SlotSection section={s} requested={2} cookedSet={new Set()} onOpen={vi.fn()} onToggleCooked={vi.fn()} />);
    expect(screen.getAllByTestId(/^small-/)).toHaveLength(2);
  });
});
