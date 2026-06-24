import { Minus, Plus } from 'lucide-react';
import { czechPlural, PORTION_FORMS } from '@/lib/portions';

export const MIN_PORTIONS = 1;
export const MAX_PORTIONS = 20;

interface PortionStepperProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
}

const btn =
  'w-9 h-9 flex items-center justify-center rounded-xl bg-slate-700 border border-slate-600 ' +
  'text-zinc-200 transition-colors hover:border-emerald-500/60 hover:text-emerald-400 ' +
  'disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-slate-600 disabled:hover:text-zinc-200';

export const PortionStepper = ({
  value,
  onChange,
  min = MIN_PORTIONS,
  max = MAX_PORTIONS,
}: PortionStepperProps) => {
  const canDecrement = value > min;
  const canIncrement = value < max;

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        aria-label="Méně porcí"
        disabled={!canDecrement}
        onClick={() => onChange(value - 1)}
        className={btn}
      >
        <Minus size={16} />
      </button>
      <span
        aria-live="polite"
        className="min-w-[5.5rem] text-center text-sm font-black uppercase tracking-tighter italic text-white tabular-nums"
      >
        {value} {czechPlural(value, PORTION_FORMS)}
      </span>
      <button
        type="button"
        aria-label="Více porcí"
        disabled={!canIncrement}
        onClick={() => onChange(value + 1)}
        className={btn}
      >
        <Plus size={16} />
      </button>
    </div>
  );
};
