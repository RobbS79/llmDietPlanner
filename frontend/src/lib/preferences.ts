// Single source of truth for onboarding/profile preference options and the
// derived meal-plan prompt. Consumed by Onboarding, CreatePlan, and (PR B) Settings.

export interface PreferenceOption {
  id: string;
  label: string;
  icon?: string;
  desc?: string;
}

export interface Preferences {
  goal: string;
  dietary_styles: string[];
  allergies: string[];
  household_size: number;
  weekly_budget: number;
  cooking_skill: string;
  cooking_time: string;
  country: string;
  shop: string;
}

export const GOALS: PreferenceOption[] = [
  { id: 'lose_weight', label: 'Chci zhubnout', icon: '🎯', desc: 'Snížit váhu zdravým způsobem' },
  { id: 'eat_healthy', label: 'Chci jíst zdravěji', icon: '🥗', desc: 'Vyvážená strava s nutričními hodnotami' },
  { id: 'save_money', label: 'Chci šetřit za jídlo', icon: '💰', desc: 'Levnější nákupy bez plýtvání' },
  { id: 'save_time', label: 'Chci šetřit čas', icon: '⏱️', desc: 'Rychlé recepty a hotový plán' },
];

export const DIETARY_STYLES: PreferenceOption[] = [
  { id: 'none', label: 'Bez omezení' },
  { id: 'vegetarian', label: 'Vegetarián' },
  { id: 'vegan', label: 'Vegan' },
  { id: 'gluten_free', label: 'Bezlepkové' },
  { id: 'keto', label: 'Keto / Low-carb' },
  { id: 'high_protein', label: 'Vysoko proteinové' },
];

export const ALLERGIES: PreferenceOption[] = [
  { id: 'none', label: 'Žádné alergie' },
  { id: 'lactose', label: 'Laktóza' },
  { id: 'gluten', label: 'Lepek' },
  { id: 'nuts', label: 'Ořechy' },
  { id: 'eggs', label: 'Vejce' },
  { id: 'fish', label: 'Ryby' },
  { id: 'soy', label: 'Sója' },
];

export const COOKING_SKILLS: PreferenceOption[] = [
  { id: 'beginner', label: 'Začátečník', desc: 'Jednoduché recepty, málo ingrediencí' },
  { id: 'intermediate', label: 'Pokročilý', desc: 'Středně náročné recepty' },
  { id: 'advanced', label: 'Zkušený kuchař', desc: 'Nebojím se i složitějších receptů' },
];

export const COOKING_TIMES: PreferenceOption[] = [
  { id: '15min', label: 'Do 15 min' },
  { id: '30min', label: 'Do 30 min' },
  { id: '60min', label: 'Do 60 min' },
  { id: 'unlimited', label: 'Čas nehraje roli' },
];

export const DEFAULT_PREFERENCES: Preferences = {
  goal: '',
  dietary_styles: [],
  allergies: [],
  household_size: 2,
  weekly_budget: 1500,
  cooking_skill: '',
  cooking_time: '',
  country: 'CZ',
  shop: 'ROHLIK',
};

// Multi-select rule with mutual exclusivity for the "none" sentinel.
// Extracted verbatim from Onboarding.toggleMulti.
export function toggleMultiValue(current: string[], id: string): string[] {
  if (id === 'none') return current.includes('none') ? [] : ['none'];
  const without = current.filter(v => v !== 'none');
  return without.includes(id) ? without.filter(v => v !== id) : [...without, id];
}

// Builds the Czech free-text prompt + dietary-restrictions string fed into
// plan generation. Extracted verbatim from CreatePlan's prefill effect.
export function buildPreferencesPrompt(
  prefs: Partial<Preferences>
): { prompt: string; restrictions: string } {
  const goalMap: Record<string, string> = { lose_weight: 'Chci zhubnout', eat_healthy: 'Chci jíst zdravěji', save_money: 'Chci šetřit za jídlo', save_time: 'Chci šetřit čas při vaření' };
  const styleMap: Record<string, string> = { vegetarian: 'vegetariánská strava', vegan: 'veganská strava', gluten_free: 'bezlepková dieta', keto: 'keto dieta', high_protein: 'vysoko proteinová strava' };
  const allergyMap: Record<string, string> = { lactose: 'bez laktózy', gluten: 'bez lepku', nuts: 'bez ořechů', eggs: 'bez vajec', fish: 'bez ryb', soy: 'bez sóji' };
  const skillMap: Record<string, string> = { beginner: 'jednoduché recepty pro začátečníky', intermediate: 'středně náročné recepty', advanced: 'i složitější recepty' };
  const timeMap: Record<string, string> = { '15min': 'Max 15 minut na přípravu', '30min': 'Max 30 minut na přípravu', '60min': 'Max 60 minut na přípravu' };

  const parts: string[] = [];
  if (prefs.goal) parts.push(goalMap[prefs.goal] || '');
  const styles = (prefs.dietary_styles || []).filter((s: string) => s !== 'none').map((s: string) => styleMap[s]).filter(Boolean);
  if (styles.length) parts.push(styles.join(', '));
  const allergies = (prefs.allergies || []).filter((a: string) => a !== 'none').map((a: string) => allergyMap[a]).filter(Boolean);
  if (allergies.length) parts.push(allergies.join(', '));
  if (prefs.household_size) parts.push(`Pro ${prefs.household_size} ${prefs.household_size === 1 ? 'osobu' : 'osoby'}`);
  if (prefs.weekly_budget) parts.push(`Rozpočet ${prefs.weekly_budget} ${prefs.country === 'SK' ? 'EUR' : 'CZK'}/týden`);
  if (prefs.cooking_skill) parts.push(skillMap[prefs.cooking_skill] || '');
  if (prefs.cooking_time && prefs.cooking_time !== 'unlimited') parts.push(timeMap[prefs.cooking_time] || '');

  const prompt = parts.filter(Boolean).join('. ') + '.';
  const restrictions = allergies.length > 0 ? allergies.join(', ') : '';
  return { prompt, restrictions };
}
