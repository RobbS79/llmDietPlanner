import { describe, it, expect } from 'vitest';
import { normalizeNutrition, nutritionBasisFor } from './nutrition';

describe('nutritionBasisFor', () => {
  it('treats a curated-sourced recipe as whole-recipe totals', () => {
    expect(nutritionBasisFor({ curated_recipe_slug: 'domaci-bramborove-halusky' })).toBe('total');
  });

  it('leaves LLM-authored meals with no declared basis', () => {
    expect(nutritionBasisFor({ curated_recipe_slug: '' })).toBeUndefined();
    expect(nutritionBasisFor({})).toBeUndefined();
    expect(nutritionBasisFor(null)).toBeUndefined();
  });
});

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

  describe('with an explicit "total" basis (curated recipes)', () => {
    // Curated meals carry nutrition covering ALL `servings` portions, and the
    // backend knows it. Without that basis the plausibility heuristic keeps a
    // multi-portion total whenever it happens to look like a believable single
    // portion — which is the common case, not an edge case.
    it('divides a plausible-looking total that is really N portions', () => {
      // Prod recipe 175 "Domácí bramborové halušky": base 1233 kcal / 4 portions,
      // served as 2 portions → 616 kcal displayed as "na porci". True value 308.
      const rows = normalizeNutrition(
        { calories: 616, protein: '20g', carbs: '119g', fat: '5g' },
        2,
        'total',
      );
      expect(rows?.find((r) => r.key === 'calories')?.value).toBe(308);
      expect(rows?.find((r) => r.key === 'protein')?.value).toBe(10);
      expect(rows?.find((r) => r.key === 'carbs')?.value).toBe(60);
      expect(rows?.find((r) => r.key === 'fat')?.value).toBe(2.5);
    });

    it('leaves a single-portion total untouched', () => {
      const rows = normalizeNutrition({ calories: 529, protein: '21g' }, 1, 'total');
      expect(rows?.find((r) => r.key === 'calories')?.value).toBe(529);
      expect(rows?.find((r) => r.key === 'protein')?.value).toBe(21);
    });

    it('still hides the card when the per-portion result is implausible', () => {
      expect(normalizeNutrition({ calories: 9000 }, 2, 'total')).toBeNull();
    });

    it('divides even when the total alone would have passed the heuristic', () => {
      // 1200 kcal over 3 portions: plausible as-is, so the heuristic would keep
      // it. The known basis must win over the guess.
      const rows = normalizeNutrition({ calories: 1200 }, 3, 'total');
      expect(rows?.find((r) => r.key === 'calories')?.value).toBe(400);
    });
  });
});
