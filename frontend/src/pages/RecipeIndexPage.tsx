import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Clock, Users, ChefHat } from 'lucide-react';
import { api } from '@/lib/api';
import { getFoodImageUrl } from '@/lib/food-image';
import { Card } from '@/components/ui/Card';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { getRecipeDeals } from '@/lib/pricing';

export const RecipeIndexPage = () => {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['public-recipes', page],
    queryFn: () => api.get(`/recipes/public/?page=${page}`).then(res => res.data.data),
  });

  return (
    <div className="min-h-screen bg-paper text-ink font-body">
      <PublicHeader />

      <div className="max-w-7xl mx-auto px-6 sm:px-12 py-12">
        <header className="mb-12">
          <p className="text-[10px] font-black text-green uppercase tracking-[1em] mb-4">Recepty</p>
          <h1 className="font-display text-5xl sm:text-6xl font-black tracking-tighter leading-[0.9]">
            Prozkoumejte <span className="text-paprika">recepty.</span>
          </h1>
          <p className="text-muted text-lg mt-4 max-w-xl">
            Recepty s nutričními hodnotami, podrobnými postupy a ingrediencemi.
          </p>
        </header>

        {isLoading ? (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6" aria-hidden="true">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="rounded-2xl border border-line bg-card overflow-hidden animate-pulse">
                <div className="h-40 bg-line/40" />
                <div className="p-8 space-y-4">
                  <div className="h-5 w-3/4 bg-line/60 rounded" />
                  <div className="h-3 w-full bg-line/40 rounded" />
                  <div className="h-3 w-5/6 bg-line/40 rounded" />
                  <div className="h-px bg-line mt-6" />
                  <div className="h-3 w-1/2 bg-line/40 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : data?.results?.length === 0 ? (
          <div className="py-20 text-center">
            <ChefHat size={64} className="text-muted mx-auto mb-6" />
            <p className="text-muted text-sm font-bold">Zatím žádné veřejné recepty. Recepty se objeví, jakmile uživatelé začnou generovat jídelníčky.</p>
          </div>
        ) : (
          <>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {data?.results?.map((recipe: any) => (
                <Card
                  key={recipe.id}
                  to={`/recepty/${recipe.id}/${recipe.slug || ''}/`}
                  variant="paper"
                  className="p-0 hover:border-green/40 group text-left overflow-hidden"
                >
                  {(() => {
                    const imgUrl = recipe.image_url || getFoodImageUrl(recipe.food_category, recipe.name);
                    return imgUrl ? (
                      <div className="relative h-40 overflow-hidden">
                        <img src={imgUrl} alt={recipe.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" loading="lazy"
                          onError={(e) => { ((e.target as HTMLImageElement).closest('.relative') as HTMLElement).style.display = 'none'; }}
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-kraft to-transparent" />
                      </div>
                    ) : null;
                  })()}
                  <div className="p-8">
                    <h2 className="font-display text-xl font-black text-ink leading-tight mb-4 line-clamp-2">
                      {recipe.name}
                    </h2>
                    {recipe.description && (
                      <p className="text-muted text-sm leading-relaxed mb-6 line-clamp-2">{recipe.description}</p>
                    )}
                    {getRecipeDeals(recipe) && (() => {
                      const d = getRecipeDeals(recipe)!;
                      return (
                        <span className="mt-1 inline-block rounded bg-paprika-soft px-1.5 py-0.5 text-[11px] font-medium text-paprika-strong">
                          {d.matched} ve slevě
                        </span>
                      );
                    })()}
                    <div className="mt-auto pt-4 border-t border-line flex items-center gap-4 font-price text-[10px] text-muted">
                      {recipe.preparation_time && (
                        <span className="flex items-center gap-1.5">
                          <Clock size={12} className="text-green" /> {recipe.preparation_time} min
                        </span>
                      )}
                      {recipe.servings && (
                        <span className="flex items-center gap-1.5">
                          <Users size={12} className="text-green" /> {recipe.servings} porcí
                        </span>
                      )}
                    </div>
                  </div>
                </Card>
              ))}
            </div>

            {data && data.num_pages > 1 && (
              <div className="flex items-center justify-center gap-4 mt-12">
                {data.has_previous && (
                  <button onClick={() => setPage(p => p - 1)} className="px-6 py-3 border border-line text-ink hover:border-green/40 rounded-xl font-body font-semibold text-sm transition-colors">
                    Předchozí
                  </button>
                )}
                <span className="text-muted text-xs font-price">Strana {data.current_page} z {data.num_pages}</span>
                {data.has_next && (
                  <button onClick={() => setPage(p => p + 1)} className="px-6 py-3 border border-line text-ink hover:border-green/40 rounded-xl font-body font-semibold text-sm transition-colors">
                    Další
                  </button>
                )}
              </div>
            )}
          </>
        )}

        <div className="mt-20 bg-green-soft border border-green/20 rounded-3xl p-12 sm:p-16 text-center">
          <h2 className="font-display text-3xl sm:text-4xl font-black text-ink tracking-tight mb-4">Chcete vlastní jídelníček na míru?</h2>
          <p className="text-muted text-lg mb-8 max-w-md mx-auto">
            Vytvoříme personalizovaný jídelníček s recepty a nákupním seznamem — a u každého receptu uvidíte, co je tento týden ve slevě.
          </p>
          <button onClick={() => navigate('/login')} className="bg-green hover:bg-green-mid text-white px-10 py-4 rounded-2xl font-body font-bold text-sm transition-colors inline-flex items-center gap-3">
            Vytvořte si jídelníček zdarma <ArrowRight size={18} />
          </button>
          <p className="text-muted text-xs font-price mt-6">2 jídelníčky zdarma · Bez kreditní karty.</p>
        </div>
      </div>

      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-line mt-12">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <span className="font-display font-extrabold text-xl tracking-tight text-ink lowercase">
            vařto<span className="text-paprika">.</span>
          </span>
          <div className="flex items-center gap-6">
            <Link to="/recepty" className="text-xs font-semibold text-muted hover:text-ink transition-colors">Recepty</Link>
            <Link to="/pricing" className="text-xs font-semibold text-muted hover:text-ink transition-colors">Ceník</Link>
            <Link to="/privacy" className="text-xs font-semibold text-muted hover:text-ink transition-colors">Zásady ochrany soukromí</Link>
            <Link to="/terms" className="text-xs font-semibold text-muted hover:text-ink transition-colors">Obchodní podmínky</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
