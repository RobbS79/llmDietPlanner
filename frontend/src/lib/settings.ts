import axios from 'axios';
import { api } from '@/lib/api';
import type { Preferences } from '@/lib/preferences';

/** Shape of GET /auth/profile/ `.data.data` (Phase-1 B4 fields). */
export interface Profile {
  email: string;
  username: string;
  free_generations_remaining: number;
  total_generations: number;
  onboarding_completed: boolean;
  dietary_preferences: Partial<Preferences> & Record<string, unknown>;
  primary_auth_provider: 'email' | 'google' | string;
  email_verified: boolean;
  marketing_consent: boolean;
  consent_version: string;
}

/** Persist edited preferences. Backend merges keys (Phase-1 B3), so send only what changed. */
export async function savePreferences(prefs: Record<string, unknown>): Promise<void> {
  await api.patch('/auth/profile/', { dietary_preferences: prefs });
}

/** Change password for email users (dj_rest_auth). */
export async function changePassword(oldPw: string, newPw: string): Promise<void> {
  await api.post('/auth/password/change/', {
    old_password: oldPw, new_password1: newPw, new_password2: newPw,
  });
}

/** Hard-delete the account (email users). Password goes in the DELETE body. */
export async function deleteAccountWithPassword(password: string): Promise<void> {
  await api.delete('/auth/account/', { data: { password } });
}

/** Download the user's data export as a JSON file (authenticated blob). */
export async function triggerDataExport(): Promise<void> {
  const res = await api.get('/auth/export/', { responseType: 'blob' });
  downloadBlob(res.data as Blob, 'moje-data.json');
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Server error payload shapes we encounter across the settings endpoints:
 * a flat `{error}` string (our own views) or dj_rest_auth's field-keyed
 * validation errors (e.g. `{old_password: ["..."]}`). */
interface ApiErrorPayload {
  error?: string;
  non_field_errors?: string[];
  [field: string]: unknown;
}

/** Pull a human-readable message out of an Axios error for inline display. */
export function extractApiError(err: unknown, fallback: string): string {
  if (!axios.isAxiosError<ApiErrorPayload>(err)) return fallback;
  const data = err.response?.data;
  if (!data) return fallback;
  if (typeof data.error === 'string' && data.error) return data.error;
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  }
  return fallback;
}
