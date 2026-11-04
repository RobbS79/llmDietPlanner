// Where to send the visitor after Google or email login (spec 2026-11-03).
// Stored as {path, ts}; only allowlisted paths under 15 minutes old count, so a
// stale intent from someone else's session on a shared device is ignored.
import { RETURN_KEY } from './storageKeys';

export const RETURN_PATHS = ['/nakup', '/hledat?plan=1'] as const;
export type ReturnPath = (typeof RETURN_PATHS)[number];
export const RETURN_MAX_AGE_MS = 15 * 60 * 1000;

export const isReturnPath = (p: unknown): p is ReturnPath => (RETURN_PATHS as readonly unknown[]).includes(p);

export function setReturnIntent(path: ReturnPath): void {
  try { localStorage.setItem(RETURN_KEY, JSON.stringify({ path, ts: Date.now() })); } catch { /* private mode */ }
}

export function clearReturnIntent(): void {
  try { localStorage.removeItem(RETURN_KEY); } catch { /* ignore */ }
}

/** Read and remove the intent; null unless it is fresh and allowlisted. */
export function takeReturnIntent(): ReturnPath | null {
  let raw: string | null = null;
  try { raw = localStorage.getItem(RETURN_KEY); } catch { return null; }
  clearReturnIntent();
  try {
    const v = JSON.parse(raw || 'null');
    if (v && isReturnPath(v.path) && typeof v.ts === 'number' && Date.now() - v.ts >= 0 && Date.now() - v.ts < RETURN_MAX_AGE_MS) return v.path;
  } catch { /* corrupt */ }
  return null;
}

/** The page to open after login for a return path; '/nakup' attaches the basket. */
export const afterLoginPath = (p: ReturnPath | null): string => (p === '/nakup' ? '/nakup?vitej=1' : p ?? '/');
