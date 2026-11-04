// frontend/src/components/discover/RecipeSheet.tsx
import { useQuery } from '@tanstack/react-query';
import { getRecipeSheet, formatAmount, formatDealDate, roundSheetAmount } from '@/lib/discover';
import { useDialog } from '@/lib/useDialog';

type Props = { id: number; picked: boolean; onToggle: (id: number) => void; onClose: () => void };

export function RecipeSheet({ id, picked, onToggle, onClose }: Props) {
  const { data: r, isError } = useQuery({ queryKey: ['recipe-sheet', id], queryFn: () => getRecipeSheet(id) });
  // The close button sits outside the loading/error/loaded branches, so it is
  // the first focus target and stays put while the recipe loads.
  const panel = useDialog(onClose);

  const dealCanon = new Set(r?.deals.items.map((d) => d.canonical));
  return (
    <div role="dialog" aria-modal="true" aria-label={r?.name ?? 'Recept'}
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 sm:items-center"
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div ref={panel} tabIndex={-1} className="relative max-h-[92%] w-full max-w-[680px] overflow-auto rounded-t-3xl bg-paper pb-6 outline-none sm:rounded-3xl">
        {/* EN: Close */}
        <button type="button" onClick={onClose} aria-label="Zavřít"
          className="absolute right-4 top-4 z-10 h-9 w-9 rounded-full border border-kraft bg-white">✕</button>
        {/* EN: The recipe couldn't be loaded. */}
        {!r && isError && <p className="p-6 pr-16 text-ink">Recept se nepodařilo načíst.</p>}
        {/* EN: Loading the recipe… */}
        {!r && !isError && <p className="p-6 pr-16 text-muted">Načítám recept…</p>}
        {r && (
          <>
            <div className="aspect-video"><img src={r.image_url} alt="" className="h-full w-full object-cover" /></div>
            <div className="flex flex-col gap-4 px-5 pt-4">
              <div>
                <h2 className="font-display text-3xl font-bold leading-tight text-ink">{r.name}</h2>
                <p className="mt-1 text-sm text-muted tabular-nums">
                  {[r.minutes && `${r.minutes} min`, r.kcal && `${r.kcal} kcal na porci`,
                    r.macros && `B ${r.macros.protein} g · S ${r.macros.carbs} g · T ${r.macros.fat} g`].filter(Boolean).join(' · ')}
                </p>
                {r.source.name && (
                  <a href={r.source.url} target="_blank" rel="noopener noreferrer" className="text-sm text-muted underline">
                    Podle receptu z {r.source.name}
                  </a>
                )}
              </div>
              {r.deals.items.length > 0 && (
                <p className="rounded-xl bg-yellow-100 px-3 py-2.5 text-[15px] text-ink">
                  <b>Tento týden v akci:</b>{' '}
                  {r.deals.items.map((d) => `${d.display_name.split(' ').slice(0, 2).join(' ').toLowerCase()} (${d.shop} do ${formatDealDate(d.valid_until)})`).join(', ')}
                </p>
              )}
              <div>
                <p className="font-display text-lg font-bold">Suroviny na 1 porci</p>
                <ul className="list-disc pl-5">
                  {r.ingredients.map((i) => (
                    <li key={i.name}>{i.name} <span className="text-sm text-muted">{formatAmount(roundSheetAmount(i.quantity, i.unit), i.unit)}</span>
                      {dealCanon.has(i.canonical) && <span className="ml-1 rounded bg-yellow-300 px-1.5 text-xs font-semibold">v akci</span>}</li>
                  ))}
                </ul>
              </div>
              {r.steps.length > 0 && (
                <div>
                  <p className="font-display text-lg font-bold">Postup</p>
                  <ol className="list-decimal pl-5">{r.steps.slice(0, 2).map((s) => <li key={s}>{s}</li>)}</ol>
                  {r.steps.length > 2 && <p className="text-sm text-muted">… a dalších {r.steps.length - 2} kroků</p>}
                </div>
              )}
              <button type="button" onClick={() => { onToggle(r.id); onClose(); }}
                className="w-full rounded-xl bg-green px-4 py-3.5 text-[17px] font-bold text-white">
                {picked ? 'V seznamu ✓' : 'Chci tohle'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
