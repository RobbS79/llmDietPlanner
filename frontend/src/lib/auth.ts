import axios from 'axios';

const TOKEN_KEYS = ['access_token', 'refresh_token'] as const;

export function clearAuthTokens() {
  TOKEN_KEYS.forEach((key) => localStorage.removeItem(key));
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
    clearAuthTokens();
    return false;
  }
}
