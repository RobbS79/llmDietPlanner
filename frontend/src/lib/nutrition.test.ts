import { describe, it, expect } from 'vitest';
import { normalizeNutrition } from './nutrition';

describe('normalizeNutrition', () => {
  it('maps English LLM keys to Czech labels in display order', () => {
    const rows = normalizeNutrition(
      { fat: '20g', calories: 550, protein: '35g', carbs: '48g' },
      1,
    );
    expect(rows?.map((r) => r.label)).toEqual(['Energie', 'Bílkoviny', 'Sacharidy', 'Tuky']);
    expect(rows?.[0]).toMatchObject({ value: 550, unit: 'kcal' });
    expect(rows?.[3]).toMatchObject({ value: 20, unit: 'g' });
  });

  it('parses noisy string values ("5 286 kcal", "1,5")', () => {
    const rows = normalizeNutrition({ calories: '1 250 kcal', fat: '1,5' }, 1);
    expect(rows).toEqual([
      { key: 'calories', label: 'Energie', value: 1250, unit: 'kcal' },
      { key: 'fat', label: 'Tuky', value: 1.5, unit: 'g' },
    ]);
  });

  it('divides per-recipe totals down to per-portion when that makes them plausible', () => {
    // Parmigiana case: 2008 kcal across 4 servings → 502 kcal / portion.
    const rows = normalizeNutrition({ calories: 2008, protein: '120g' }, 4);
    expect(rows?.find((r) => r.key === 'calories')?.value).toBe(502);
    expect(rows?.find((r) => r.key === 'protein')?.value).toBe(30);
  });

  it('hides the card entirely when values are implausible and cannot be rescued', () => {
    // Halušky case: 5286 kcal claimed for "1 porce" — no serving count to divide by.
    expect(normalizeNutrition({ calories: 5286, fat: '128g', carbs: '800g' }, 1)).toBeNull();
    // Dividing does not help either (still >1500 kcal per portion).
    expect(normalizeNutrition({ calories: 9000 }, 2)).toBeNull();
  });

  it('ignores unknown keys and returns null when nothing is recognized', () => {
    expect(normalizeNutrition({ fiber: '12g', sodium: '1g' }, 2)).toBeNull();
    expect(normalizeNutrition(null, 2)).toBeNull();
    expect(normalizeNutrition({}, 2)).toBeNull();
  });

  it('recognizes Czech keys too', () => {
    const rows = normalizeNutrition({ 'Bílkoviny': '30 g', 'sacharidy': 60, 'energie': 480 }, 1);
    expect(rows?.map((r) => r.key)).toEqual(['calories', 'protein', 'carbs']);
  });

  it('rejects non-positive values instead of displaying them', () => {
    expect(normalizeNutrition({ calories: 0 }, 1)).toBeNull();
    expect(normalizeNutrition({ protein: -5 }, 1)).toBeNull();
  });
});
