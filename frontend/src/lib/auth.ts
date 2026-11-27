import axios from 'axios';
import { BASKET_KEY, PENDING_PLAN_KEY, RETURN_KEY } from './storageKeys';

const TOKEN_KEYS = ['access_token', 'refresh_token'] as const;

/** Session expired: drop the tokens but keep the basket, so signing back in can still save it. */
export function clearSessionTokens() {
  TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
}

/** Logout or account deletion: also forget the basket, the return intent and a pending plan, so
 *  the next person on this device can't attach them to their own account.
 *  Removes the keys directly (not via basket.ts) to avoid an import cycle. */
export function clearAuthTokens() {
  clearSessionTokens();
  [BASKET_KEY, RETURN_KEY, PENDING_PLAN_KEY].forEach((key) => { try { localStorage.removeItem(key); } catch { /* ignore */ } });
}

export function isAccessTokenValid(): boolean {
  const token = localStorage.getItem('access_token');
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

export async function tryRefreshToken(): Promise<boolean> {
  const refresh = localStorage.getItem('refresh_token');
  if (!refresh) return false;
  try {
    const res = await axios.post('/api/auth/refresh/', { refresh });
    localStorage.setItem('access_token', res.data.access);
    return true;
  } catch {
    clearSessionTokens();
    return false;
  }
}

/** Before an authed action: a valid access token, or a successful refresh. False = treat as signed out. */
export async function confirmSession(): Promise<boolean> {
  return isAccessTokenValid() || tryRefreshToken();
}
