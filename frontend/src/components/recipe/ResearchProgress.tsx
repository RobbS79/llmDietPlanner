import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { ResearchJobStatus } from '@/lib/refineRecipe';

/** The three stages the backend actually publishes. No fourth invented one,
 * and no percentage bar — we cannot know how far through `searching` a job is,
 * and a bar stalled at 70% is worse than no bar at all. */
const STAGES: { key: ResearchJobStatus; step: string; sentence: string }[] = [
  { key: 'queued', step: 'zadáno', sentence: 'Chystám hledání…' },
  { key: 'searching', step: 'hledám', sentence: 'Hledám recepty na webu…' },
  { key: 'curating', step: 'čtu recept', sentence: 'Čtu nalezený recept a přepočítávám porce…' },
];

const SLOW_AFTER_MS = 90_000;

const mmss = (ms: number) => {
  const total = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
};

interface ResearchProgressProps {
  status: ResearchJobStatus;
  startedAt: number;
  onCancel: () => void;
}

export const ResearchProgress = ({ status, startedAt, onCancel }: ResearchProgressProps) => {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  const elapsed = now - startedAt;
  const activeIdx = Math.max(0, STAGES.findIndex((s) => s.key === status));

  return (
    <div className="mr-8 mb-4 rounded-xl border border-line bg-paper px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        {/* Only the stage sentence is announced; a per-second counter in a live
            region would flood a screen reader. */}
        <p role="status" aria-live="polite" className="flex items-center gap-2 text-sm text-muted">
          <Loader2 size={14} className="shrink-0 animate-spin text-green" />
          {STAGES[activeIdx].sentence}
        </p>
        <span aria-hidden="true" className="shrink-0 text-xs font-semibold tabular-nums text-muted">
          {mmss(elapsed)}
        </span>
      </div>

      <ol aria-hidden="true" className="mt-3 flex items-center gap-2">
        {STAGES.map((s, i) => (
          <li key={s.key} className="flex flex-1 items-center gap-2">
            <span
              className={`h-2 w-2 shrink-0 rounded-full ${i <= activeIdx ? 'bg-green' : 'bg-line'}`}
            />
            <span
              className={`text-[10px] font-black uppercase tracking-widest ${i <= activeIdx ? 'text-green' : 'text-muted'}`}
            >
              {s.step}
            </span>
          </li>
        ))}
      </ol>

      <p className="mt-3 text-xs leading-relaxed text-muted">
        {elapsed >= SLOW_AFTER_MS
          ? 'Ještě hledám, tenhle je oříšek.'
          : 'Trvá to obvykle minutu až dvě. Klidně mezitím dělejte něco jiného — recept se objeví tady v chatu, i když se sem vrátíte později.'}
      </p>

      <button
        type="button"
        onClick={onCancel}
        className="mt-2 text-xs font-semibold text-muted underline underline-offset-2 hover:text-green"
      >
        Zrušit hledání
      </button>
    </div>
  );
};
