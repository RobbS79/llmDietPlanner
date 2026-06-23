// Shared pricing types + helpers for the meal-plan shopping list.
//
// These mirror EXACTLY the `pricing` payload the backend returns on a plan
// (see diet_planner/services/shopping_list_pricing.py). Price is always an
// ESTIMATE — never presented as an exact figure. Store/brand names live only
// in `deals`, never in the main shopping list.

// ---- New contract ----

export type PriceSource = 'estimate' | 'pantry_estimate' | 'not_available';

// A single row in `plan.shopping_list`. There is intentionally NO
// matched_product_name / shop here — the list is brand- and store-agnostic.
export interface ShoppingListItem {
  ingredient: string;
  quantity: number | string;
  unit: string;
  price_total: number | null;
  price_source: PriceSource;
  estimated: boolean;
  // Legacy pantry flags some payloads still carry (used to quietly fold
  // pantry staples into a collapsed section).
  is_pantry_staple?: boolean;
  pantry?: boolean;
}

// The whole-trolley estimate for THIS plan.
export interface PriceEstimate {
  total: number;
  per_day: number | null;
  per_portion: number | null;
  currency: string;
  is_estimate: true;
  priced_items: number;
  total_items: number;
}

export interface DealItem {
  ingredient: string;
  matched_product_name: string;
  sale: number;
  original: number | null;
  savings: number | null;
}

export interface Deal {
  store: string;
  store_name: string;
  status: 'current' | 'upcoming';
  valid_from: string | null;
  valid_until: string | null;
  currency: string;
  items: DealItem[];
}

export interface Pricing {
  estimate: PriceEstimate | null;
  deals: Deal[];
  // Pantry toggles + presence still ride along on the payload so the
  // shopping list can offer "I already have the basics" switches.
  pantry_toggles?: { basics_on: boolean; fridge_on: boolean };
  pantry_present?: { basics: boolean; fridge: boolean };
}

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

// Read the estimate off a plan object regardless of how it's nested.
export const getEstimate = (plan: any): PriceEstimate | null =>
  plan?.pricing?.estimate ?? null;

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
