import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { PortionStepper } from './PortionStepper';
import { formatScaledIngredient, type IngredientInput } from '@/lib/portions';

interface RecipeIngredientsProps {
  ingredients: Array<IngredientInput | string> | null | undefined;
  baseServings: number | null | undefined;
  /** 'app' (default) = dark auth-app surface; 'paper' = light public surface. */
  variant?: 'app' | 'paper';
}

// Recipe quantities sometimes arrive as numeric strings ("200", "1,5").
// Coerce those so they scale; leave non-numeric values for the helper to
// pass through as quantity-less ("to taste") rows.
function coerceQuantity(quantity: IngredientInput['quantity']): number | string | null {
  if (typeof quantity !== 'string') return quantity;
  const parsed = parseFloat(quantity.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : quantity;
}

export const RecipeIngredients = ({ ingredients, baseServings, variant = 'app' }: RecipeIngredientsProps) => {
  const base = baseServings && baseServings > 0 ? baseServings : 1;
  const [chosen, setChosen] = useState(base);
  const list = ingredients || [];
  const paper = variant === 'paper';

  const headingCls = paper
    ? 'font-display text-lg font-bold text-ink mb-6 pb-4 border-b border-line'
    : 'text-lg font-black text-white uppercase tracking-tighter italic mb-6 pb-4 border-b border-slate-600';
  const eyebrowCls = paper
    ? 'text-[11px] font-bold text-muted uppercase tracking-[0.12em]'
    : 'text-[9px] font-black text-zinc-400 uppercase tracking-widest italic';
  const dotCls = paper ? 'bg-green' : 'bg-emerald-500';
  const textCls = paper ? 'text-ink' : 'text-zinc-300';
  const nameCls = paper ? 'font-bold text-ink' : 'font-bold text-white';
  const amountCls = paper ? 'text-muted ml-1' : 'text-zinc-300 ml-1';
  const optionalCls = paper ? 'text-muted italic ml-1' : 'text-zinc-400 italic ml-1';

  return (
    <Card variant={variant} className="p-8 md:col-span-1 text-left h-fit md:sticky md:top-10">
      <h2 className={headingCls}>
        Ingredience
      </h2>

      <div className="mb-6 flex flex-col gap-2">
        <span className={eyebrowCls}>
          Počet porcí
        </span>
        <PortionStepper value={chosen} onChange={setChosen} variant={variant} />
      </div>

      <ul className="space-y-3">
        {list.map((ing, idx) => {
          if (typeof ing === 'string') {
            return (
              <li key={idx} className="flex items-start gap-3 text-sm">
                <span className={`w-1.5 h-1.5 rounded-full ${dotCls} mt-2 shrink-0`} />
                <span className={textCls}>{ing}</span>
              </li>
            );
          }
          const scaled = formatScaledIngredient(
            { ...ing, quantity: coerceQuantity(ing.quantity) },
            base,
            chosen,
          );
          return (
            <li key={idx} className="flex items-start gap-3 text-sm">
              <span className={`w-1.5 h-1.5 rounded-full ${dotCls} mt-2 shrink-0`} />
              <span className={textCls}>
                <span className={nameCls}>{scaled.name}</span>
                {scaled.amountLabel && (
                  <span className={amountCls}>— {scaled.amountLabel}</span>
                )}
                {scaled.optional && (
                  <span className={optionalCls}>(volitelné)</span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
};
