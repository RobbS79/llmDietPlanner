import { ChefHat, ChevronRight, MessageCircle, Timer } from 'lucide-react';
import { getFoodImageUrl } from '@/lib/food-image';
import { dayMealEntries, dayTotals, parseNutrition, DayMealEntry, PlanDay, PlanMeal } from '@/lib/planMeals';
import { MealSideLine } from '@/components/recipe/MealSideLine';

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

  const kcalOf = (meal: PlanMeal) => parseNutrition(meal.nutritional_info).kcal;
  const hideImg = (e: React.SyntheticEvent<HTMLImageElement>) => { (e.target as HTMLImageElement).style.display = 'none'; };

  const renderMain = (entry: DayMealEntry) => {
    const { meal, mealId, label } = entry;
    const isCooked = cookedSet.has(mealId);
    return (
      <article
        key={entry.key} data-testid={`main-${mealId}`} data-cooked={isCooked}
        className={`grid sm:grid-cols-[200px_1fr] rounded-2xl border overflow-hidden transition-colors ${isCooked ? 'bg-green-soft border-green/40' : 'bg-card border-line hover:border-green/40'}`}
      >
        <button type="button" onClick={() => onOpen(mealId, false)} className="relative h-40 sm:h-full bg-kraft text-left" aria-label={`Otevřít recept ${meal.name}`}>
          <img src={getFoodImageUrl(meal.food_category, meal.name)} alt="" loading="lazy" className="w-full h-full object-cover" onError={hideImg} />
          <span className="absolute top-3 left-3 px-3 py-1 bg-green text-white rounded-lg text-[9px] font-black uppercase tracking-[0.25em] italic shadow">{label}</span>
        </button>
        <div className="p-5 sm:p-6 flex flex-col gap-3">
          <div className="cursor-pointer" onClick={() => onOpen(mealId, false)}>
            <h3 className={`font-display text-2xl font-black tracking-tight uppercase italic leading-tight ${isCooked ? 'text-muted line-through' : 'text-ink'}`}>{meal.name}</h3>
            <MealSideLine side={meal.side} />
            {meal.description && <p className="text-muted text-sm leading-relaxed line-clamp-2 italic">{meal.description}</p>}
          </div>
          <div className="mt-auto flex flex-wrap items-center gap-2 pt-3 border-t border-line">
            <span className="text-[10px] font-black text-ink tabular-nums">{kcalOf(meal)} kcal</span>
            <span className="flex items-center gap-1 text-[10px] font-black text-muted uppercase tracking-widest"><Timer size={12} className="text-green" /> {meal.preparation_time || 20} min</span>
            <span className="flex-1" />
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onToggleCooked(mealId, !isCooked, meal.name); }}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest border transition-all ${isCooked ? 'bg-green-soft border-green/40 text-green' : 'bg-paper border-line text-muted hover:border-green/40 hover:text-green-mid'}`}
            >
              <ChefHat size={12} /> {isCooked ? 'Uvařeno' : 'Označit jako uvařené'}
            </button>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onOpen(mealId, true); }}
              aria-label="Nesedí vám tohle jídlo? Otevřít chat s kuchařkou"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[9px] font-black uppercase tracking-widest border bg-paper border-line text-muted hover:border-green/40 hover:text-green-mid transition-all"
            >
              <MessageCircle size={12} /> Nesedí?
            </button>
          </div>
        </div>
      </article>
    );
  };

  const renderSmall = (entry: DayMealEntry) => {
    const { meal, mealId, label } = entry;
    const isCooked = cookedSet.has(mealId);
    return (
      <li key={entry.key} data-testid={`small-${mealId}`} data-cooked={isCooked}>
        <button
          type="button" onClick={() => onOpen(mealId, false)}
          className={`w-full flex items-center gap-4 px-3 py-2.5 rounded-xl border text-left transition-colors ${isCooked ? 'bg-green-soft border-green/40' : 'bg-paper border-line hover:border-green/40'}`}
        >
          <img src={getFoodImageUrl(meal.food_category, meal.name)} alt="" loading="lazy" className="w-12 h-12 rounded-lg object-cover bg-kraft shrink-0" onError={hideImg} />
          <span className="text-[9px] font-black uppercase tracking-[0.2em] text-green w-16 shrink-0">{label}</span>
          <span className={`flex-1 font-bold text-sm ${isCooked ? 'text-muted line-through' : 'text-ink'}`}>{meal.name}</span>
          {kcalOf(meal) > 0 && <span className="text-[10px] font-black text-ink tabular-nums">{kcalOf(meal)} kcal</span>}
          <span className="hidden sm:flex items-center gap-1 text-[10px] font-black text-muted uppercase tracking-widest w-16 justify-end"><Timer size={11} className="text-green" /> {meal.preparation_time || 20} min</span>
          <ChevronRight size={14} className="text-muted shrink-0" />
        </button>
      </li>
    );
  };

  return (
    <section id={`den-${day.day_number}`} className="scroll-mt-24 bg-card border border-line rounded-3xl p-5 sm:p-8 text-left">
      <header className="flex flex-wrap items-baseline gap-x-6 gap-y-2 mb-6">
        <h2 className="font-display text-3xl font-black text-ink uppercase tracking-tighter italic leading-none">Den {day.day_number}</h2>
        <span className="text-sm font-black text-ink tabular-nums">{totals.kcal} kcal</span>
        <span className="text-sm font-bold text-muted tabular-nums">{totals.protein} g bílkovin</span>
        <span className="ml-auto text-[10px] font-black uppercase tracking-[0.2em] text-muted">{cooked}/{entries.length} uvařeno</span>
      </header>

      <div className="grid gap-4">{mains.map(renderMain)}</div>

      {smalls.length > 0 && (
        <ul className="mt-5 grid gap-2">{smalls.map(renderSmall)}</ul>
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
