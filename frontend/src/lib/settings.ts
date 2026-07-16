import { api } from '@/lib/api';
import type { Preferences } from '@/lib/preferences';

/** Persist edited preferences. Backend merges keys (Phase-1 B3), so send only what changed. */
export async function savePreferences(prefs: Partial<Preferences> & Record<string, unknown>): Promise<void> {
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
