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
  priced_count: number;
  total_count: number;
}

// Format a from–to as "1 250–1 600" (Czech locale, en dash, no currency).
// Caller adds the `~` prefix and currency suffix to match existing copy.
export const fmtRange = (
  lo: number | null | undefined,
  hi: number | null | undefined,
  decimals = 0,
): string => `${fmtMoney(lo, decimals)}–${fmtMoney(hi, decimals)}`;

// Pull a price range off a recipe object, else null. Un-stubbed 2026-07-13
// (Component 2 of the priced-shopping-list spec) now that the price book
// carries `verified`/`source` per entry and the UI labels every total
// "odhad" (estimate) rather than implying exactness. See
// docs/superpowers/specs/2026-07-13-per-recipe-priced-shopping-list-design.md.
// ROLLED BACK 2026-07-13: absolute per-recipe prices are disabled again. Prod
// verification showed the per-line engine still produces plausible-but-wrong
// amounts for cooking-unit quantities (herbs by volume, per-bunch `ks` book
// values, missing piece weights, canonical mis-maps). Showing those to paid
// traffic is worse than showing none, so we revert to the deals-only surface
// until the pricing-data project lands (density table, piece weights, per-ks
// book audit, mapping audit). Flip PRICE_DISPLAY_ENABLED back to re-enable.
export const PRICE_DISPLAY_ENABLED = false;

export const getRecipeRange = (recipe: any): RecipePriceRange | null => {
  if (!PRICE_DISPLAY_ENABLED) return null;
  return (recipe?.price_range as RecipePriceRange | undefined) ?? null;
};

// ---- Per-recipe priced shopping list (Component 2) ----

// Mirrors the backend RecipeSerializer.shopping_list payload
// (diet_planner/serializers.py RecipeSerializer.get_shopping_list).
export interface ShoppingListLine {
  name: string;
  canonical: string | null;
  consumed_cost: number | null;
  priced: boolean;
  verified: boolean;
}

export interface ShoppingList {
  lines: ShoppingListLine[];
  total_low: number;
  total_high: number;
  per_portion_low: number | null;
  per_portion_high: number | null;
  priced_count: number;
  total_count: number;
  verified_count: number;
  currency: string;
  confident: boolean;
}

// Pull the per-line priced shopping list off a recipe object, else null.
export const getShoppingList = (recipe: any): ShoppingList | null => {
  if (!PRICE_DISPLAY_ENABLED) return null;  // rolled back — see getRecipeRange
  return (recipe?.shopping_list as ShoppingList | undefined) ?? null;
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
