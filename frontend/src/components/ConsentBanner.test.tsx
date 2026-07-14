import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axios from 'axios';
import { ConsentBanner } from './ConsentBanner';
import { CONSENT_KEY } from '@/lib/analytics';

// The consent endpoint (ConsentView) is IsAuthenticated. An anonymous visitor
// must therefore NOT hit it — otherwise every banner click on the ad funnel
// produces a 401 console error. Anonymous consent lives in localStorage and
// rides the signup payload; only an authenticated visitor syncs to the server.
describe('ConsentBanner', () => {
  beforeEach(() => {
    localStorage.removeItem(CONSENT_KEY);
    localStorage.removeItem('access_token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.removeItem('access_token');
  });

  it('persists the decision locally WITHOUT calling the server for an anonymous visitor', async () => {
    const postSpy = vi.spyOn(axios, 'post');
    const originalHref = window.location.href;

    render(<ConsentBanner />);
    expect(await screen.findByRole('dialog')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Odmítnout' }));

    // Banner hides, decision persists locally — but no request is made (no
    // access_token), so there is no 401 and nothing navigates us away.
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
    expect(postSpy).not.toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem(CONSENT_KEY) || '{}').consent).toBe(false);
    expect(window.location.href).toBe(originalHref);
  });

  it('posts the consent decision for an authenticated visitor', async () => {
    localStorage.setItem('access_token', 'fake-jwt');
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
