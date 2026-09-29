import { PoolSection } from '@/lib/planMeals';
import { MealRow } from './MealRow';

interface SlotSectionProps {
  section: PoolSection;
  /** How many the user asked for in this slot (heading shows "x z y" when short). */
  requested: number;
  cookedSet: Set<string>;
  onOpen: (mealId: string, chat: boolean) => void;
  onToggleCooked: (mealId: string, isCooked: boolean, mealName: string) => void;
}

/** One slot of the pool: "Večeře · 5" plus its meals. Mains are cards,
 *  small meals and snacks compact rows. Anchor id `slot-<slot>`. */
export const SlotSection = ({ section, requested, cookedSet, onOpen, onToggleCooked }: SlotSectionProps) => {
  const got = section.entries.length;
  const short = requested > got;
  const cooked = section.entries.filter(e => cookedSet.has(e.mealId)).length;
  return (
    <section id={`slot-${section.slot}`} className="scroll-mt-24 bg-card border border-line rounded-3xl p-5 sm:p-8 text-left">
      <header className="flex flex-wrap items-baseline gap-x-6 gap-y-2 mb-6">
        <h2 className="font-display text-3xl font-black text-ink uppercase tracking-tighter italic leading-none">
          {section.label} · {short ? `${got} z ${requested}` : got}
        </h2>
        <span className="ml-auto text-[10px] font-black uppercase tracking-[0.2em] text-muted">{cooked}/{got} uvařeno</span>
      </header>
      {short && (
        // EN: "We only found N of M. Try a different request, or ask the chef chat for more."
        <p className="mb-6 text-sm font-medium text-paprika-strong bg-paprika-soft border border-paprika/30 rounded-xl px-4 py-3">
          Našli jsme jen {got} z {requested}. Zkuste jiné zadání, nebo si nechte poradit v chatu s kuchařkou u některého receptu.
        </p>
      )}
      {section.isMain ? (
        <div className="grid gap-4">
          {section.entries.map(e => (
            <MealRow key={e.key} entry={e} variant="main" isCooked={cookedSet.has(e.mealId)} onOpen={onOpen} onToggleCooked={onToggleCooked} />
          ))}
        </div>
      ) : (
        <ul className="grid gap-2">
          {section.entries.map(e => (
            <MealRow key={e.key} entry={e} variant="small" isCooked={cookedSet.has(e.mealId)} onOpen={onOpen} onToggleCooked={onToggleCooked} />
          ))}
        </ul>
      )}
    </section>
  );
};
