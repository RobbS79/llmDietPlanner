import { api } from '@/lib/api';

export type BillingTier = 'standard' | 'premium';

export interface SubscriptionInfo {
  tier: BillingTier;
  status: string;
  source: 'stripe' | 'promo';
  current_period_end: string | null;
  grant_expires_at: string | null;
  cancel_at_period_end: boolean;
  plans_used_this_period: number;
  entitled: boolean;
  remaining_quota: number;
}

export interface BillingMe {
  subscription: SubscriptionInfo | null;
  free_generations_remaining: number;
}

/**
 * Start a Stripe Checkout session for the given tier and redirect the browser
 * to Stripe's hosted page. Resolves only on failure (otherwise the page
 * navigates away).
 */
export async function startCheckout(tier: BillingTier): Promise<void> {
  const { data } = await api.post('/billing/checkout/', { tier });
  if (data?.url) {
    window.location.href = data.url;
  }
}

/** Open the Stripe Customer Portal (cancel / update card / invoices). */
export async function openBillingPortal(): Promise<void> {
  const { data } = await api.post('/billing/portal/', {});
  if (data?.url) {
    window.location.href = data.url;
  }
}

/** Fetch the current user's subscription + remaining quota. */
export async function fetchBillingMe(): Promise<BillingMe> {
  const { data } = await api.get('/billing/me/');
  return data;
}

export const TIER_LABELS: Record<BillingTier, string> = { standard: 'Standard', premium: 'Premium' };

/**
 * One-line quota status for the dashboard header. Subscribers (Stripe or
 * promo) see their tier + monthly usage; everyone else the free counter.
 */
export function quotaHeadline(billing: BillingMe | undefined, freeRemaining: number): string {
  const sub = billing?.subscription;
  if (sub?.entitled) {
    const total = sub.plans_used_this_period + sub.remaining_quota;
    return `${TIER_LABELS[sub.tier]} · ${sub.plans_used_this_period} z ${total} jídelníčků tento měsíc`;
  }
  return `${freeRemaining} plánů zdarma zbývá`;
}
