// Per-recipe portion scaling helpers. Pure functions — no React, no I/O.
// Mirrors toprecepty.cz's model: exact base value per ingredient, scaled
// linearly to the chosen portion count, rounded only for display.

export type PluralForms = [one: string, few: string, many: string];

// 1 porce / 2-4 porce / 5+ porcí
export const PORTION_FORMS: PluralForms = ['porce', 'porce', 'porcí'];

// Counted Czech units that inflect. Metric units (g/kg/ml/l/ks) are invariant
// and intentionally absent — they pass through verbatim.
export const UNIT_PLURALS: Record<string, PluralForms> = {
  'lžíce': ['lžíce', 'lžíce', 'lžic'],
  'lžička': ['lžička', 'lžičky', 'lžiček'],
  'vejce': ['vejce', 'vejce', 'vajec'],
  'plátek': ['plátek', 'plátky', 'plátků'],
  'hrnek': ['hrnek', 'hrnky', 'hrnků'],
  'konzerva': ['konzerva', 'konzervy', 'konzerv'],
  'špetka': ['špetka', 'špetky', 'špetek'],
};

export interface IngredientInput {
  name: string;
  quantity: number | string | null;
  unit?: string | null;
  optional?: boolean;
}

export interface ScaledIngredient {
  name: string;
  amountLabel: string | null; // null when quantity-less ("to taste")
  optional: boolean;
}

export function scaleAmount(qty: number, baseServings: number, chosen: number): number {
  const base = baseServings > 0 ? baseServings : 1;
  return qty * (chosen / base);
}

export function czechPlural(n: number, forms: PluralForms): string {
  if (n === 1) return forms[0];
  if (n >= 2 && n <= 4) return forms[1];
  return forms[2];
}

export function pluralizeUnit(value: number, unit: string | null | undefined): string {
  if (!unit) return '';
  const forms = UNIT_PLURALS[unit];
  if (!forms) return unit; // metric / unknown -> verbatim
  if (Number.isInteger(value)) return czechPlural(value, forms);
  return forms[1]; // fractional decimals read naturally with the few-form
}

export function roundForUnit(value: number, unit: string | null | undefined): number {
  const u = (unit || '').toLowerCase();
  let step: number;
  let rounded: number;
  if (u === 'g' || u === 'ml') {
    step = 1;
    rounded = Math.round(value);
  } else if (u === 'kg' || u === 'l') {
    step = 0.1;
    rounded = Math.round(value * 10) / 10;
  } else if (u === 'ks' || u === '') {
    step = 0.5; // allow halves
    rounded = Math.round(value * 2) / 2;
  } else {
    step = 0.25; // counted units (lžíce, špetka…) read naturally in quarters
    rounded = Math.round(value * 4) / 4;
  }
  // A positive quantity must never display as 0 — clamp to the smallest step.
  return value > 0 && rounded === 0 ? step : rounded;
}

export function formatNumber(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  return rounded.toString().replace('.', ',');
}

export function formatScaledIngredient(
  ing: IngredientInput,
  baseServings: number,
  chosen: number,
): ScaledIngredient {
  const qty = ing.quantity;
  const optional = !!ing.optional;
  if (typeof qty !== 'number' || !(qty > 0)) {
    return { name: ing.name, amountLabel: null, optional };
  }
  const rounded = roundForUnit(scaleAmount(qty, baseServings, chosen), ing.unit);
  const unitLabel = pluralizeUnit(rounded, ing.unit);
  const num = formatNumber(rounded);
  return { name: ing.name, amountLabel: unitLabel ? `${num} ${unitLabel}` : num, optional };
}
