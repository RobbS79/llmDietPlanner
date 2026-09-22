import { describe, it, expect, vi } from 'vitest';
import { quotaHeadline, type BillingMe } from './billing';

vi.mock('./api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));

const sub = (over: Partial<NonNullable<BillingMe['subscription']>> = {}): BillingMe => ({
  subscription: {
    tier: 'premium', status: 'active', source: 'promo', current_period_end: null, grant_expires_at: null,
    cancel_at_period_end: false, plans_used_this_period: 0, entitled: true, remaining_quota: 30, ...over,
  },
  free_generations_remaining: 7,
});

describe('quotaHeadline', () => {
  it('shows the tier and monthly quota for an entitled subscriber', () => {
    expect(quotaHeadline(sub(), 7)).toBe('Premium · 0 z 30 jídelníčků tento měsíc');
  });
  it('counts used plans against the period total', () => {
    expect(quotaHeadline(sub({ tier: 'standard', plans_used_this_period: 3, remaining_quota: 4 }), 7))
      .toBe('Standard · 3 z 7 jídelníčků tento měsíc');
  });
  it('falls back to the free counter when the subscription is not entitled', () => {
    expect(quotaHeadline(sub({ status: 'canceled', entitled: false }), 7)).toBe('7 plánů zdarma zbývá');
  });
  it('uses the profile counter while billing has not loaded', () => {
    expect(quotaHeadline(undefined, 2)).toBe('2 plánů zdarma zbývá');
  });
});
