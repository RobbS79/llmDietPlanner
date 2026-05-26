import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Zap, ArrowRight, Clock, Users, ChefHat, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { getFoodImageUrl } from '@/lib/food-image';
import { Card } from '@/components/ui/Card';

export const RecipeIndexPage = () => {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['public-recipes', page],
    queryFn: () => api.get(`/recipes/public/?page=${page}`).then(res => res.data.data),
  });

  return (
    <div className="min-h-screen bg-[#09090b] text-white">
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
          <button onClick={() => navigate('/pricing')} className="text-xs font-black text-zinc-400 hover:text-white uppercase tracking-widest transition-colors hidden sm:block">Ceník</button>
          <button onClick={() => navigate('/login')} className="text-xs font-black text-zinc-400 hover:text-white uppercase tracking-widest transition-colors">Přihlásit se</button>
          <button onClick={() => navigate('/login')} className="bg-emerald-600 hover:bg-emerald-500 text-white px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest transition-all">Začít zdarma</button>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-6 sm:px-12 py-12">
        <header className="mb-12">
          <p className="text-[10px] font-black text-emerald-500 uppercase tracking-[1em] mb-4">Recepty</p>
          <h1 className="text-5xl sm:text-6xl font-black tracking-tighter uppercase italic leading-[0.85]">
            Prozkoumejte <span className="text-emerald-500 not-italic">recepty.</span>
          </h1>
          <p className="text-zinc-400 text-lg mt-4 max-w-xl">
            Recepty generované AI s nutričními hodnotami, podrobnými postupy a ingrediencemi.
          </p>
        </header>

        {isLoading ? (
          <div className="flex justify-center py-20">
            <Loader2 size={48} className="text-emerald-500 animate-spin" />
          </div>
        ) : data?.results?.length === 0 ? (
          <div className="py-20 text-center">
            <ChefHat size={64} className="text-zinc-500 mx-auto mb-6" />
            <p className="text-zinc-500 text-sm font-bold italic">Zatím žádné veřejné recepty. Recepty se objeví, jakmile uživatelé začnou generovat jídelníčky.</p>
          </div>
        ) : (
          <>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {data?.results?.map((recipe: any) => (
                <Card
                  key={recipe.id}
                  className="p-0 hover:bg-zinc-900 hover:border-emerald-500/30 cursor-pointer group text-left overflow-hidden"
                  onClick={() => navigate(`/recepty/${recipe.id}/${recipe.slug || ''}/`)}
                >
                  {(() => {
                    const imgUrl = recipe.image_url || getFoodImageUrl(recipe.food_category);
                    return imgUrl ? (
                      <div className="relative h-40 overflow-hidden">
                        <img src={imgUrl} alt={recipe.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" loading="lazy"
                          onError={(e) => { (e.target as HTMLImageElement).closest('.relative')!.style.display = 'none'; }}
                        />
                        <div className="absolute inset-0 bg-gradient-to-t from-[#161d2f] to-transparent" />
                      </div>
                    ) : null;
                  })()}
                  <div className="p-8">
                    <h2 className="text-xl font-black text-white uppercase tracking-tight italic leading-tight group-hover:text-emerald-400 transition-colors mb-4 line-clamp-2">
                      {recipe.name}
                    </h2>
                    {recipe.description && (
                      <p className="text-zinc-500 text-sm leading-relaxed mb-6 line-clamp-2">{recipe.description}</p>
                    )}
                    <div className="mt-auto pt-4 border-t border-zinc-800 flex items-center gap-4 text-[10px] font-black text-zinc-500 uppercase tracking-widest">
                      {recipe.preparation_time && (
                        <span className="flex items-center gap-1.5">
                          <Clock size={12} className="text-emerald-500" /> {recipe.preparation_time} min
                        </span>
                      )}
                      {recipe.servings && (
                        <span className="flex items-center gap-1.5">
                          <Users size={12} className="text-emerald-500" /> {recipe.servings} porcí
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
                  <button onClick={() => setPage(p => p - 1)} className="px-6 py-3 border border-zinc-800 text-zinc-400 hover:text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-colors">
                    Předchozí
                  </button>
                )}
                <span className="text-zinc-500 text-xs font-bold">Strana {data.current_page} z {data.num_pages}</span>
                {data.has_next && (
                  <button onClick={() => setPage(p => p + 1)} className="px-6 py-3 border border-zinc-800 text-zinc-400 hover:text-white rounded-xl font-black uppercase text-[10px] tracking-widest transition-colors">
                    Další
                  </button>
                )}
              </div>
            )}
          </>
        )}

        <div className="mt-20 bg-gradient-to-br from-emerald-600/10 to-teal-600/5 border border-emerald-500/10 rounded-3xl p-12 sm:p-16 text-center">
          <h2 className="text-3xl sm:text-4xl font-black tracking-tighter mb-4">Chcete vlastní jídelníček na míru?</h2>
          <p className="text-zinc-400 text-lg mb-8 max-w-md mx-auto">
            AI vytvoří personalizovaný jídelníček s recepty a nákupním seznamem s reálními cenami z vašeho obchodu.
          </p>
          <button onClick={() => navigate('/login')} className="bg-white text-black px-10 py-4 rounded-2xl font-black uppercase text-sm tracking-widest shadow-2xl hover:shadow-white/10 transition-all active:scale-[0.98] inline-flex items-center gap-3">
            Vytvořte si jídelníček zdarma <ArrowRight size={18} />
          </button>
          <p className="text-zinc-500 text-xs font-bold mt-6 uppercase tracking-widest">10 plánů zdarma. Bez kreditní karty.</p>
        </div>
      </div>

      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-zinc-900 mt-12">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Zap size={16} className="text-emerald-500" />
            <span className="text-sm font-black tracking-tighter uppercase italic text-zinc-600">DietPlanner.</span>
          </div>
          <div className="flex items-center gap-6">
            <Link to="/recepty" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Recepty</Link>
            <Link to="/pricing" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Ceník</Link>
            <Link to="/privacy" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Zásady ochrany soukromí</Link>
            <Link to="/terms" className="text-xs font-bold text-zinc-500 hover:text-white transition-colors">Obchodní podmínky</Link>
          </div>
        </div>
      </footer>
    </div>
  );
};
