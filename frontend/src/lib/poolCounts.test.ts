import { describe, it, expect } from 'vitest';
import { countLabel, mealsLabel, poolSummary } from './poolCounts';

describe('Czech count labels', () => {
  it('declines each slot noun', () => {
    expect(countLabel('breakfast', 1)).toBe('1 snídaně');
    expect(countLabel('breakfast', 3)).toBe('3 snídaně');
    expect(countLabel('breakfast', 5)).toBe('5 snídaní');
    expect(countLabel('lunch', 1)).toBe('1 oběd');
    expect(countLabel('lunch', 2)).toBe('2 obědy');
    expect(countLabel('lunch', 7)).toBe('7 obědů');
    expect(countLabel('dinner', 1)).toBe('1 večeře');
    expect(countLabel('dinner', 4)).toBe('4 večeře');
    expect(countLabel('dinner', 5)).toBe('5 večeří');
    expect(countLabel('small_meal', 1)).toBe('1 svačina');
    expect(countLabel('small_meal', 3)).toBe('3 svačiny');
    expect(countLabel('small_meal', 6)).toBe('6 svačin');
    expect(countLabel('snack', 1)).toBe('1 snack');
    expect(countLabel('snack', 2)).toBe('2 snacky');
    expect(countLabel('snack', 9)).toBe('9 snacků');
  });

  it('mealsLabel declines jídlo', () => {
    expect(mealsLabel(1)).toBe('1 jídlo');
    expect(mealsLabel(3)).toBe('3 jídla');
    expect(mealsLabel(13)).toBe('13 jídel');
    expect(mealsLabel(0)).toBe('0 jídel');
  });

  it('poolSummary joins non-zero slots in slot order', () => {
    expect(poolSummary({ breakfast: 0, lunch: 2, dinner: 5, small_meal: 0, snack: 1 }))
      .toBe('2 obědy · 5 večeří · 1 snack');
    expect(poolSummary({ breakfast: 0, lunch: 0, dinner: 0, small_meal: 0, snack: 0 })).toBe('0 jídel');
  });
});
