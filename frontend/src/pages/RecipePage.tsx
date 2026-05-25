import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Clock, Users, ChefHat, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

export const RecipePage = () => {
  const { id, mealId } = useParams();
  const navigate = useNavigate();

  const { data, isLoading, error } = useQuery({
    queryKey: ['recipe', mealId],
    queryFn: () => api.get(`/recipes/${mealId}/`).then(res => res.data.data),
    retry: 1,
    staleTime: Infinity,
  });

  if (isLoading) {
    return (
      <MainLayout>
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
          <div className="w-20 h-20 rounded-2xl bg-indigo-600/10 flex items-center justify-center border border-indigo-500/20 animate-pulse">
            <Loader2 size={40} className="text-indigo-500 animate-spin" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-black text-white uppercase tracking-tighter italic">Generating Recipe</h2>
            <p className="text-zinc-600 text-sm italic">Our chef is writing step-by-step instructions...</p>
          </div>
        </div>
      </MainLayout>
    );
  }

  if (error || !data) {
    return (
      <MainLayout>
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
          <h2 className="text-2xl font-black text-white uppercase tracking-tighter italic">Recipe not found</h2>
          <button onClick={() => navigate(`/plan/${id}`)} className="px-8 h-12 bg-white text-black font-black uppercase text-[10px] tracking-widest rounded-xl">
            Back to Plan
          </button>
        </div>
      </MainLayout>
    );
  }

  const recipe = data;

  return (
    <MainLayout>
      <div className="max-w-4xl mx-auto px-6 py-12 w-full">
        <button
          onClick={() => navigate(`/plan/${id}`)}
          className="flex items-center gap-2 text-zinc-500 hover:text-white text-xs font-black uppercase tracking-widest mb-12 transition-colors"
        >
          <ArrowLeft size={16} /> Back to Plan
        </button>

        <header className="mb-16 text-left">
          <Badge variant="emerald">Recipe</Badge>
          <h1 className="text-5xl sm:text-6xl font-black text-white tracking-tighter uppercase italic leading-[0.9] mt-6">
            {recipe.name}<span className="text-indigo-500 not-italic">.</span>
          </h1>
          {recipe.description && (
            <p className="text-zinc-500 text-lg font-medium italic mt-6 max-w-2xl leading-relaxed">"{recipe.description}"</p>
          )}

          <div className="flex flex-wrap gap-4 mt-8">
            {recipe.preparation_time && (
              <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">
                <Clock size={14} className="text-indigo-500" /> {recipe.preparation_time} min prep
              </div>
            )}
            {recipe.cooking_time && (
              <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">
                <Clock size={14} className="text-indigo-500" /> {recipe.cooking_time} min cook
              </div>
            )}
            {recipe.servings && (
              <div className="flex items-center gap-2 bg-zinc-900 border border-zinc-800 px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">
                <Users size={14} className="text-indigo-500" /> {recipe.servings} serving{recipe.servings > 1 ? 's' : ''}
              </div>
            )}
          </div>
        </header>

        <div className="grid md:grid-cols-3 gap-10">
          {/* Ingredients sidebar */}
          <Card className="p-8 md:col-span-1 text-left h-fit md:sticky md:top-10">
            <h2 className="text-lg font-black text-white uppercase tracking-tighter italic mb-6 pb-4 border-b border-zinc-800">
              Ingredients
            </h2>
            <ul className="space-y-3">
              {(recipe.ingredients || []).map((ing: any, idx: number) => (
                <li key={idx} className="flex items-start gap-3 text-sm">
                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 mt-2 shrink-0" />
                  <span className="text-zinc-300">
                    {typeof ing === 'string' ? ing : (
                      <>
                        <span className="font-bold text-white">{ing.name}</span>
                        {ing.quantity && (
                          <span className="text-zinc-500 ml-1">— {ing.quantity} {ing.unit || ''}</span>
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
              <ChefHat size={24} className="text-indigo-500" />
              <h2 className="text-lg font-black text-white uppercase tracking-tighter italic">Instructions</h2>
            </div>

            {(recipe.instructions || []).length > 0 ? (
              <ol className="space-y-6">
                {recipe.instructions.map((step: string, idx: number) => (
                  <li key={idx} className="flex gap-5">
                    <div className="w-10 h-10 rounded-xl bg-indigo-600/10 border border-indigo-500/10 flex items-center justify-center text-indigo-400 font-black text-sm italic shrink-0">
                      {idx + 1}
                    </div>
                    <p className="text-zinc-300 leading-relaxed pt-2">{step}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-zinc-600 italic">No instructions available for this recipe.</p>
            )}

            {/* Nutritional info */}
            {recipe.nutritional_info && Object.keys(recipe.nutritional_info).length > 0 && (
              <Card className="p-8 mt-12">
                <h3 className="text-sm font-black text-white uppercase tracking-tighter italic mb-6">Nutrition Facts</h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {Object.entries(recipe.nutritional_info).map(([k, v]: any) => (
                    <div key={k} className="space-y-1">
                      <p className="text-[9px] font-black text-zinc-600 uppercase tracking-widest italic">{k}</p>
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
