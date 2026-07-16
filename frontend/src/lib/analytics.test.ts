import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import axios from 'axios';
import { readUtmParams, getConsent, setConsent, syncConsentToServer, CONSENT_KEY, CONSENT_VERSION } from './analytics';

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

// syncConsentToServer closes the "opted in while anonymous, then LOGGED IN
// (not registered)" gap: registration carries consent in its payload, a plain
// login does not, and the banner won't re-show for a returning user.
describe('syncConsentToServer', () => {
  beforeEach(() => { localStorage.clear(); });
  afterEach(() => { vi.restoreAllMocks(); });

  it('does nothing when no consent decision is stored', async () => {
    const postSpy = vi.spyOn(axios, 'post');
    localStorage.setItem('access_token', 'tok');
    await syncConsentToServer();
    expect(postSpy).not.toHaveBeenCalled();
  });

  it('does nothing when not authenticated', async () => {
    const postSpy = vi.spyOn(axios, 'post');
    setConsent(true);
    await syncConsentToServer();
    expect(postSpy).not.toHaveBeenCalled();
  });

  it('posts the stored consent when authenticated', async () => {
    const postSpy = vi.spyOn(axios, 'post').mockResolvedValue({ status: 200, data: {} } as never);
    setConsent(false);
    localStorage.setItem('access_token', 'tok');
    await syncConsentToServer();
    expect(postSpy).toHaveBeenCalledWith(
      '/api/analytics/consent/',
      { consent: false, version: CONSENT_VERSION },
      { headers: { Authorization: 'Bearer tok' } },
    );
  });

  it('swallows a failed sync (best-effort — local decision stands)', async () => {
    vi.spyOn(axios, 'post').mockRejectedValue({ response: { status: 401 } });
    setConsent(true);
    localStorage.setItem('access_token', 'tok');
    await expect(syncConsentToServer()).resolves.toBeUndefined();
  });
});
