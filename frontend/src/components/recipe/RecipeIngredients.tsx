import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { PortionStepper } from './PortionStepper';
import { formatScaledIngredient, type IngredientInput } from '@/lib/portions';
import { fmtMoney, fmtRange, type ShoppingList, type RecipeDeals } from '@/lib/pricing';

interface RecipeIngredientsProps {
  ingredients: Array<IngredientInput | string> | null | undefined;
  baseServings: number | null | undefined;
  /** 'app' (default) = dark auth-app surface; 'paper' = light public surface. */
  variant?: 'app' | 'paper';
  /** Per-line priced shopping list (RecipeSerializer.shopping_list). Omit/null
   * to render the plain ingredient list with no prices. */
  shoppingList?: ShoppingList | null;
  /** Active leaflet deals (RecipeSerializer.deals) — matched lines get a
   * SLEVA chip alongside their price. */
  deals?: RecipeDeals | null;
}

// Recipe quantities sometimes arrive as numeric strings ("200", "1,5").
// Coerce those so they scale; leave non-numeric values for the helper to
// pass through as quantity-less ("to taste") rows.
function coerceQuantity(quantity: IngredientInput['quantity']): number | string | null {
  if (typeof quantity !== 'string') return quantity;
  const parsed = parseFloat(quantity.replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : quantity;
}

export const RecipeIngredients = ({
  ingredients,
  baseServings,
  variant = 'app',
  shoppingList = null,
  deals = null,
}: RecipeIngredientsProps) => {
  const base = baseServings && baseServings > 0 ? baseServings : 1;
  const [chosen, setChosen] = useState(base);
  const list = ingredients || [];
  const paper = variant === 'paper';
  // Prices rescale live with the portion stepper, exactly like quantities.
  const scale = chosen / base;
  const dealCanonicals = new Set((deals?.deals || []).map((d) => d.canonical));

  const headingCls = paper
    ? 'font-display text-lg font-bold text-ink mb-6 pb-4 border-b border-line'
    : 'font-display text-lg font-black text-ink uppercase tracking-tighter italic mb-6 pb-4 border-b border-line';
  const eyebrowCls = paper
    ? 'text-[11px] font-bold text-muted uppercase tracking-[0.12em]'
    : 'text-[9px] font-black text-muted uppercase tracking-widest italic';
  const textCls = paper ? 'text-ink' : 'text-ink';
  const amountCls = 'w-20 shrink-0 text-right font-price font-semibold text-ink tabular-nums';
  const dealChipCls = 'bg-paprika-soft text-paprika-strong font-bold text-[10px] px-1.5 py-0.5 rounded-md ml-1.5 uppercase tracking-wide align-middle';
  const priceCls = 'font-price font-bold text-ink ml-auto pl-3 shrink-0 whitespace-nowrap';
  const unpricedCls = 'text-muted italic ml-auto pl-3 shrink-0 whitespace-nowrap text-xs';
  const estimateTagCls = 'block text-right text-[9px] font-bold text-muted uppercase tracking-wide';
  const totalCls = paper
    ? 'font-price text-base font-bold text-ink'
    : 'font-price text-base font-bold text-ink';
  const coverageCls = 'text-[11px] text-muted';

  // Optional ingredients render in their own group below the required ones —
  // a "(volitelné)" suffix on every other row drowns the core ingredients on
  // topping-heavy recipes. Required keeps the original relative order, so the
  // running price index over non-optional rows still lines up with
  // shopping_list.lines (price_recipe_lines skips optional ingredients).
  const entries = list.map((ing, idx) => ({ ing, idx }));
  const requiredEntries = entries.filter((e) => typeof e.ing === 'string' || !e.ing.optional);
  const optionalEntries = entries.filter((e) => typeof e.ing !== 'string' && !!e.ing.optional);

  let priceIdx = -1;

  const renderRow = ({ ing, idx }: { ing: IngredientInput | string; idx: number }) => {
    if (typeof ing === 'string') {
      return (
        <li key={idx} className="flex items-baseline gap-3 text-sm">
          <span className={amountCls} aria-hidden="true" />
          <span className={`${textCls} flex-1 min-w-0`}>{ing}</span>
        </li>
      );
    }
    const isOptional = !!ing.optional;
    let line = undefined as ShoppingList['lines'][number] | undefined;
    if (!isOptional) {
      priceIdx += 1;
      line = shoppingList?.lines[priceIdx];
    }
    const scaled = formatScaledIngredient(
      { ...ing, quantity: coerceQuantity(ing.quantity) },
      base,
      chosen,
    );
    const isDeal = !!(line?.canonical && dealCanonicals.has(line.canonical));
    return (
      <li key={idx} className="flex items-baseline gap-3 text-sm">
        {/* Amount-first fixed column: quantities align vertically so the list
          * scans like a shopping list; empty for "to taste" rows. */}
        <span className={amountCls}>{scaled.amountLabel}</span>
        <span className={`${textCls} flex-1 min-w-0`}>
          {scaled.name}
          {isDeal && <span className={dealChipCls}>Sleva</span>}
        </span>
        {line && (
          line.priced ? (
            <span className={priceCls}>
              ~{fmtMoney((line.consumed_cost || 0) * scale)}&nbsp;Kč
              {!line.verified && <span className={estimateTagCls}>odhad</span>}
            </span>
          ) : (
            <span className={unpricedCls}>bez ceny</span>
          )
        )}
      </li>
    );
  };

  return (
    <Card variant={variant} className="p-6 md:col-span-2 text-left h-fit md:sticky md:top-10">
      <h2 className={headingCls}>
        Ingredience
      </h2>

      <div className="mb-6 flex flex-col gap-2">
        <span className={eyebrowCls}>
          Počet porcí
        </span>
        <PortionStepper value={chosen} onChange={setChosen} variant={variant} />
      </div>

      <ul className="space-y-2.5">
        {requiredEntries.map(renderRow)}
      </ul>

      {optionalEntries.length > 0 && (
        <>
          <h3 className={`${eyebrowCls} block mt-6 mb-3`}>Volitelné</h3>
          <ul className="space-y-2.5">
            {optionalEntries.map(renderRow)}
          </ul>
        </>
      )}

      {shoppingList && (
        <div className="mt-6 pt-4 border-t border-line space-y-1.5">
          {shoppingList.confident && (
            <p className={totalCls}>
              odhad {fmtRange(shoppingList.total_low * scale, shoppingList.total_high * scale)}&nbsp;Kč
              {shoppingList.per_portion_low != null && shoppingList.per_portion_high != null && (
                <span className="block text-xs font-normal text-muted mt-0.5">
                  {fmtRange(shoppingList.per_portion_low, shoppingList.per_portion_high)}&nbsp;Kč / porce
                </span>
              )}
            </p>
          )}
          <p className={coverageCls}>
            {shoppingList.priced_count} z {shoppingList.total_count} surovin oceněno
          </p>
        </div>
      )}
    </Card>
  );
};
