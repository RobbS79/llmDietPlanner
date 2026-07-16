import { describe, it, expect, vi, beforeEach } from 'vitest';
import { savePreferences, deleteAccountWithPassword, triggerDataExport } from './settings';
import { api } from './api';

vi.mock('./api', () => ({ api: { patch: vi.fn(), delete: vi.fn(), get: vi.fn() } }));

describe('savePreferences', () => {
  beforeEach(() => vi.clearAllMocks());
  it('PATCHes only the dietary_preferences payload', async () => {
    (api.patch as any).mockResolvedValue({ data: { status: 'success' } });
    await savePreferences({ goal: 'eat_healthy', num_days: 5 } as any);
    expect(api.patch).toHaveBeenCalledWith('/auth/profile/', { dietary_preferences: { goal: 'eat_healthy', num_days: 5 } });
  });
});

describe('deleteAccountWithPassword', () => {
  beforeEach(() => vi.clearAllMocks());
  it('DELETEs /auth/account/ with the password in the body', async () => {
    (api.delete as any).mockResolvedValue({ data: { status: 'success' } });
    await deleteAccountWithPassword('hunter2');
    expect(api.delete).toHaveBeenCalledWith('/auth/account/', { data: { password: 'hunter2' } });
  });
});

describe('triggerDataExport', () => {
  beforeEach(() => vi.clearAllMocks());
  it('requests the export as a blob', async () => {
    const blob = new Blob(['{}'], { type: 'application/json' });
    (api.get as any).mockResolvedValue({ data: blob });
    // downloadBlob touches DOM URL APIs — stub them
    (globalThis.URL as any).createObjectURL = vi.fn(() => 'blob:x');
    (globalThis.URL as any).revokeObjectURL = vi.fn();
    await triggerDataExport();
    expect(api.get).toHaveBeenCalledWith('/auth/export/', { responseType: 'blob' });
  });
});
