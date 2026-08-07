// Normalizes the free-form `nutritional_info` dict (LLM-authored, mixed
// languages/units, unlabeled per-recipe vs per-portion) into displayable
// per-portion rows with Czech labels — or null when the numbers can't be
// made plausible, in which case the UI hides the card entirely rather than
// show fabricated-looking values.

export type NutrientKey = 'calories' | 'protein' | 'carbs' | 'fat';

export interface NutrientRow {
  key: NutrientKey;
  label: string;
  value: number;
  unit: 'kcal' | 'g';
}

const LABELS: Record<NutrientKey, string> = {
  calories: 'Energie',
  protein: 'Bílkoviny',
  carbs: 'Sacharidy',
  fat: 'Tuky',
};

// Per-portion plausibility bounds. A meal outside these is either per-recipe
// data or garbage — never worth displaying as-is.
const KCAL_MIN = 50;
const KCAL_MAX = 1500;
const MACRO_MAX_G = 250;

const DISPLAY_ORDER: NutrientKey[] = ['calories', 'protein', 'carbs', 'fat'];

function classifyKey(key: string): NutrientKey | null {
  const k = key.toLowerCase();
  if (/kcal|calor|energ/.test(k)) return 'calories';
  if (/protein|b[ií]lkovin/.test(k)) return 'protein';
  if (/carb|sachar/.test(k)) return 'carbs';
  if (/fat|tuk/.test(k)) return 'fat';
  return null;
}

function parseValue(raw: unknown): number | null {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null;
  if (typeof raw !== 'string') return null;
  // "5 286 kcal", "128g", "1,5" → number
  const match = raw.replace(/\s+/g, '').replace(',', '.').match(/-?\d+(\.\d+)?/);
  if (!match) return null;
  const parsed = parseFloat(match[0]);
  return Number.isFinite(parsed) ? parsed : null;
}

function plausible(values: Partial<Record<NutrientKey, number>>): boolean {
  for (const [key, value] of Object.entries(values) as [NutrientKey, number][]) {
    if (value <= 0) return false;
    if (key === 'calories' && (value < KCAL_MIN || value > KCAL_MAX)) return false;
    if (key !== 'calories' && value > MACRO_MAX_G) return false;
  }
  return true;
}

function roundValue(key: NutrientKey, value: number): number {
  if (key === 'calories') return Math.round(value);
  return value < 10 ? Math.round(value * 10) / 10 : Math.round(value);
}

/** What the raw `nutritional_info` numbers cover. 'total' = all `servings`
 * portions (curated recipes, where the backend knows the basis); undefined =
 * unknown (LLM-authored meals), which falls back to the plausibility guess. */
export type NutritionBasis = 'total' | 'portion';

/**
 * The nutrition basis for a recipe payload. A recipe sourced from the curated
 * corpus was rendered by `scale_recipe_to_meal`, whose nutrition covers all
 * `servings` portions; LLM-authored meals declare no basis and fall back to the
 * plausibility guess. `curated_recipe_slug` is already stored on every Recipe
 * row, so this reads correctly for plans generated before the fix too.
 */
export function nutritionBasisFor(
  recipe: { curated_recipe_slug?: string | null } | null | undefined,
): NutritionBasis | undefined {
  return recipe?.curated_recipe_slug ? 'total' : undefined;
}

/**
 * Returns per-portion nutrient rows in display order, or null when the card
 * should not be shown at all (no recognized data, or values implausible even
 * after dividing by the serving count).
 *
 * Pass `basis: 'total'` whenever the caller KNOWS the numbers cover all
 * `servings` portions. The plausibility heuristic below can only catch totals
 * that look absurd as a single portion, so a 2-portion recipe totalling
 * 616 kcal sails through it and gets shown as "na porci" (prod recipe 175).
 */
export function normalizeNutrition(
  info: Record<string, unknown> | null | undefined,
  servings: number | null | undefined,
  basis?: NutritionBasis,
): NutrientRow[] | null {
  if (!info) return null;
  const values: Partial<Record<NutrientKey, number>> = {};
  for (const [key, raw] of Object.entries(info)) {
    const nutrient = classifyKey(key);
    if (!nutrient || nutrient in values) continue;
    const parsed = parseValue(raw);
    if (parsed != null) values[nutrient] = parsed;
  }
  if (Object.keys(values).length === 0) return null;

  const s = servings && servings > 1 ? servings : null;
  const divide = () =>
    Object.fromEntries(
      Object.entries(values).map(([k, v]) => [k, (v as number) / s!]),
    ) as Partial<Record<NutrientKey, number>>;

  let perPortion = values;
  if (basis === 'total') {
    // Known basis wins over the guess: divide whether or not the total looked
    // plausible on its own.
    if (s) perPortion = divide();
  } else if (!plausible(values)) {
    if (!s) return null;
    perPortion = divide();
  }
  if (!plausible(perPortion)) return null;

  return DISPLAY_ORDER.filter((key) => perPortion[key] != null).map((key) => ({
    key,
    label: LABELS[key],
    value: roundValue(key, perPortion[key]!),
    unit: key === 'calories' ? 'kcal' : 'g',
  }));
}
