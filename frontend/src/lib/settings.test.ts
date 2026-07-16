import { describe, it, expect, vi, beforeEach } from 'vitest';
import { savePreferences, deleteAccountWithPassword, triggerDataExport } from './settings';
import { api } from './api';

vi.mock('./api', () => ({ api: { patch: vi.fn(), delete: vi.fn(), get: vi.fn() } }));

describe('savePreferences', () => {
  beforeEach(() => vi.clearAllMocks());
  it('PATCHes only the dietary_preferences payload', async () => {
    vi.mocked(api.patch).mockResolvedValue({ data: { status: 'success' } });
    await savePreferences({ goal: 'eat_healthy', num_days: 5 });
    expect(api.patch).toHaveBeenCalledWith('/auth/profile/', { dietary_preferences: { goal: 'eat_healthy', num_days: 5 } });
  });
});

describe('deleteAccountWithPassword', () => {
  beforeEach(() => vi.clearAllMocks());
  it('DELETEs /auth/account/ with the password in the body', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { status: 'success' } });
    await deleteAccountWithPassword('hunter2');
    expect(api.delete).toHaveBeenCalledWith('/auth/account/', { data: { password: 'hunter2' } });
  });
});

describe('triggerDataExport', () => {
  beforeEach(() => vi.clearAllMocks());
  it('requests the export as a blob', async () => {
    const blob = new Blob(['{}'], { type: 'application/json' });
    vi.mocked(api.get).mockResolvedValue({ data: blob });
    // downloadBlob touches DOM URL APIs — jsdom doesn't implement them, so
    // vi.spyOn can't wrap a non-existent property; define them directly.
    Object.defineProperty(URL, 'createObjectURL', { value: vi.fn(() => 'blob:x'), configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: vi.fn(), configurable: true });
    await triggerDataExport();
    expect(api.get).toHaveBeenCalledWith('/auth/export/', { responseType: 'blob' });
  });
});
