import { describe, it, expect } from 'vitest';
import {
  scaleAmount,
  czechPlural,
  pluralizeUnit,
  roundForUnit,
  formatNumber,
  formatScaledIngredient,
  PORTION_FORMS,
} from './portions';

describe('scaleAmount', () => {
  it('scales linearly', () => {
    expect(scaleAmount(100, 4, 8)).toBe(200);
    expect(scaleAmount(100, 4, 2)).toBe(50);
  });
  it('treats non-positive base servings as 1', () => {
    expect(scaleAmount(100, 0, 3)).toBe(300);
  });
});

describe('czechPlural', () => {
  it('picks the right form', () => {
    expect(czechPlural(1, PORTION_FORMS)).toBe('porce');
    expect(czechPlural(3, PORTION_FORMS)).toBe('porce');
    expect(czechPlural(5, PORTION_FORMS)).toBe('porcí');
    expect(czechPlural(0, PORTION_FORMS)).toBe('porcí');
  });
});

describe('pluralizeUnit', () => {
  it('passes metric/unknown units through verbatim', () => {
    expect(pluralizeUnit(3, 'kg')).toBe('kg');
    expect(pluralizeUnit(3, 'g')).toBe('g');
    expect(pluralizeUnit(3, 'ks')).toBe('ks');
  });
  it('inflects known counted units for integers', () => {
    expect(pluralizeUnit(1, 'lžíce')).toBe('lžíce');
    expect(pluralizeUnit(5, 'lžíce')).toBe('lžic');
    expect(pluralizeUnit(5, 'vejce')).toBe('vajec');
  });
  it('uses the few-form for fractional amounts', () => {
    expect(pluralizeUnit(0.5, 'lžíce')).toBe('lžíce');
  });
  it('returns empty string for missing unit', () => {
    expect(pluralizeUnit(2, null)).toBe('');
  });
});

describe('roundForUnit', () => {
  it('rounds by unit family', () => {
    expect(roundForUnit(80.4, 'g')).toBe(80);
    expect(roundForUnit(0.3000004, 'kg')).toBe(0.3);
    expect(roundForUnit(1.24, 'ks')).toBe(1);
    expect(roundForUnit(1.3, 'ks')).toBe(1.5);
  });
});

describe('formatNumber', () => {
  it('uses a Czech decimal comma and trims zeros', () => {
    expect(formatNumber(0.5)).toBe('0,5');
    expect(formatNumber(80)).toBe('80');
    expect(formatNumber(1.5)).toBe('1,5');
  });
});

describe('formatScaledIngredient', () => {
  it('scales, rounds, and labels with unit', () => {
    const r = formatScaledIngredient(
      { name: 'brambory', quantity: 300, unit: 'kg' }, 4, 8,
    );
    expect(r.name).toBe('brambory');
    expect(r.amountLabel).toBe('600 kg');
  });
  it('returns a null amountLabel for to-taste ingredients', () => {
    const r = formatScaledIngredient(
      { name: 'sůl', quantity: null, unit: null }, 4, 8,
    );
    expect(r.amountLabel).toBeNull();
  });
  it('omits the unit when there is none', () => {
    const r = formatScaledIngredient(
      { name: 'vejce', quantity: 2, unit: '' }, 4, 8,
    );
    expect(r.amountLabel).toBe('4');
  });
});
