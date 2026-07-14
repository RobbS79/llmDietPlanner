import { describe, it, expect, beforeEach, vi } from 'vitest';
import { readUtmParams, getConsent, setConsent, CONSENT_KEY } from './analytics';

describe('analytics utils', () => {
  beforeEach(() => { localStorage.clear(); });

  it('reads utm params + fbclid from a query string', () => {
    const utm = readUtmParams('?utm_source=facebook&utm_campaign=pilot&fbclid=xyz');
    expect(utm.utm_source).toBe('facebook');
    expect(utm.utm_campaign).toBe('pilot');
    expect(utm.fbclid).toBe('xyz');
  });

  it('returns empty strings for missing params', () => {
    const utm = readUtmParams('?foo=bar');
    expect(utm.utm_source).toBe('');
    expect(utm.fbclid).toBe('');
  });

  it('persists and reads consent decision', () => {
    expect(getConsent()).toBeNull();
    setConsent(true);
    expect(getConsent()).toBe(true);
    setConsent(false);
    expect(getConsent()).toBe(false);
    expect(localStorage.getItem(CONSENT_KEY)).not.toBeNull();
  });
});
