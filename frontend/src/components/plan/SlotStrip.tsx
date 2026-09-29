import { PoolSection } from '@/lib/planMeals';

/** Sticky nav for a pool plan: one pill per non-empty slot (`#slot-<slot>`). */
export const SlotStrip = ({ sections }: { sections: PoolSection[] }) => {
  if (!sections?.length) return null;
  return (
    <nav aria-label="Jídla v plánu" className="sticky top-0 z-20 -mx-6 px-6 py-3 bg-paper/95 backdrop-blur border-b border-line mb-10">
      <ul className="flex gap-2 overflow-x-auto [scrollbar-width:none]">
        {sections.map((s) => (
          <li key={s.slot} className="shrink-0">
            <a href={`#slot-${s.slot}`} className="flex flex-col items-center px-4 py-2 rounded-xl bg-card border border-line hover:border-green/40 hover:text-green transition-colors">
              <span className="text-[10px] font-black uppercase tracking-[0.2em] text-muted">{s.label}</span>
              <span className="text-sm font-black text-ink tabular-nums">{s.entries.length}</span>
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
};
