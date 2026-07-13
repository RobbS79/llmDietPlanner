import { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Clock, Users, ChefHat, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { getFoodImageUrl } from '@/lib/food-image';
import { Card } from '@/components/ui/Card';
import { RecipeIngredients } from '@/components/recipe/RecipeIngredients';
import { getRecipeDeals, getShoppingList } from '@/lib/pricing';

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
      <div className="min-h-screen bg-paper font-body flex items-center justify-center">
        <div className="text-center space-y-4">
          <Loader2 size={48} className="text-green animate-spin mx-auto" />
          <p className="text-muted text-sm font-semibold">Načítáme recept...</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-paper font-body flex items-center justify-center">
        <div className="text-center space-y-4">
          <h2 className="font-display text-2xl font-bold text-ink">Recept nenalezen</h2>
          <Link to="/recepty" className="text-green font-bold text-sm hover:text-green-mid">Zpět na recepty</Link>
        </div>
      </div>
    );
  }

  const recipe = data;

  return (
    <div className="min-h-screen bg-paper text-ink font-body">
      <nav className="flex items-center justify-between px-6 sm:px-12 py-6 max-w-7xl mx-auto">
        <Link to="/" className="flex items-center gap-3">
          <span className="font-display font-extrabold text-2xl tracking-tight text-ink lowercase">vařto<span className="text-paprika">.</span></span>
        </Link>
        <div className="flex items-center gap-4">
          <button onClick={() => navigate('/recepty')} className="text-ink/80 hover:text-ink font-body font-semibold transition-colors hidden sm:block">Recepty</button>
          <button onClick={() => navigate('/pricing')} className="text-ink/80 hover:text-ink font-body font-semibold transition-colors hidden sm:block">Ceník</button>
          <button onClick={() => navigate('/login')} className="bg-green hover:bg-green-mid text-white px-5 py-3 rounded-xl font-body font-bold transition-all">Začít zdarma</button>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-12 w-full">
        <div className="flex items-center gap-2 text-xs font-semibold text-muted mb-8">
          <Link to="/recepty" className="text-green hover:text-green-mid transition-colors">Recepty</Link>
          <span>/</span>
          <span className="truncate">{recipe.name}</span>
        </div>

        {(() => {
          const imgUrl = recipe.image_url || getFoodImageUrl(recipe.food_category, recipe.name);
          return imgUrl ? (
            <div className="relative h-64 sm:h-80 rounded-3xl overflow-hidden mb-12">
              <img src={imgUrl} alt={recipe.name} className="w-full h-full object-cover" />
              <div className="absolute inset-0 bg-gradient-to-t from-ink/40 via-transparent to-transparent" />
            </div>
          ) : null;
        })()}

        <header className="mb-16 text-left">
          <h1 className="font-display text-5xl sm:text-6xl font-extrabold text-ink tracking-tight leading-[0.95]">
            {recipe.name}<span className="text-paprika">.</span>
          </h1>
          {recipe.description && (
            <p className="text-muted text-lg mt-6 max-w-2xl leading-relaxed">{recipe.description}</p>
          )}
          <div className="flex flex-wrap gap-4 mt-8">
            {recipe.preparation_time && (
              <div className="flex items-center gap-2 bg-card border border-line px-4 py-2.5 rounded-xl text-xs font-semibold text-muted">
                <Clock size={14} className="text-green" /> {recipe.preparation_time} min příprava
              </div>
            )}
            {recipe.cooking_time && (
              <div className="flex items-center gap-2 bg-card border border-line px-4 py-2.5 rounded-xl text-xs font-semibold text-muted">
                <Clock size={14} className="text-green" /> {recipe.cooking_time} min vaření
              </div>
            )}
            {recipe.servings && (
              <div className="flex items-center gap-2 bg-card border border-line px-4 py-2.5 rounded-xl text-xs font-semibold text-muted">
                <Users size={14} className="text-green" /> {recipe.servings} {recipe.servings > 1 ? 'porcí' : 'porce'}
              </div>
            )}
          </div>
        </header>

        {getRecipeDeals(recipe) && (() => {
          const d = getRecipeDeals(recipe)!;
          return (
            <div className="mt-3 rounded-xl bg-paprika-soft p-4">
              <p className="text-sm font-bold text-paprika-strong">
                {d.matched} z {d.total} surovin ve slevě tento týden
              </p>
              <ul className="mt-1.5 space-y-0.5">
                {d.deals.map((deal) => (
                  <li key={deal.canonical} className="text-[13px] text-paprika-strong/90">
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

        <div className="grid md:grid-cols-3 gap-10">
          <RecipeIngredients
            ingredients={recipe.ingredients}
            baseServings={recipe.servings}
            variant="paper"
            shoppingList={getShoppingList(recipe)}
            deals={getRecipeDeals(recipe)}
          />

          <div className="md:col-span-2 space-y-8 text-left">
            <div className="flex items-center gap-3 mb-2">
              <ChefHat size={24} className="text-green" />
              <h2 className="font-display text-lg font-bold text-ink">Postup</h2>
            </div>
            {(recipe.instructions || []).length > 0 ? (
              <ol className="space-y-6">
                {recipe.instructions.map((step: string, idx: number) => (
                  <li key={idx} className="flex gap-5">
                    <div className="w-10 h-10 rounded-xl bg-green-soft border border-line flex items-center justify-center text-green font-price font-bold text-sm shrink-0">
                      {idx + 1}
                    </div>
                    <p className="text-ink leading-relaxed pt-2">{step}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-muted italic">Pro tento recept nejsou k dispozici instrukce.</p>
            )}

            {recipe.nutritional_info && Object.keys(recipe.nutritional_info).length > 0 && (
              <Card variant="paper" className="p-8 mt-12">
                <h3 className="font-display text-sm font-bold text-ink uppercase tracking-wide mb-6">Nutriční hodnoty</h3>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                  {Object.entries(recipe.nutritional_info).map(([k, v]: any) => (
                    <div key={k} className="space-y-1">
                      <p className="text-[10px] font-bold text-muted uppercase tracking-widest">{k}</p>
                      <p className="font-price text-xl font-bold text-ink">{v}</p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </div>
        </div>

        <div className="mt-20 bg-green-soft border border-line rounded-3xl p-12 sm:p-16 text-center">
          <h2 className="font-display text-3xl sm:text-4xl font-extrabold text-ink tracking-tight mb-4">Chcete celý týden takových jídel?</h2>
          <p className="text-muted text-lg mb-8 max-w-md mx-auto">
            Vytvoříme personalizovaný jídelníček s recepty a nákupním seznamem s poctivým odhadem ceny.
          </p>
          <button onClick={() => navigate('/login')} className="bg-green hover:bg-green-mid text-white px-10 py-4 rounded-2xl font-body font-bold text-sm transition-all active:scale-[0.98] inline-flex items-center gap-3">
            Vytvořte si jídelníček zdarma <ArrowRight size={18} />
          </button>
          <p className="text-muted text-xs font-semibold mt-6">2 jídelníčky zdarma. Bez kreditní karty.</p>
        </div>
      </div>

      <footer className="px-6 sm:px-12 py-12 max-w-7xl mx-auto border-t border-line mt-12">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-display font-extrabold text-lg tracking-tight text-ink lowercase">vařto<span className="text-paprika">.</span></span>
          </div>
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
