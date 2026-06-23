// Shared pricing helpers + per-recipe pricing/deals types.
//
// Whole-plan shopping-list pricing has been removed — shopping and pricing
// live per-recipe now. What remains is the shared money/date formatters and
// the per-recipe price-range + active-deals contracts.

// ---- Helpers ----

// Group thousands with the Czech locale (e.g. 1 250). We round to whole
// units by default — sub-koruna precision implies a false exactness for an
// estimate. Pass `decimals` only where a fractional value genuinely helps
// (e.g. a single deal item priced at 24.90).
export const fmtMoney = (n: number | null | undefined, decimals = 0): string => {
  if (n == null || Number.isNaN(n)) return '—';
  return n.toLocaleString('cs-CZ', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
};

// Format an ISO datetime into the Czech "DD.MM." leaflet token.
export const fmtDay = (iso: string | null): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getDate()}.${d.getMonth() + 1}.`;
};

// Normalise an ingredient name for matching deal -> list row.
export const normName = (s: string | undefined | null): string =>
  (s || '').toLowerCase().trim();

// ---- Per-recipe price range (sub-project 2) ----

// Mirrors the backend RecipeSerializer.price_range payload
// (diet_planner/services/recipe_pricing.py RecipeRange). Always an estimate.
export interface RecipePriceRange {
  low: number;
  high: number;
  per_portion_low: number | null;
  per_portion_high: number | null;
  currency: string;
  confident: boolean;
}

// Format a from–to as "1 250–1 600" (Czech locale, en dash, no currency).
// Caller adds the `~` prefix and currency suffix to match existing copy.
export const fmtRange = (
  lo: number | null | undefined,
  hi: number | null | undefined,
  decimals = 0,
): string => `${fmtMoney(lo, decimals)}–${fmtMoney(hi, decimals)}`;

// Pull a confident price range off a recipe object, else null.
// PIVOT 2026-06-23: absolute price display is disabled — the estimate
// fabricated whole-pack costs for unconvertible units (see deals-headline
// spec). The backend engine stays; we just stop surfacing it. Returns null so
// every price block stops rendering. Replaced by getRecipeDeals (Task 5).
export const getRecipeRange = (_recipe: any): RecipePriceRange | null => {
  return null;
};

// ---- Per-recipe active deals (deals-headline pivot, 2026-06-23) ----

// Mirrors backend services.recipe_deals output. Active-only — every deal here
// is currently live (valid_from <= now < valid_until). Never a price/savings.
export interface RecipeDeal {
  ingredient: string;
  canonical: string;
  shop: string;
  display_name: string;
  source_url: string;
  valid_until: string | null;
}

export interface RecipeDeals {
  matched: number;
  total: number;
  deals: RecipeDeal[];
}

// Pull active deals off a recipe object; null when there are none to show.
export const getRecipeDeals = (recipe: any): RecipeDeals | null => {
  const d = recipe?.deals as RecipeDeals | undefined;
  return d && d.matched > 0 ? d : null;
};
