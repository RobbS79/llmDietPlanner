import { useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BadgePercent, Clock, Users, ChefHat, Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { getFoodImageUrl } from '@/lib/food-image';
import { Card } from '@/components/ui/Card';
import { PublicHeader } from '@/components/layout/PublicHeader';
import { RecipeIngredients } from '@/components/recipe/RecipeIngredients';
import { getRecipeDeals, getShoppingList } from '@/lib/pricing';
import { normalizeNutrition, nutritionBasisFor } from '@/lib/nutrition';
import { czechPlural, PORTION_FORMS } from '@/lib/portions';

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
    // Only emit nutrition Google should trust — same normalized per-portion
    // values the visible card shows, nothing when the data is implausible.
    const nutrition = normalizeNutrition(
      recipe.nutritional_info,
      recipe.servings,
      nutritionBasisFor(recipe),
    );
    if (nutrition) {
      schema.nutrition = { '@type': 'NutritionInformation' };
      for (const row of nutrition) {
        if (row.key === 'calories') schema.nutrition.calories = `${row.value} kcal`;
        else if (row.key === 'protein') schema.nutrition.proteinContent = `${row.value} g`;
        else if (row.key === 'carbs') schema.nutrition.carbohydrateContent = `${row.value} g`;
        else if (row.key === 'fat') schema.nutrition.fatContent = `${row.value} g`;
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
      <PublicHeader />

      <div className="max-w-4xl mx-auto px-6 py-12 w-full">
        <div className="flex items-center gap-2 text-sm font-semibold text-muted mb-8">
          <Link to="/recepty" className="inline-flex py-2 text-green hover:text-green-mid transition-colors">Recepty</Link>
          <span>/</span>
          <span className="truncate">{recipe.name}</span>
        </div>

        {(() => {
          const imgUrl = recipe.image_url || getFoodImageUrl(recipe.food_category, recipe.name);
          return imgUrl ? (
            <div className="relative aspect-[16/9] w-full rounded-3xl overflow-hidden mb-12">
              <img src={imgUrl} alt={recipe.name} className="w-full h-full object-cover" />
              {/* Stock images are category-based, not photos of the actual dish —
                * say so instead of letting visitors catch the mismatch. */}
              <span className="absolute bottom-3 right-3 rounded-lg bg-ink/60 px-2 py-1 text-[10px] font-semibold text-white/90">
                Ilustrační foto
              </span>
            </div>
          ) : null;
        })()}

        <header className="mb-12 text-left">
          <h1 className="font-display text-5xl sm:text-6xl font-extrabold text-ink tracking-tight leading-[0.95]">
            {recipe.name}<span className="text-paprika">.</span>
          </h1>
          {recipe.description && (
            <p className="text-muted text-lg mt-6 max-w-2xl leading-relaxed">{recipe.description}</p>
          )}
          {recipe.source_name && recipe.source_url && (
            <p className="text-muted text-sm mt-4">
              Podle receptu z{' '}
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
                <Users size={14} className="text-green" /> {recipe.servings} {czechPlural(recipe.servings, PORTION_FORMS)}
              </div>
            )}
          </div>
        </header>

        {getRecipeDeals(recipe) && (() => {
          const d = getRecipeDeals(recipe)!;
          return (
            <section className="mb-12 rounded-2xl border border-paprika/30 bg-paprika-soft/60 p-5">
              <div className="flex items-center gap-2.5">
                <BadgePercent size={20} className="text-paprika-strong shrink-0" />
                <h2 className="font-display text-base font-bold text-ink">
                  {d.matched} z {d.total} surovin ve slevě tento týden
                </h2>
              </div>
              <ul className="mt-3 divide-y divide-paprika/15">
                {d.deals.map((deal) => (
                  <li key={deal.canonical}>
                    <a
                      href={deal.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group flex items-center justify-between gap-3 py-2.5 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-paprika/50"
                    >
                      <span className="text-sm font-semibold text-ink underline decoration-paprika/40 underline-offset-2 group-hover:decoration-paprika transition-colors">
                        {deal.display_name}
                      </span>
                      <span className="shrink-0 rounded-md bg-card border border-line px-2 py-0.5 text-[11px] font-semibold text-muted">
                        {deal.shop}
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-[11px] text-muted">Podle aktuálních letáků obchodů.</p>
            </section>
          );
        })()}

        <div className="grid md:grid-cols-5 gap-10">
          <RecipeIngredients
            ingredients={recipe.ingredients}
            baseServings={recipe.servings}
            variant="paper"
            shoppingList={getShoppingList(recipe)}
            deals={getRecipeDeals(recipe)}
          />

          <div className="md:col-span-3 space-y-8 text-left">
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

            {(() => {
              const nutrition = normalizeNutrition(
      recipe.nutritional_info,
      recipe.servings,
      nutritionBasisFor(recipe),
    );
              return nutrition && (
                <Card variant="paper" className="p-8 mt-12">
                  <h3 className="font-display text-sm font-bold text-ink uppercase tracking-wide mb-6">
                    Nutriční hodnoty <span className="text-muted font-semibold normal-case tracking-normal">· na porci</span>
                  </h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {nutrition.map((row) => (
                      <div key={row.key} className="space-y-1">
                        <p className="text-[10px] font-bold text-muted uppercase tracking-widest">{row.label}</p>
                        <p className="font-price text-xl font-bold text-ink">{row.value} {row.unit}</p>
                      </div>
                    ))}
                  </div>
                </Card>
              );
            })()}
          </div>
        </div>

        <div className="mt-20 bg-green-soft border border-line rounded-3xl p-8 sm:p-16 text-center">
          <h2 className="font-display text-2xl sm:text-4xl font-extrabold text-ink tracking-tight mb-4">Chcete celý týden takových jídel?</h2>
          <p className="text-muted text-lg mb-8 max-w-md mx-auto">
            Vytvoříme personalizovaný jídelníček s recepty a nákupním seznamem — a u každého receptu uvidíte, co je tento týden ve slevě.
          </p>
          <button onClick={() => navigate('/login')} className="bg-green hover:bg-green-mid text-white px-10 py-4 rounded-2xl font-body font-bold text-sm transition-all active:scale-[0.98] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green/50 focus-visible:ring-offset-2 inline-flex items-center gap-3">
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
