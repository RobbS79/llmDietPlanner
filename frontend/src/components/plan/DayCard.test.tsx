import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DayCard } from './DayCard';

const day = {
  day_number: 2,
  lunch: {
    name: 'Segedínský guláš', meal_identifier: '150:2:lunch:0', preparation_time: 70,
    description: 'Klasika.', nutritional_info: { calories: '600', protein: '30g', carbs: '40g', fat: '20g' },
    side: { key: 'knedlik', name_cs: 'houskový knedlík', with_cs: 's houskovým knedlíkem', display: '3 plátky' },
  },
  small_meals: [
    { name: 'Cuketová polévka', meal_identifier: '150:2:small_meal:0', preparation_time: 55, nutritional_info: { calories: '260' } },
    { name: 'Bramborové klínky', meal_identifier: '150:2:small_meal:1', preparation_time: 40, nutritional_info: { calories: '240' } },
  ],
  snacks: [{ name: 'Čerstvé jablko', meal_identifier: '150:2:snack:0', nutritional_info: { calories: '80' } }],
};

const renderDay = (overrides: Partial<React.ComponentProps<typeof DayCard>> = {}) => {
  const onOpen = vi.fn();
  const onToggleCooked = vi.fn();
  render(
    <DayCard
      day={day} goalId="150" cookedSet={new Set(['150:2:small_meal:1'])}
      onOpen={onOpen} onToggleCooked={onToggleCooked} {...overrides}
    />,
  );
  return { onOpen, onToggleCooked };
};

describe('DayCard', () => {
  it('has an anchor per day and a header with the day total and cooked count', () => {
    renderDay();
    const card = document.getElementById('den-2');
    expect(card).not.toBeNull();
    const header = within(card!).getByRole('heading', { level: 2 });
    expect(header).toHaveTextContent('Den 2');
    expect(within(card!).getByText('1180 kcal')).toBeInTheDocument();
    expect(within(card!).getByText('30 g bílkovin')).toBeInTheDocument();
    expect(within(card!).getByText('1/4 uvařeno')).toBeInTheDocument();
  });

  it('renders the main course as a card with side line, time and kcal', () => {
    renderDay();
    const main = screen.getByTestId('main-150:2:lunch:0');
    expect(within(main).getByRole('heading', { level: 3 })).toHaveTextContent('Segedínský guláš');
    expect(within(main).getByText(/s houskovým knedlíkem/)).toBeInTheDocument();
    expect(within(main).getByText('70 min')).toBeInTheDocument();
    expect(within(main).getByText('600 kcal')).toBeInTheDocument();
  });

  it('renders small meals as compact rows, not headings', () => {
    renderDay();
    const row = screen.getByTestId('small-150:2:small_meal:0');
    expect(within(row).queryByRole('heading')).toBeNull();
    expect(within(row).getByText('Cuketová polévka')).toBeInTheDocument();
    expect(within(row).getByText('260 kcal')).toBeInTheDocument();
    expect(within(row).getByText('55 min')).toBeInTheDocument();
  });

  it('marks a cooked row and renders snacks as chips', () => {
    renderDay();
    expect(screen.getByTestId('small-150:2:small_meal:1')).toHaveAttribute('data-cooked', 'true');
    const chip = screen.getByTestId('snack-150:2:snack:0');
    expect(chip).toHaveTextContent('Čerstvé jablko');
    expect(chip).toHaveTextContent('80 kcal');
  });

  it('omits the kcal on a snack chip when the generator gave none', () => {
    const noKcal = { ...day, snacks: [{ name: 'Bílý jogurt', meal_identifier: '150:2:snack:0' }] };
    renderDay({ day: noKcal });
    const chip = screen.getByTestId('snack-150:2:snack:0');
    expect(chip).toHaveTextContent('Bílý jogurt');
    expect(chip).not.toHaveTextContent('kcal');
  });

  it('opens a meal when its row is clicked and passes the identifier', async () => {
    const { onOpen } = renderDay();
    await userEvent.click(screen.getByText('Bramborové klínky'));
    expect(onOpen).toHaveBeenCalledWith('150:2:small_meal:1', false);
  });

  it('toggles cooked from the main card without opening it', async () => {
    const { onOpen, onToggleCooked } = renderDay();
    const main = screen.getByTestId('main-150:2:lunch:0');
    await userEvent.click(within(main).getByRole('button', { name: /uvařen/i }));
    expect(onToggleCooked).toHaveBeenCalledWith('150:2:lunch:0', true, 'Segedínský guláš');
    expect(onOpen).not.toHaveBeenCalled();
  });
});
