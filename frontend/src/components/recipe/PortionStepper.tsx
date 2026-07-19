import { Minus, Plus } from 'lucide-react';
import { czechPlural, PORTION_FORMS } from '@/lib/portions';

export const MIN_PORTIONS = 1;
export const MAX_PORTIONS = 20;

interface PortionStepperProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  /** 'app' (default) = dark auth-app surface; 'paper' = light public surface. */
  variant?: 'app' | 'paper';
}

// 44×44px buttons — the minimum comfortable touch target on mobile.
const btnApp =
  'w-11 h-11 flex items-center justify-center rounded-xl bg-card border border-line ' +
  'text-ink transition-colors hover:border-green/40 hover:text-green-mid ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/50 ' +
  'disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-line disabled:hover:text-ink';

const btnPaper =
  'w-11 h-11 flex items-center justify-center rounded-xl bg-card border border-line ' +
  'text-ink transition-colors hover:border-green hover:text-green ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/50 ' +
  'disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:border-line disabled:hover:text-ink';

export const PortionStepper = ({
  value,
  onChange,
  min = MIN_PORTIONS,
  max = MAX_PORTIONS,
  variant = 'app',
}: PortionStepperProps) => {
  const canDecrement = value > min;
  const canIncrement = value < max;
  const paper = variant === 'paper';
  const btn = paper ? btnPaper : btnApp;
  const valueCls = paper
    ? 'min-w-[5.5rem] text-center text-sm font-price font-bold text-ink tabular-nums'
    : 'min-w-[5.5rem] text-center text-sm font-black uppercase tracking-tighter italic text-ink tabular-nums';

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
        className={valueCls}
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
