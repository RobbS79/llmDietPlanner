import { dayTotals, PlanDay } from '@/lib/planMeals';

/**
 * The whole plan at a glance: one pill per day with its kcal, each an anchor
 * to that day's card (`#den-N`). Sticky under the app header so the user can
 * jump between days without scrolling past every card.
 */
export const WeekStrip = ({ days, goalId }: { days: PlanDay[]; goalId: string | number }) => {
  if (!days?.length) return null;
  return (
    <nav aria-label="Dny plánu" className="sticky top-0 z-20 -mx-6 px-6 py-3 bg-paper/95 backdrop-blur border-b border-line mb-10">
      <ul className="flex gap-2 overflow-x-auto [scrollbar-width:none]">
        {days.map((day) => {
          const t = dayTotals(day, goalId);
          return (
            <li key={day.day_number} className="shrink-0">
              <a
                href={`#den-${day.day_number}`}
                className="flex flex-col items-center px-4 py-2 rounded-xl bg-card border border-line hover:border-green/40 hover:text-green transition-colors"
              >
                <span className="text-[10px] font-black uppercase tracking-[0.2em] text-muted">Den {day.day_number}</span>
                <span className="text-sm font-black text-ink tabular-nums">{t.kcal} kcal</span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
};
