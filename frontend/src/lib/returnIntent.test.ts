import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { RETURN_KEY } from './storageKeys';
import { RETURN_MAX_AGE_MS, afterLoginPath, setReturnIntent, takeReturnIntent } from './returnIntent';

describe('return intent', () => {
  beforeEach(() => { localStorage.clear(); });
  afterEach(() => { vi.useRealTimers(); });

  it('returns a fresh allowlisted path once', () => {
    setReturnIntent('/hledat?plan=1');
    expect(takeReturnIntent()).toBe('/hledat?plan=1');
    expect(localStorage.getItem(RETURN_KEY)).toBeNull();
    expect(takeReturnIntent()).toBeNull();
  });

  it('ignores a stale intent', () => {
    localStorage.setItem(RETURN_KEY, JSON.stringify({ path: '/nakup', ts: Date.now() - RETURN_MAX_AGE_MS - 1 }));
    expect(takeReturnIntent()).toBeNull();
    expect(localStorage.getItem(RETURN_KEY)).toBeNull();
  });

  it('ignores paths outside the allowlist and the old bare-string format', () => {
    localStorage.setItem(RETURN_KEY, JSON.stringify({ path: 'https://evil.example', ts: Date.now() }));
    expect(takeReturnIntent()).toBeNull();
    localStorage.setItem(RETURN_KEY, '/nakup');
    expect(takeReturnIntent()).toBeNull();
  });

  it('maps return paths to the page to open', () => {
    expect(afterLoginPath('/nakup')).toBe('/nakup?vitej=1');
    expect(afterLoginPath('/hledat?plan=1')).toBe('/hledat?plan=1');
    expect(afterLoginPath(null)).toBe('/');
  });
});
