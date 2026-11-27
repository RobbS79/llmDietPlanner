import type { RecipeCardData } from '@/lib/discover';
import { dealBadge } from '@/lib/discover';

type Props = { recipe: RecipeCardData; picked: boolean; onToggle: (id: number) => void; onOpen: (id: number) => void };

export function RecipeCard({ recipe, picked, onToggle, onOpen }: Props) {
  const meta = [recipe.minutes ? `${recipe.minutes} min` : null, recipe.kcal ? `${recipe.kcal} kcal na porci` : null]
    .filter(Boolean).join(' · ');
  const badge = dealBadge(recipe.deals.names);
  return (
    <article className="flex flex-col overflow-hidden rounded-2xl border border-kraft bg-white">
      <button type="button" onClick={() => onOpen(recipe.id)} aria-hidden="true" tabIndex={-1} className="aspect-[4/3] bg-ink">
        <img src={recipe.image_url} alt="" loading="lazy" className="h-full w-full object-cover" />
      </button>
      <div className="flex flex-1 flex-col gap-1.5 p-3.5">
        <button type="button" onClick={() => onOpen(recipe.id)} className="text-left hover:underline">
          <h3 className="font-display text-lg font-bold leading-tight text-ink">{recipe.name}</h3>
        </button>
        {meta && <p className="text-sm text-muted tabular-nums">{meta}</p>}
        {badge && <span className="self-start rounded-md bg-yellow-300 px-2 py-0.5 text-sm font-semibold text-ink">{badge}</span>}
        <button type="button" aria-pressed={picked} onClick={() => onToggle(recipe.id)}
          className={`mt-auto rounded-xl border-2 border-green px-3 py-2 font-bold ${picked ? 'bg-green text-white' : 'text-green'}`}>
          {/* EN: "In the list ✓" / "I want this" */}
          {picked ? 'V seznamu ✓' : 'Chci tohle'}
        </button>
      </div>
    </article>
  );
}
