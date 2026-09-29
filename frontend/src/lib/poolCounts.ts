/** Czech plural forms for pool counts. EN gloss: breakfast(s) / lunch(es) /
 *  dinner(s) / small meal(s) / snack(s) / meal(s). Forms: [1, 2–4, 5+/0]. */
export type PoolSlot = 'breakfast' | 'lunch' | 'dinner' | 'small_meal' | 'snack';
export type PoolCounts = Record<PoolSlot, number>;

export const POOL_SLOT_ORDER: PoolSlot[] = ['breakfast', 'lunch', 'dinner', 'small_meal', 'snack'];

const FORMS: Record<PoolSlot, [string, string, string]> = {
  breakfast: ['snídaně', 'snídaně', 'snídaní'],
  lunch: ['oběd', 'obědy', 'obědů'],
  dinner: ['večeře', 'večeře', 'večeří'],
  small_meal: ['svačina', 'svačiny', 'svačin'],
  snack: ['snack', 'snacky', 'snacků'],
};
const MEAL_FORMS: [string, string, string] = ['jídlo', 'jídla', 'jídel'];

function pick(n: number, forms: [string, string, string]): string {
  if (n === 1) return forms[0];
  if (n >= 2 && n <= 4) return forms[1];
  return forms[2];
}

export function countLabel(slot: PoolSlot, n: number): string {
  return `${n} ${pick(n, FORMS[slot])}`;
}

export function mealsLabel(n: number): string {
  return `${n} ${pick(n, MEAL_FORMS)}`;
}

/** "2 obědy · 5 večeří · 1 snack", or "0 jídel" when everything is zero. */
export function poolSummary(counts: Partial<PoolCounts> | null | undefined): string {
  const parts = POOL_SLOT_ORDER
    .filter(slot => (counts?.[slot] ?? 0) > 0)
    .map(slot => countLabel(slot, counts![slot]!));
  return parts.length ? parts.join(' · ') : mealsLabel(0);
}
