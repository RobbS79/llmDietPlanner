import { api } from '@/lib/api';
import type { BillingTier } from '@/lib/billing';

export const PENDING_PROMO_KEY = 'pending_promo';

export type PromoReason =
  | 'not_found' | 'inactive' | 'expired' | 'exhausted'
  | 'tier_not_allowed' | 'already_redeemed' | 'already_subscribed' | 'stripe_error';

export type PromoDurationKind = 'lifetime' | 'months' | 'first_invoice';

export interface PromoPrice { original: number; discounted: number }

export type PromoValidation =
  | { valid: false; reason: PromoReason }
  | {
      valid: true;
      code: string;
      percent_off: number;
      duration_kind: PromoDurationKind;
      duration_months: number | null;
      tiers: BillingTier[];
      prices: Partial<Record<BillingTier, PromoPrice>>;
    };

export type PromoRedeemResult =
  | { granted: true; tier: BillingTier }
  | { granted: false; url: string };

export const PROMO_REASON_TEXT: Record<PromoReason, string> = {
  not_found: 'Tento kód neznáme.',
  inactive: 'Tento kód už není aktivní.',
  expired: 'Platnost kódu vypršela.',
  exhausted: 'Kód už byl využit maximálním počtem uživatelů.',
  tier_not_allowed: 'Tento kód nelze použít na zvolený tarif.',
  already_redeemed: 'Tento kód jste už použili.',
  already_subscribed: 'Máte aktivní předplatné, kód teď nelze uplatnit.',
  stripe_error: 'Platbu se nepodařilo zahájit. Zkuste to prosím znovu.',
};

/** Reasons after which keeping the code pending makes no sense. */
export const TERMINAL_REASONS: PromoReason[] = [
  'not_found', 'inactive', 'expired', 'exhausted', 'already_redeemed', 'already_subscribed',
];

/** Half-up, same as the backend's Decimal ROUND_HALF_UP (Math.round is half-up for positives). */
export function discountedPrice(original: number, percentOff: number): number {
  return Math.round((original * (100 - percentOff)) / 100);
}

export function durationText(kind: PromoDurationKind, months: number | null): string {
  if (kind === 'lifetime') return 'navždy';
  if (kind === 'months') return `na ${months ?? 1} měs.`;
  return 'na první měsíc';
}

export async function validatePromo(code: string): Promise<PromoValidation> {
  const { data } = await api.get('/billing/promo/validate/', { params: { code } });
  return data;
}

export async function redeemPromo(code: string, tier: BillingTier): Promise<PromoRedeemResult> {
  const { data } = await api.post('/billing/promo/redeem/', { code, tier });
  return data;
}

export function getPendingPromo(): string | null {
  try {
    return localStorage.getItem(PENDING_PROMO_KEY) || null;
  } catch {
    return null;
  }
}

export function setPendingPromo(code: string): void {
  const norm = code.trim().toUpperCase();
  if (!norm) return;
  try {
    localStorage.setItem(PENDING_PROMO_KEY, norm);
  } catch { /* storage unavailable — code just won't survive the login hop */ }
}

export function clearPendingPromo(): void {
  try {
    localStorage.removeItem(PENDING_PROMO_KEY);
  } catch { /* ignore */ }
}
