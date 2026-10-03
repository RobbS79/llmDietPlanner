import { ChefHat, ChevronRight, MessageCircle, Timer } from 'lucide-react';
import { getFoodImageUrl } from '@/lib/food-image';
import { parseNutrition, DayMealEntry } from '@/lib/planMeals';
import { MealSideLine } from '@/components/recipe/MealSideLine';

export interface MealRowProps {
  entry: DayMealEntry;
  /** main = medium card with thumbnail; small = compact row. small renders an `<li>`; the caller must wrap rows in `<ul>`/`<ol>`. */
  variant: 'main' | 'small';
  isCooked: boolean;
  onOpen: (mealId: string, chat: boolean) => void;
  onToggleCooked: (mealId: string, isCooked: boolean, mealName: string) => void;
}

const hideImg = (e: React.SyntheticEvent<HTMLImageElement>) => { (e.target as HTMLImageElement).style.display = 'none'; };

/** One meal, shared by the legacy DayCard and the pool SlotSection. */
export const MealRow = ({ entry, variant, isCooked, onOpen, onToggleCooked }: MealRowProps) => {
  const { meal, mealId, label } = entry;
  const kcal = parseNutrition(meal.nutritional_info, meal).kcal;

  if (variant === 'small') {
    return (
      <li data-testid={`small-${mealId}`} data-cooked={isCooked}>
        <button
          type="button" onClick={() => onOpen(mealId, false)}
          className={`w-full flex items-center gap-4 px-3 py-2.5 rounded-xl border text-left transition-colors ${isCooked ? 'bg-green-soft border-green/40' : 'bg-paper border-line hover:border-green/40'}`}
        >
          <img src={getFoodImageUrl(meal.food_category, meal.name)} alt="" loading="lazy" className="w-12 h-12 rounded-lg object-cover bg-kraft shrink-0" onError={hideImg} />
          <span className="text-[9px] font-black uppercase tracking-[0.2em] text-green w-16 shrink-0">{label}</span>
          <span className={`flex-1 font-bold text-sm ${isCooked ? 'text-muted line-through' : 'text-ink'}`}>{meal.name}</span>
          {kcal > 0 && <span className="text-[10px] font-black text-ink tabular-nums">{kcal} kcal</span>}
          <span className="hidden sm:flex items-center gap-1 text-[10px] font-black text-muted uppercase tracking-widest w-16 justify-end"><Timer size={11} className="text-green" /> {meal.preparation_time || 20} min</span>
          <ChevronRight size={14} className="text-muted shrink-0" />
        </button>
      </li>
    );
  }

  return (
    <article
      data-testid={`main-${mealId}`} data-cooked={isCooked}
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
          <span className="text-[10px] font-black text-ink tabular-nums">{kcal} kcal</span>
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
