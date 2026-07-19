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

/**
 * Returns per-portion nutrient rows in display order, or null when the card
 * should not be shown at all (no recognized data, or values implausible even
 * after dividing by the serving count).
 */
export function normalizeNutrition(
  info: Record<string, unknown> | null | undefined,
  servings: number | null | undefined,
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

  let perPortion = values;
  if (!plausible(values)) {
    const s = servings && servings > 1 ? servings : null;
    if (!s) return null;
    const divided = Object.fromEntries(
      Object.entries(values).map(([k, v]) => [k, (v as number) / s]),
    ) as Partial<Record<NutrientKey, number>>;
    if (!plausible(divided)) return null;
    perPortion = divided;
  }

  return DISPLAY_ORDER.filter((key) => perPortion[key] != null).map((key) => ({
    key,
    label: LABELS[key],
    value: roundValue(key, perPortion[key]!),
    unit: key === 'calories' ? 'kcal' : 'g',
  }));
}
