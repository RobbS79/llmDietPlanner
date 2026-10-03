import { describe, it, expect, vi } from 'vitest';
import { exportPlanAsText } from './PlanView';

describe('exportPlanAsText nutrition', () => {
  it('prints labelled per-portion rows, not raw meta keys', async () => {
    let blob: Blob | undefined;
    (URL as any).createObjectURL = vi.fn((b: Blob) => { blob = b; return 'blob:x'; });
    (URL as any).revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const meal = {
      name: 'Guláš', slot: 'dinner', index: 0, meal_identifier: '1:dinner:0',
      nutritional_info: { calories: 600, protein: '30g', carbs: '40g', fat: '20g', basis: 'total', servings: 2 },
    };
    exportPlanAsText({ id: 1, city: 'Praha', counts: { dinner: 1 } }, { meals: [meal] });
    const text = await new Promise<string>((res) => {
      const r = new FileReader();
      r.onload = () => res(String(r.result));
      r.readAsText(blob!);
    });
    expect(text).toContain('Energie: 300 kcal');
    expect(text).not.toMatch(/basis|servings/);
  });
});
