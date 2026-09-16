import { describe, it, expect } from 'vitest';
import { dayMealEntries, dayTotals, parseNutrition, MEAL_SLOT_LABELS } from './planMeals';

const day = {
  day_number: 3,
  lunch: { name: 'Oběd', meal_identifier: '150:3:lunch:0', nutritional_info: { calories: 600 } },
  small_meals: [
    { name: 'Polévka', meal_identifier: '150:3:small_meal:0', nutritional_info: { calories: 260 } },
    { name: 'Klínky', nutritional_info: { calories: 240 } },
  ],
  snacks: [{ name: 'Jablko', meal_identifier: '150:3:snack:0', nutritional_info: { calories: 80 } }],
};

describe('dayMealEntries', () => {
  it('lists mains first, then small meals, then snacks, with labels', () => {
    const entries = dayMealEntries(day, '150');
    expect(entries.map(e => e.meal.name)).toEqual(['Oběd', 'Polévka', 'Klínky', 'Jablko']);
    expect(entries.map(e => e.label)).toEqual(['Oběd', 'Svačina', 'Svačina', 'Snack']);
  });

  it('uses the stored identifier and falls back to the indexed contract', () => {
    const entries = dayMealEntries(day, '150');
    expect(entries[1].mealId).toBe('150:3:small_meal:0');
    expect(entries[2].mealId).toBe('150:3:small_meal:1');
    expect(entries[3].mealId).toBe('150:3:snack:0');
  });

  it('sums a day across mains, small meals and snacks', () => {
    expect(dayTotals(day)).toEqual({ kcal: 1180, protein: 0, carbs: 0, fat: 0 });
  });

  it('parses "46g" style macro strings', () => {
    expect(parseNutrition({ calories: '742 kcal', protein: '46g', carbs: '138g', fat: '4g' }))
      .toEqual({ kcal: 742, protein: 46, carbs: 138, fat: 4 });
  });

  it('skips absent mains and empty lists', () => {
    const entries = dayMealEntries({ day_number: 1, dinner: { name: 'Večeře' } }, '9');
    expect(entries).toHaveLength(1);
    expect(entries[0].mealId).toBe('9:1:dinner:0');
    expect(MEAL_SLOT_LABELS.dinner).toBe('Večeře');
  });
});
