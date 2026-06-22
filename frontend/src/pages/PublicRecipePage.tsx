import { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Clock, Users, ChefHat, Loader2, Zap } from 'lucide-react';
import { api } from '@/lib/api';
import { getFoodImageUrl } from '@/lib/food-image';
import { Card } from '@/components/ui/Card';
import { fmtRange, getRecipeRange } from '@/lib/pricing';

export const PublicRecipePage = () => {
  const { id } = useParams();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['public-recipe', id],
    queryFn: () => api.get(`/recipes/public/${id}/`).then(res => res.data.data),
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (!data) return;
    const recipe = data;
    const schema: Record<string, any> = {
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
    };
    if (recipe.preparation_time) schema.prepTime = `PT${recipe.preparation_time}M`;
    if (recipe.cooking_time) schema.cookTime = `PT${recipe.cooking_time}M`;
    if (recipe.servings) schema.recipeYield = `${recipe.servings}`;
    if (recipe.nutritional_info) {
      schema.nutrition = { '@type': 'NutritionInformation' };
      for (const [k, v] of Object.entries(recipe.nutritional_info)) {
        const kl = k.toLowerCase();
        if (kl.includes('calor') || kl === 'kcal') schema.nutrition.calories = `${v}`;
        else if (kl.includes('protein')) schema.nutrition.proteinContent = `${v}`;
        else if (kl.includes('carb')) schema.nutrition.carbohydrateContent = `${v}`;
        else if (kl.includes('fat')) schema.nutrition.fatContent = `${v}`;
      }
    }
    const script = document.createElement('script');
    script.type = 'application/ld+json';
    script.textContent = JSON.stringify(schema);
    script.id = 'recipe-schema';
    document.head.appendChild(script);
    return () => { document.getElementById('recipe-schema')?.remove(); };
  }, [data]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#1e293b] flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 size={48} className="text-emerald-500 animate-spin mx-auto" />
          <p className="text-zinc-300 text-sm font-bold italic">Načítáme recept...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-[#1e293b] flex items-center justify-center">
        <div className="text-center space-y-4">
          <h2 className="text-2xl font-black text-white uppercase tracking-tighter italic">Recept nenalezen</h2>
          <Link to="/recepty" className="text-emerald-400 font-bold text-sm hover:text-emerald-300">Zpět na recepty</Link>
        </div>
      </div>
    );
  }

  const recipe = data;

  return (
    <div className="min-h-screen bg-[#1e293b] text-white">
      <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-7xl mx-auto">
        <Link to="/" className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-600 to-emerald-400 flex items-center justify-center shadow-lg">
            <Zap size={20} fill="currentColor" />
          </div>
          <span className="text-xl font-black tracking-tighter uppercase italic">
            Diet<span className="text-emerald-500 not-italic">Planner.</span>
          </span>
        </Link>
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/recepty')} className="text-xs font-black text-zinc-200 hover:text-white uppercase tracking-widest transition-colors hidden sm:block">Recepty</button>
          <button onClick={() => navigate('/pricing')} className="text-xs font-black text-zinc-200 hover:text-white uppercase tracking-widest transition-colors hidden sm:block">Ceník</button>
          <button onClick={() => navigate('/login')} className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all">Začít zdarma</button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-12 w-full">
        <div className="flex items-center gap-2 text-xs font-bold text-zinc-300 mb-8">
          <Link to="/recepty" className="text-emerald-400 hover:text-emerald-300 transition-colors">Recepty</Link>
          <span>/</span>
          <span className="truncate">{recipe.name}</span>
        </div>

        {(() => {
          const imgUrl = recipe.image_url || getFoodImageUrl(recipe.food_category, recipe.name);
          return imgUrl ? (
            <div className="relative h-64 sm:h-80 rounded-3xl overflow-hidden mb-12">
              <img src={imgUrl} alt={recipe.name} className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-[#1e293b] via-transparent to-transparent" />
            </div>
          ) : null;
        })()}

        <header className="mb-16 text-left">
          <h1 className="text-5xl sm:text-6xl font-black text-white tracking-tighter uppercase italic leading-[0.9]">
            {recipe.name}<span className="text-emerald-500 not-italic">.</span>
          </h1>
          {recipe.description && (
            <p className="text-zinc-300 text-lg font-medium italic mt-6 max-w-2xl leading-relaxed">"{recipe.description}"</p>
          )}
          <div className="flex flex-wrap gap-4 mt-8">
            {recipe.preparation_time && (
              <div className="flex items-center gap-2 bg-slate-700 border border-slate-600 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                <Clock size={14} className="text-emerald-500" /> {recipe.preparation_time} min příprava
              </div>
            )}
            {recipe.cooking_time && (
              <div className="flex items-center gap-2 bg-slate-700 border border-slate-600 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                <Clock size={14} className="text-emerald-500" /> {recipe.cooking_time} min vaření
              </div>
            )}
            {recipe.servings && (
              <div className="flex items-center gap-2 bg-slate-700 border border-slate-600 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-300">
                <Users size={14} className="text-emerald-500" /> {recipe.servings} {recipe.servings > 1 ? 'porcí' : 'porce'}
              </div>
            )}
          </div>
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
          <Card className="p-8 md:col-span-1 text-left h-fit md:sticky md:top-10">
            <h2 className="text-lg font-black text-white uppercase tracking-tighter italic mb-6 pb-4 border-b border-slate-600">Ingredience</h2>
            <ul className="space-y-3">
              {(recipe.ingredients || []).map((ing: any, idx: number) => (
                <li key={idx} className="flex items-start gap-3 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-2 shrink-0" />
                  <span className="text-zinc-300">
                    {typeof ing === 'string' ? ing : (
                      <>
                        <span className="font-bold text-white">{ing.name}</span>
                        {ing.quantity && <span className="text-zinc-300 ml-1">— {ing.quantity} {ing.unit || ''}</span>}
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </Card>

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

        <div className="mt-20 bg-gradient-to-br from-emerald-600/10 to-teal-600/5 border border-emerald-500/10 rounded-3xl p-12 sm:p-16 text-center">
          <h2 className="text-3xl sm:text-4xl font-black tracking-tighter mb-4">Chcete celý týden takových jídel?</h2>
          <p className="text-zinc-200 text-lg mb-8 max-w-md mx-auto">
            Vytvoříme personalizovaný jídelníček s recepty a nákupním seznamem s reálními cenami.
          </p>
          <button onClick={() => navigate('/login')} className="bg-white text-black px-10 py-4 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] inline-flex items-center gap-3">
            Vytvořte si jídelníček zdarma <ArrowRight size={18} />
          </button>
          <p className="text-zinc-300 text-xs font-bold mt-6 uppercase tracking-widest">2 jídelníčky zdarma. Bez kreditní karty.</p>
        </div>
      </div>

      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-slate-700 mt-12">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-emerald-500" />
            <span className="text-sm font-black tracking-tighter uppercase italic text-zinc-400">DietPlanner.</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/recepty" className="text-xs font-bold text-zinc-300 hover:text-white transition-colors">Recepty</Link>
            <Link to="/pricing" className="text-xs font-bold text-zinc-300 hover:text-white transition-colors">Ceník</Link>
            <Link to="/privacy" className="text-xs font-bold text-zinc-300 hover:text-white transition-colors">Zásady ochrany soukromí</Link>
            <Link to="/terms" className="text-xs font-bold text-zinc-300 hover:text-white transition-colors">Obchodní podmínky</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
