import { api } from './api';

export type DealItem = { canonical: string; shop: string; display_name: string; valid_until: string; ingredient?: string };
export type RecipeCardData = {
  id: number; slug: string; name: string; image_url: string; minutes: number | null; kcal: number | null;
  deals: { matched: number; total: number; names: string[]; items: DealItem[] };
};
export type RecipeSheetData = RecipeCardData & {
  macros: { protein: number; carbs: number; fat: number } | null;
  ingredients: { name: string; canonical: string; quantity: number | null; unit: string }[];
  steps: string[];
  source: { name: string; url: string };
};
export type DiscoverResult = { understood: string[]; exact: boolean; fallback: boolean; medical_note: boolean; has_more: boolean; recipes: RecipeCardData[] };
export type WeekDeal = { canonical: string; name: string; shop: string; valid_until: string };
export type ListLine = { name: string; canonical: string; amount: number | null; unit: string; needed_by: number; recipe_ids: number[]; deal: DealItem | null };

export async function searchRecipes(q: string, page: number, turnstileToken?: string): Promise<DiscoverResult> {
  const res = await api.post('/discover/', { q, page, turnstile_token: turnstileToken });
  return res.data.data;
}
export const getRecipeSheet = async (id: number): Promise<RecipeSheetData> => (await api.get(`/discover/recipe/${id}/`)).data.data;
export const getWeekDeals = async (): Promise<WeekDeal[]> => (await api.get('/deals/this-week/')).data.data.deals;
export const composeList = async (recipeIds: number[], people: number): Promise<{ recipes: RecipeCardData[]; lines: ListLine[] }> =>
  (await api.post('/shopping-list/compose/', { recipe_ids: recipeIds, people })).data.data;

export function dealBadge(names: string[]): string | null {
  if (!names.length) return null;
  if (names.length === 1) return `V akci: ${names[0]}`;
  if (names.length === 2) return `V akci: ${names[0]}, ${names[1]}`;
  return `V akci: ${names[0]} a ${names.length - 1} další`;
}

export function formatDealDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()}. ${d.getUTCMonth() + 1}.`;
}

export function formatAmount(amount: number | null, unit: string): string {
  if (amount == null) return '';
  return `${String(amount).replace('.', ',')} ${unit}`.trim();
}
