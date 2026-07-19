import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Clock, Users, ChefHat, Loader2, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import { getFoodImageUrl } from '@/lib/food-image';
import { MainLayout } from '@/components/layout/MainLayout';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { RecipeIngredients } from '@/components/recipe/RecipeIngredients';
import { getRecipeDeals, getShoppingList } from '@/lib/pricing';
import { normalizeNutrition } from '@/lib/nutrition';
import { czechPlural, PORTION_FORMS } from '@/lib/portions';
import { useToast } from '@/components/ui/Toast';
import { RecipeRefineChat } from '@/components/recipe/RecipeRefineChat';

export const RecipePage = () => {
  const { id, mealId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data, isLoading, error } = useQuery({
    queryKey: ['recipe', mealId],
    queryFn: () => api.get(`/recipes/${mealId}/`).then(res => res.data.data),
    retry: 1,
    staleTime: Infinity,
  });

  const recipe = data;

  // Conversational replace-recipe swap. See
  // docs/superpowers/specs/2026-07-18-recipe-refine-chat-design.md.
  const [panelOpen, setPanelOpen] = useState(false);

  const handleAccepted = (recipe: Record<string, unknown>) => {
    queryClient.setQueryData(['recipe', mealId], recipe);
    queryClient.invalidateQueries({ queryKey: ['plan', id] });
    // The swap resets MealInstance.is_cooked server-side; PlanView derives
    // its cooked badges from this separate query, so it must refresh too.
    queryClient.invalidateQueries({ queryKey: ['mealInstances', id] });
    setPanelOpen(false);
    toast.success('Recept byl vyměněn.');
  };

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
          <div className="w-20 h-20 rounded-2xl bg-green-soft flex items-center justify-center border border-green/40 animate-pulse">
            <Loader2 size={40} className="text-green animate-spin" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-black font-display text-ink uppercase tracking-tighter italic">Generujeme recept</h2>
            <p className="text-muted text-sm italic">Náš kuchař píše postup krok za krokem...</p>
          </div>
        </div>
      </MainLayout>
    );
  }

  if (error || !data) {
    return (
      <MainLayout>
        <div className="flex-1 flex flex-col items-center justify-center gap-6 text-center">
          <h2 className="text-2xl font-black font-display text-ink uppercase tracking-tighter italic">Recept nenalezen</h2>
          <button onClick={() => navigate(`/plan/${id}`)} className="px-8 h-12 bg-green text-white font-black uppercase text-[10px] tracking-widest rounded-xl">
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
          className="flex items-center gap-2 text-muted hover:text-ink text-xs font-black uppercase tracking-widest mb-12 transition-colors"
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
          <h1 className="text-5xl sm:text-6xl font-black font-display text-ink tracking-tighter uppercase italic leading-[0.9] mt-6">
            {recipe.name}<span className="text-paprika not-italic">.</span>
          </h1>
          {recipe.description && (
            <p className="text-muted text-lg font-medium italic mt-6 max-w-2xl leading-relaxed">"{recipe.description}"</p>
          )}

          <div className="flex flex-wrap gap-4 mt-8">
            {recipe.preparation_time && (
              <div className="flex items-center gap-2 bg-card border border-line px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-muted">
                <Clock size={14} className="text-green" /> {recipe.preparation_time} min prep
              </div>
            )}
            {recipe.cooking_time && (
              <div className="flex items-center gap-2 bg-card border border-line px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-muted">
                <Clock size={14} className="text-green" /> {recipe.cooking_time} min cook
              </div>
            )}
            {recipe.servings && (
              <div className="flex items-center gap-2 bg-card border border-line px-4 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-[0.2em] text-muted">
                <Users size={14} className="text-green" /> {recipe.servings} {czechPlural(recipe.servings, PORTION_FORMS)}
              </div>
            )}
          </div>

          {recipe.source_url && recipe.source_name && (
            <p className="text-muted text-xs mt-6">
              Inspirováno receptem z{' '}
              <a
                href={recipe.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-green hover:text-green-mid underline underline-offset-2 font-semibold"
              >
                {recipe.source_name}
              </a>
              {recipe.source_author ? ` (${recipe.source_author})` : ''}.
            </p>
          )}
        </header>

        {/* Conversational replace-recipe swap */}
        <div className="mb-12">
          {!panelOpen ? (
            <button
              onClick={() => setPanelOpen(true)}
              className="flex items-center gap-2 px-5 h-11 bg-card border border-line rounded-xl text-[10px] font-black uppercase tracking-widest text-ink hover:border-green/50 transition-colors"
            >
              <RefreshCw size={14} className="text-green" /> Vyměnit recept
            </button>
          ) : (
            <RecipeRefineChat
              mealId={mealId!}
              onAccepted={handleAccepted}
              onClose={() => setPanelOpen(false)}
            />
          )}
        </div>

        {getRecipeDeals(recipe) && (() => {
          const d = getRecipeDeals(recipe)!;
          return (
            <div className="mt-3 rounded-lg bg-green-soft p-3">
              <p className="text-sm font-medium text-green">
                {d.matched} z {d.total} surovin ve slevě tento týden
              </p>
              <ul className="mt-1 space-y-0.5">
                {d.deals.map((deal) => (
                  <li key={deal.canonical} className="text-[13px] text-green">
                    <a href={deal.source_url} target="_blank" rel="noopener noreferrer"
                       className="hover:underline">
                      {deal.display_name} — {deal.shop}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          );
        })()}

        <div className="grid md:grid-cols-5 gap-10">
          {/* Ingredients sidebar — scaled "shopping list" with portion stepper */}
          <RecipeIngredients
            ingredients={recipe.ingredients}
            baseServings={recipe.servings}
            shoppingList={getShoppingList(recipe)}
            deals={getRecipeDeals(recipe)}
          />

          {/* Instructions */}
          <div className="md:col-span-3 space-y-8 text-left">
            <div className="flex items-center gap-3 mb-2">
              <ChefHat size={24} className="text-green" />
              <h2 className="text-lg font-black font-display text-ink uppercase tracking-tighter italic">Postup</h2>
            </div>

            {(recipe.instructions || []).length > 0 ? (
              <ol className="space-y-6">
                {recipe.instructions.map((step: string, idx: number) => (
                  <li key={idx} className="flex gap-5">
                    <div className="w-10 h-10 rounded-xl bg-green-soft border border-green/40 flex items-center justify-center text-green font-black text-sm italic shrink-0">
                      {idx + 1}
                    </div>
                    <p className="text-muted leading-relaxed pt-2">{step}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-muted italic">Pro tento recept nejsou k dispozici instrukce.</p>
            )}

            {/* Nutritional info */}
            {(() => {
              const nutrition = normalizeNutrition(recipe.nutritional_info, recipe.servings);
              return nutrition && (
                <Card className="p-8 mt-12">
                  <h3 className="text-sm font-black text-ink uppercase tracking-tighter italic mb-6">
                    Nutriční hodnoty <span className="text-muted font-bold normal-case not-italic tracking-normal">· na porci</span>
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {nutrition.map((row) => (
                      <div key={row.key} className="space-y-1">
                        <p className="text-[9px] font-black text-muted uppercase tracking-widest italic">{row.label}</p>
                        <p className="text-xl font-black text-ink italic tracking-tighter">{row.value} {row.unit}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              );
            })()}
          </div>
        </div>
      </div>
    </MainLayout>
  );
};
