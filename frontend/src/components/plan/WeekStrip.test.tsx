import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WeekStrip } from './WeekStrip';

const days = [
  { day_number: 1, lunch: { name: 'A', nutritional_info: { calories: '700' } }, small_meals: [{ name: 'B', nutritional_info: { calories: '300' } }], snacks: [] },
  { day_number: 2, lunch: { name: 'C', nutritional_info: { calories: '650' } }, small_meals: [], snacks: [] },
];

describe('WeekStrip', () => {
  it('renders one pill per day with its kcal, linking to the day anchor', () => {
    render(<WeekStrip days={days} goalId="150" />);
    const pills = screen.getAllByRole('link');
    expect(pills).toHaveLength(2);
    expect(pills[0]).toHaveAttribute('href', '#den-1');
    expect(pills[0]).toHaveTextContent('Den 1');
    expect(pills[0]).toHaveTextContent('1000 kcal');
    expect(pills[1]).toHaveTextContent('650 kcal');
  });
});
