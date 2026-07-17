import { api } from '@/lib/api';

/** Result of POST /api/recipes/<meal_identifier>/replace/.
 * `replaced:true` carries the swapped-in recipe (same shape as the recipe-detail
 * GET) and `hint_matched` (true / false when a hint was given, null when blank).
 * `replaced:false` carries a `reason` (e.g. "no_alternatives") and no recipe. */
export interface ReplaceRecipeResult {
  replaced: boolean;
  hint_matched?: boolean | null;
  recipe?: Record<string, unknown>;
  reason?: string;
}

/** Swap the meal at `mealId` for a different curated recipe, optionally steered
 * by a free-text `hint` (blank = plain next-best). */
export async function replaceRecipe(mealId: string, hint: string): Promise<ReplaceRecipeResult> {
  const res = await api.post(`/recipes/${mealId}/replace/`, { hint });
  return res.data.data as ReplaceRecipeResult;
}
