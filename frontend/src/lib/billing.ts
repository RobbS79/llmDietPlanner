import { api } from '@/lib/api';

export type BillingTier = 'standard' | 'premium';

export interface SubscriptionInfo {
  tier: BillingTier;
  status: string;
  current_period_end: string | null;
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
