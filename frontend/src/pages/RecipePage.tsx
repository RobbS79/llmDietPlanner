import { useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Clock, Users, ChefHat, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { getFoodImageUrl } from '@/lib/food-image';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { fmtRange, getRecipeRange } from '@/lib/pricing';

export const RecipePage = () => {
  const { id, mealId } = useParams();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['recipe', mealId],
    queryFn: () => api.get(`/recipes/${mealId}/`).then(res => res.data.data),
    retry: 1,
    staleTime: Infinity,
  });

  const recipe = data;

  useEffect(() => {
    if (!recipe) return;
    const schema = {
      '@context': 'https://schema.org',
      '@type': 'Recipe',
      name: recipe.name,
      description: recipe.description || '',
      recipeIngredient: (recipe.ingredients || []).map((ing: any) =>
        typeof ing === 'string' ? ing : `${ing.quantity || ''} ${ing.unit || ''} ${ing.name}`.trim()
      ),
      recipeInstructions: (recipe.instructions || []).map((step: string, idx: number) => ({
        '@type': 'HowToStep',
        position: idx + 1,
        text: step,
      })),
      ...(recipe.preparation_time && { prepTime: `PT${recipe.preparation_time}M` }),
      ...(recipe.cooking_time && { cookTime: `PT${recipe.cooking_time}M` }),
      ...(recipe.preparation_time && recipe.cooking_time && {
        totalTime: `PT${recipe.preparation_time + recipe.cooking_time}M`,
      }),
      ...(recipe.servings && { recipeYield: `${recipe.servings}` }),
      ...(recipe.nutritional_info && {
        nutrition: {
          '@type': 'NutritionInformation',
          ...Object.fromEntries(
            Object.entries(recipe.nutritional_info).map(([k, v]) => {
              const key = k.toLowerCase();
              if (key.includes('calor') || key === 'kcal') return ['calories', `${v}`];
              if (key.includes('protein')) return ['proteinContent', `${v}`];
              if (key.includes('carb')) return ['carbohydrateContent', `${v}`];
              if (key.includes('fat')) return ['fatContent', `${v}`];
              return [k, `${v}`];
            })
          ),
        },
      }),
    };
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify(schema);
    script.id = 'recipe-schema';
    document.head.appendChild(script);
    return () => { document.getElementById('recipe-schema')?.remove(); };
  }, [recipe]);

  if (isLoading) {
    return (
      <MainLayout>
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
          <div className="w-20 h-20 rounded-2xl bg-emerald-600/10 flex items-center justify-center border border-emerald-500/20 animate-pulse">
            <Loader2 size={40} className="text-emerald-500 animate-spin" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-black text-white uppercase tracking-tighter italic">Generujeme recept</h2>
            <p className="text-zinc-400 text-sm italic">Náš kuchař píše postup krok za krokem...</p>
          </div>
        </div>
      </MainLayout>
    );
  }

  if (error || !data) {
    return (
      <MainLayout>
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
          <h2 className="text-2xl font-black text-white uppercase tracking-tighter italic">Recept nenalezen</h2>
          <button onClick={() => navigate(`/plan/${id}`)} className="px-8 h-12 bg-white text-black font-black uppercase text-[10px] tracking-widest rounded-xl">
            Zpět na plán
          </button>
        </div>
      </MainLayout>
    );
  }

  return (
    <MainLayout>
      <div className="max-w-4xl mx-auto px-6 py-12 w-full">
        <button
          onClick={() => navigate(`/plan/${id}`)}
          className="flex items-center gap-2 text-zinc-300 hover:text-white text-xs font-black uppercase tracking-widest mb-12 transition-colors"
        >
          <ArrowLeft size={16} /> Zpět na plán
        </button>

        {(() => {
          const imgUrl = recipe.image_url || getFoodImageUrl(recipe.food_category, recipe.name);
          return imgUrl ? (
            <div className="relative h-64 sm:h-80 rounded-3xl overflow-hidden mb-12">
              <img src={imgUrl} alt={recipe.name} className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-[#09090b] via-transparent to-transparent" />
            </div>
          ) : null;
        })()}

        <header className="mb-16 text-left">
          <div className="flex items-center gap-2">
            <Badge variant="emerald">Recept</Badge>
            {recipe.source_url && <Badge variant="emerald">Ověřený recept</Badge>}
          </div>
          <h1 className="text-5xl sm:text-6xl font-black text-white tracking-tighter uppercase italic leading-[0.9] mt-6">
            {recipe.name}<span className="text-emerald-500 not-italic">.</span>
          </h1>
          {recipe.description && (
            <p className="text-zinc-300 text-lg font-medium italic mt-6 max-w-2xl leading-relaxed">"{recipe.description}"</p>
          )}

          <div className="flex flex-wrap gap-4 mt-8">
            {recipe.preparation_time && (
              <div className="flex items-center gap-2 bg-slate-700 border border-slate-600 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                <Clock size={14} className="text-emerald-500" /> {recipe.preparation_time} min prep
              </div>
            )}
            {recipe.cooking_time && (
              <div className="flex items-center gap-2 bg-slate-700 border border-slate-600 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                <Clock size={14} className="text-emerald-500" /> {recipe.cooking_time} min cook
              </div>
            )}
            {recipe.servings && (
              <div className="flex items-center gap-2 bg-slate-700 border border-slate-600 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                <Users size={14} className="text-emerald-500" /> {recipe.servings} {recipe.servings > 1 ? 'porcí' : 'porce'}
              </div>
            )}
          </div>

          {recipe.source_url && recipe.source_name && (
            <p className="text-zinc-400 text-xs mt-6">
              Inspirováno receptem z{' '}
              <a
                href={recipe.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2 font-semibold"
              >
                {recipe.source_name}
              </a>
              {recipe.source_author ? ` (${recipe.source_author})` : ''}.
            </p>
          )}
        </header>

        {getRecipeRange(recipe) && (() => {
          const pr = getRecipeRange(recipe)!;
          const cur = pr.currency === 'EUR' ? '€' : 'Kč';
          return (
            <div className="mb-16 -mt-8 inline-block rounded-2xl border border-emerald-500/15 bg-emerald-500/5 px-6 py-5 text-left">
              <p className="mb-1 text-[9px] font-black uppercase italic tracking-[0.3em] text-zinc-400">Přibližná cena · na porci</p>
              <p className="text-4xl font-black italic tracking-tighter tabular-nums text-white">
                ~{pr.per_portion_low != null ? fmtRange(pr.per_portion_low, pr.per_portion_high) : fmtRange(pr.low, pr.high)}{' '}
                <span className="text-base not-italic text-emerald-500">{cur}</span>
              </p>
              {pr.per_portion_low != null && (
                <p className="mt-1 text-[11px] italic text-zinc-400 tabular-nums">celý recept ~{fmtRange(pr.low, pr.high)} {cur}</p>
              )}
              <p className="mt-2 text-[10px] italic text-zinc-500">z reálných cen Rohlíku · jen odhad</p>
            </div>
          );
        })()}

        <div className="grid md:grid-cols-3 gap-10">
          {/* Ingredients sidebar */}
          <Card className="p-8 md:col-span-1 text-left h-fit md:sticky md:top-10">
            <h2 className="text-lg font-black text-white uppercase tracking-tighter italic mb-6 pb-4 border-b border-slate-600">
              Ingredience
            </h2>
            <ul className="space-y-3">
              {(recipe.ingredients || []).map((ing: any, idx: number) => (
                <li key={idx} className="flex items-start gap-3 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
                  <span className="text-zinc-300">
                    {typeof ing === 'string' ? ing : (
                      <>
                        <span className="font-bold text-white">{ing.name}</span>
                        {ing.quantity && (
                          <span className="text-zinc-300 ml-1">— {ing.quantity} {ing.unit || ''}</span>
                        )}
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

          {/* Instructions */}
          <div className="md:col-span-2 space-y-8 text-left">
            <div className="flex items-center gap-3 mb-2">
              <ChefHat size={24} className="text-emerald-500" />
              <h2 className="text-lg font-black text-white uppercase tracking-tighter italic">Postup</h2>
            </div>

            {(recipe.instructions || []).length > 0 ? (
              <ol className="space-y-6">
                {recipe.instructions.map((step: string, idx: number) => (
                  <li key={idx} className="flex gap-5">
                    <div className="w-10 h-10 rounded-xl bg-emerald-600/10 border border-emerald-500/10 flex items-center justify-center text-emerald-400 font-black text-sm italic shrink-0">
                      {idx + 1}
                    </div>
                    <p className="text-zinc-300 leading-relaxed pt-2">{step}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-zinc-400 italic">Pro tento recept nejsou k dispozici instrukce.</p>
            )}

            {/* Nutritional info */}
            {recipe.nutritional_info && Object.keys(recipe.nutritional_info).length > 0 && (
              <Card className="p-8 mt-12">
                <h3 className="text-sm font-black text-white uppercase tracking-tighter italic mb-6">Nutriční hodnoty</h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {Object.entries(recipe.nutritional_info).map(([k, v]: any) => (
                    <div key={k} className="space-y-1">
                      <p className="text-[9px] font-black text-zinc-400 uppercase tracking-widest italic">{k}</p>
                      <p className="text-xl font-black text-zinc-200 italic tracking-tighter">{v}</p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>
      </div>
    </MainLayout>
  );
};
