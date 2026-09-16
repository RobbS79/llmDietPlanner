/**
 * One place that knows how a plan day is laid out.
 *
 * A day has three dict slots (breakfast / lunch / dinner) and two list slots
 * (small_meals / snacks). Until 2026-09-16 the plan view only drew the dict
 * slots, so everything a user configured under "Svačinky" was generated,
 * stored and never shown (plan 150). Every consumer of a day — cards, daily
 * totals, cooked counter, export — should iterate this instead of hard-coding
 * the three main keys.
 *
 * Identifier contract (mirrors diet_planner.views._parse_meal_identifier):
 *   <goal>:<day>:<breakfast|lunch|dinner>:0
 *   <goal>:<day>:small_meal:<index>
 *   <goal>:<day>:snack:<index>
 */

export const MEAL_SLOT_LABELS: Record<string, string> = {
  breakfast: 'Snídaně',
  lunch: 'Oběd',
  dinner: 'Večeře',
  small_meal: 'Svačina',
  snack: 'Snack',
};

const MAIN_SLOTS = ['breakfast', 'lunch', 'dinner'] as const;
const LIST_SLOTS: { key: string; slot: string }[] = [
  { key: 'small_meals', slot: 'small_meal' },
  { key: 'snacks', slot: 'snack' },
];

export interface DayMealEntry {
  /** Slot type as used in the identifier (lunch, small_meal, …). */
  slot: string;
  /** Stable React key within the day. */
  key: string;
  /** Czech badge text. */
  label: string;
  /** Whether this is one of the three main courses. */
  isMain: boolean;
  meal: any;
  mealId: string;
}

export function dayMealEntries(day: any, goalId: string | number): DayMealEntry[] {
  if (!day) return [];
  const out: DayMealEntry[] = [];
  for (const slot of MAIN_SLOTS) {
    const meal = day[slot];
    if (!meal) continue;
    out.push({
      slot, key: slot, label: MEAL_SLOT_LABELS[slot], isMain: true, meal,
      mealId: meal.meal_identifier || `${goalId}:${day.day_number}:${slot}:0`,
    });
  }
  for (const { key, slot } of LIST_SLOTS) {
    const items = Array.isArray(day[key]) ? day[key] : [];
    items.forEach((meal: any, i: number) => {
      if (!meal) return;
      out.push({
        slot, key: `${slot}:${i}`, label: MEAL_SLOT_LABELS[slot], isMain: false, meal,
        mealId: meal.meal_identifier || `${goalId}:${day.day_number}:${slot}:${i}`,
      });
    });
  }
  return out;
}
