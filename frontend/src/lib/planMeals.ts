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

/** A meal as stored in DietaryPlan.days (LLM output, so every field is optional). */
export interface PlanMeal {
  name: string;
  meal_identifier?: string;
  description?: string;
  food_category?: string;
  preparation_time?: number | null;
  nutritional_info?: Record<string, unknown> | null;
  side?: { key: string; name_cs: string; with_cs: string; display: string } | null;
  [extra: string]: unknown;
}

export interface PlanDay {
  day_number: number;
  breakfast?: PlanMeal | null;
  lunch?: PlanMeal | null;
  dinner?: PlanMeal | null;
  small_meals?: PlanMeal[] | null;
  snacks?: PlanMeal[] | null;
}

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
  meal: PlanMeal;
  mealId: string;
}

export interface Nutrition { kcal: number; protein: number; carbs: number; fat: number }

/** Tolerant reader for the LLM's nutritional_info shapes ("46g", "742 kcal", 742). */
export function parseNutrition(raw: unknown): Nutrition {
  if (!raw || typeof raw !== 'object') return { kcal: 0, protein: 0, carbs: 0, fat: 0 };
  const ni = raw as Record<string, unknown>;
  const parse = (v: unknown) => parseInt(String(v).replace(/[^\d]/g, '')) || 0;
  return {
    kcal: parse(ni.calories || ni.kcal || ni.Calories || ni.energy || 0),
    protein: parse(ni.protein || ni.Protein || 0),
    carbs: parse(ni.carbs || ni.carbohydrates || ni.Carbs || 0),
    fat: parse(ni.fat || ni.Fat || ni.fats || 0),
  };
}

/** Whole-day totals over every slot, mains and small dishes alike. */
export function dayTotals(day: PlanDay | null | undefined, goalId: string | number = ''): Nutrition {
  return dayMealEntries(day, goalId).reduce((acc, { meal }) => {
    const n = parseNutrition(meal.nutritional_info);
    return { kcal: acc.kcal + n.kcal, protein: acc.protein + n.protein, carbs: acc.carbs + n.carbs, fat: acc.fat + n.fat };
  }, { kcal: 0, protein: 0, carbs: 0, fat: 0 });
}

export function dayMealEntries(day: PlanDay | null | undefined, goalId: string | number): DayMealEntry[] {
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
    const raw = day[key as 'small_meals' | 'snacks'];
    const items: PlanMeal[] = Array.isArray(raw) ? raw : [];
    items.forEach((meal, i) => {
      if (!meal) return;
      out.push({
        slot, key: `${slot}:${i}`, label: MEAL_SLOT_LABELS[slot], isMain: false, meal,
        mealId: meal.meal_identifier || `${goalId}:${day.day_number}:${slot}:${i}`,
      });
    });
  }
  return out;
}
