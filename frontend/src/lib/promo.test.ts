import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  validatePromo, redeemPromo, discountedPrice,
  getPendingPromo, setPendingPromo, clearPendingPromo, PENDING_PROMO_KEY, validPromoMessage,
} from './promo';
import { api } from './api';

vi.mock('./api', () => ({ api: { get: vi.fn(), post: vi.fn() } }));

describe('pending promo storage', () => {
  beforeEach(() => localStorage.clear());
  it('round-trips an upper-cased, trimmed code', () => {
    setPendingPromo('  leto2026 ');
    expect(localStorage.getItem(PENDING_PROMO_KEY)).toBe('LETO2026');
    expect(getPendingPromo()).toBe('LETO2026');
  });
  it('returns null when empty and after clear', () => {
    expect(getPendingPromo()).toBeNull();
    setPendingPromo('X');
    clearPendingPromo();
    expect(getPendingPromo()).toBeNull();
  });
  it('ignores blank input', () => {
    setPendingPromo('   ');
    expect(getPendingPromo()).toBeNull();
  });
});

describe('discountedPrice', () => {
  it('matches backend rounding', () => {
    expect(discountedPrice(199, 100)).toBe(0);
    expect(discountedPrice(199, 50)).toBe(100);
    expect(discountedPrice(99, 33)).toBe(66);
    expect(discountedPrice(197, 50)).toBe(99);
  });
});

describe('API wrappers', () => {
  beforeEach(() => vi.clearAllMocks());
  it('validatePromo GETs with the code as a query param', async () => {
    vi.mocked(api.get).mockResolvedValue({ data: { valid: false, reason: 'not_found' } });
    const out = await validatePromo('abc');
    expect(api.get).toHaveBeenCalledWith('/billing/promo/validate/', { params: { code: 'abc' } });
    expect(out).toEqual({ valid: false, reason: 'not_found' });
  });
  it('redeemPromo POSTs code and tier', async () => {
    vi.mocked(api.post).mockResolvedValue({ data: { granted: true, tier: 'premium' } });
    const out = await redeemPromo('abc', 'premium');
    expect(api.post).toHaveBeenCalledWith('/billing/promo/redeem/', { code: 'abc', tier: 'premium' });
    expect(out).toEqual({ granted: true, tier: 'premium' });
  });
});

describe('validPromoMessage', () => {
  const base = { valid: true as const, code: 'TEST100', percent_off: 100, duration_kind: 'lifetime' as const, duration_months: null, tiers: ['premium'] };
  it('tells a 100 % user to click "Aktivovat zdarma" on the free tier', () => {
    const msg = validPromoMessage({ ...base, prices: { premium: { original: 199, discounted: 0 } } });
    expect(msg).toBe('Kód TEST100: sleva 100 % navždy. Klikněte na „Aktivovat zdarma“ u tarifu Premium.');
  });
  it('names every tier the 100 % code applies to', () => {
    const msg = validPromoMessage({ ...base, tiers: [], prices: { standard: { original: 99, discounted: 0 }, premium: { original: 199, discounted: 0 } } });
    expect(msg).toContain('u tarifu Standard nebo Premium.');
  });
  it('tells a partial-discount user the discount applies at checkout', () => {
    const msg = validPromoMessage({ ...base, percent_off: 50, duration_kind: 'months', duration_months: 3, prices: { premium: { original: 199, discounted: 100 } } });
    expect(msg).toBe('Kód TEST100: sleva 50 % na 3 měs. Sleva se uplatní při platbě.');
  });
});
