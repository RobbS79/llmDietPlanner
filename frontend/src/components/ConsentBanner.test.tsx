import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import { ConsentBanner } from './ConsentBanner';
import { CONSENT_KEY } from '@/lib/analytics';

// Regression test for the critical finding: the shared `api` axios instance
// has a response interceptor that redirects to /login on an unrefreshable
// 401. The consent endpoint is IsAuthenticated, so an anonymous visitor
// clicking the banner must NOT trigger that redirect — the ping has to go
// out over bare axios instead.
describe('ConsentBanner', () => {
  beforeEach(() => {
    localStorage.removeItem(CONSENT_KEY);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hides and persists the decision without navigating, even when the consent ping 401s (anonymous visitor)', async () => {
    const postSpy = vi.spyOn(axios, 'post').mockRejectedValue({
      response: { status: 401 },
    });
    const originalHref = window.location.href;

    render(<ConsentBanner />);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Odmítnout' }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        '/api/analytics/consent/',
        { consent: false, version: expect.any(String) },
      );
    });

    // Banner hides and the decision is persisted locally regardless of the
    // 401 — and critically, nothing navigated us away.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(CONSENT_KEY) || '{}').consent).toBe(false);
    expect(window.location.href).toBe(originalHref);
  });

  it('posts the consent decision for an authenticated visitor', async () => {
    const postSpy = vi.spyOn(axios, 'post').mockResolvedValue({ status: 200, data: {} });

    render(<ConsentBanner />);
    await userEvent.click(await screen.findByRole('button', { name: 'Přijmout' }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        '/api/analytics/consent/',
        { consent: true, version: expect.any(String) },
      );
    });
    expect(JSON.parse(localStorage.getItem(CONSENT_KEY) || '{}').consent).toBe(true);
  });
});
