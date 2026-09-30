import { describe, it, expect } from 'vitest';
import { dayMealEntries, dayTotals, parseNutrition, MEAL_SLOT_LABELS, groupPoolMeals, poolEntries, poolTotals, POOL_SECTION_LABELS } from './planMeals';

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

const pool = [
  { slot: 'dinner', index: 1, name: 'Řízek', meal_identifier: '151:dinner:1', nutritional_info: { calories: 700 } },
  { slot: 'breakfast', index: 0, name: 'Kaše', meal_identifier: '151:breakfast:0', nutritional_info: { calories: 400 } },
  { slot: 'dinner', index: 0, name: 'Guláš', nutritional_info: { calories: 600 } },
  { slot: 'snack', index: 0, name: 'Jablko', meal_identifier: '151:snack:0', nutritional_info: { calories: 80 } },
];

describe('pool helpers', () => {
  it('poolEntries orders by slot then index and falls back to the pool identifier', () => {
    const entries = poolEntries(pool, '151');
    expect(entries.map(e => e.meal.name)).toEqual(['Kaše', 'Guláš', 'Řízek', 'Jablko']);
    expect(entries.map(e => e.mealId)).toEqual(['151:breakfast:0', '151:dinner:0', '151:dinner:1', '151:snack:0']);
    expect(entries.map(e => e.isMain)).toEqual([true, true, true, false]);
    expect(entries[3].label).toBe('Snack');
  });

  it('groupPoolMeals yields only non-empty sections with plural labels', () => {
    const sections = groupPoolMeals(pool, '151');
    expect(sections.map(s => s.slot)).toEqual(['breakfast', 'dinner', 'snack']);
    expect(sections.map(s => s.label)).toEqual(['Snídaně', 'Večeře', 'Snacky']);
    expect(sections[1].entries.map(e => e.meal.name)).toEqual(['Guláš', 'Řízek']);
    expect(POOL_SECTION_LABELS.lunch).toBe('Obědy');
  });

  it('poolTotals counts cooked and averages kcal over mains only', () => {
    const t = poolTotals(pool, '151', new Set(['151:dinner:1', '151:snack:0']));
    expect(t).toEqual({ cooked: 2, total: 4, avgMainKcal: 567 });
  });

  it('poolTotals with no mains has avgMainKcal 0', () => {
    expect(poolTotals([pool[3]], '151', new Set()).avgMainKcal).toBe(0);
  });
});

describe('parseNutrition basis', () => {
  it('divides whole-recipe totals by servings', () => {
    expect(parseNutrition({ calories: 575, protein: '30g', carbs: '40g', fat: '20g', basis: 'total', servings: 2 }))
      .toEqual({ kcal: 288, protein: 15, carbs: 20, fat: 10 });
  });
  it('leaves legacy and per-portion rows unchanged', () => {
    expect(parseNutrition({ calories: 600, protein: '30g' }).kcal).toBe(600);
    expect(parseNutrition({ calories: 600, basis: 'portion', servings: 2 }).kcal).toBe(600);
  });
});
