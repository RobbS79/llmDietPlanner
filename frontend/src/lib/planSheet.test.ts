import { describe, it, expect } from 'vitest';
import { countsFor, goalPrompt } from './planSheet';

describe('plan sheet mapping', () => {
  it('maps the count answer onto pool counts', () => {
    expect(countsFor('5 večeří')).toEqual({ breakfasts: 0, lunches: 0, dinners: 5, small_meals: 0, snacks: 0 });
    expect(countsFor('5 obědů a 5 večeří')).toEqual({ breakfasts: 0, lunches: 5, dinners: 5, small_meals: 0, snacks: 0 });
    expect(countsFor('Nastavím si sám')).toBeNull();
  });

  it('builds the prompt from the goal chip and the search', () => {
    expect(goalPrompt('Chci zhubnout', 'kuřecí prsa')).toBe('Chci zhubnout. kuřecí prsa');
    expect(goalPrompt(null, '')).toBe('Jen ať nemusím vymýšlet');
    expect(goalPrompt(null, 'keto')).toBe('keto. Jen ať nemusím vymýšlet');
  });
});
