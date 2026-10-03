import { dayMealEntries, dayTotals, parseNutrition, PlanDay, PlanMeal } from '@/lib/planMeals';
import { MealRow } from './MealRow';

interface DayCardProps {
  day: PlanDay;
  goalId: string | number;
  cookedSet: Set<string>;
  /** Open the meal's recipe page; `chat` = jump straight into the chef chat. */
  onOpen: (mealId: string, chat: boolean) => void;
  onToggleCooked: (mealId: string, isCooked: boolean, mealName: string) => void;
}

/**
 * One day = one card, three tiers. Mains get a medium card with a thumbnail,
 * side line, time and kcal; small meals are compact rows; snacks are chips.
 * Before this (plan 150, 2026-09-16) every meal — an apple included — was a
 * full-width hero card, 28 of them on a week plan, and no day had a total.
 */
export const DayCard = ({ day, goalId, cookedSet, onOpen, onToggleCooked }: DayCardProps) => {
  const entries = dayMealEntries(day, goalId);
  const mains = entries.filter(e => e.isMain);
  const smalls = entries.filter(e => e.slot === 'small_meal');
  const snacks = entries.filter(e => e.slot === 'snack');
  const totals = dayTotals(day, goalId);
  const cooked = entries.filter(e => cookedSet.has(e.mealId)).length;

  const kcalOf = (meal: PlanMeal) => parseNutrition(meal.nutritional_info, meal).kcal;

  return (
    <section id={`den-${day.day_number}`} className="scroll-mt-24 bg-card border border-line rounded-3xl p-5 sm:p-8 text-left">
      <header className="flex flex-wrap items-baseline gap-x-6 gap-y-2 mb-6">
        <h2 className="font-display text-3xl font-black text-ink uppercase tracking-tighter italic leading-none">Den {day.day_number}</h2>
        <span className="text-sm font-black text-ink tabular-nums">{totals.kcal} kcal</span>
        <span className="text-sm font-bold text-muted tabular-nums">{totals.protein} g bílkovin</span>
        <span className="ml-auto text-[10px] font-black uppercase tracking-[0.2em] text-muted">{cooked}/{entries.length} uvařeno</span>
      </header>

      <div className="grid gap-4">
        {mains.map(e => <MealRow key={e.key} entry={e} variant="main" isCooked={cookedSet.has(e.mealId)} onOpen={onOpen} onToggleCooked={onToggleCooked} />)}
      </div>

      {smalls.length > 0 && (
        <ul className="mt-5 grid gap-2">
          {smalls.map(e => <MealRow key={e.key} entry={e} variant="small" isCooked={cookedSet.has(e.mealId)} onOpen={onOpen} onToggleCooked={onToggleCooked} />)}
        </ul>
      )}

      {snacks.length > 0 && (
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <span className="text-[9px] font-black uppercase tracking-[0.2em] text-muted mr-1">Snack</span>
          {snacks.map(({ key, meal, mealId }) => (
            <button
              key={key} type="button" data-testid={`snack-${mealId}`} onClick={() => onOpen(mealId, false)}
              className="px-3 py-1.5 rounded-full border border-line bg-paper text-xs font-bold text-ink hover:border-green/40 hover:text-green transition-colors"
            >
              {meal.name}{kcalOf(meal) > 0 && <span className="text-muted font-black tabular-nums"> · {kcalOf(meal)} kcal</span>}
            </button>
          ))}
        </div>
      )}
    </section>
  );
};
