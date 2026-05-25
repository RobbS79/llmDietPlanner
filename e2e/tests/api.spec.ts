import { test, expect } from '@playwright/test';
import { env, hasRealTestUser } from '../helpers/env';
import { loginViaApi } from '../fixtures/auth';

/**
 * Django REST API tests using Playwright's `request` fixture.
 *
 * These hit the *real* backend at E2E_API_URL (default http://localhost:8000).
 * They check the public contract of the API surface — health, auth boundaries,
 * public shop list, and that protected endpoints return 401 without a JWT.
 */

test.describe('api - public surface', () => {
  test('GET /health/ returns 200 OK', async ({ request }) => {
    const res = await request.get(`${env.apiURL}/health/`);
    expect(res.status()).toBe(200);
    const body = await res.text();
    expect(body).toContain('OK');
  });

  test('GET /api/shops/?country=CZ returns the configured shops', async ({ request }) => {
    const res = await request.get(`${env.apiURL}/api/shops/?country=CZ`);
    expect(res.status()).toBe(200);
    const json = await res.json();
    expect(json.status).toBe('success');
    expect(json.data.country).toBe('CZ');
    expect(Array.isArray(json.data.shops)).toBe(true);
    // At least one shop should be returned for CZ (ROHLIK/KOSIK).
    expect(json.data.shops.length).toBeGreaterThan(0);
    for (const shop of json.data.shops) {
      expect(typeof shop.code).toBe('string');
      expect(typeof shop.name).toBe('string');
    }
  });

  test('GET /api/shops/ without country returns a 400 error', async ({ request }) => {
    const res = await request.get(`${env.apiURL}/api/shops/`);
    expect(res.status()).toBe(400);
    const json = await res.json();
    expect(json.status).toBe('error');
  });
});

test.describe('api - protected endpoints reject anonymous access', () => {
  test('GET /api/goals/list/ without auth is unauthorized', async ({ request }) => {
    const res = await request.get(`${env.apiURL}/api/goals/list/`);
    expect([401, 403]).toContain(res.status());
  });

  test('POST /api/goals/ without auth is unauthorized', async ({ request }) => {
    const res = await request.post(`${env.apiURL}/api/goals/`, {
      data: { is_draft: true, prompt: 'x', country: 'CZ', city: 'Prague' },
    });
    expect([401, 403]).toContain(res.status());
  });

  test('GET /api/goals/1/ without auth is unauthorized', async ({ request }) => {
    const res = await request.get(`${env.apiURL}/api/goals/1/`);
    expect([401, 403]).toContain(res.status());
  });
});

test.describe('api - auth endpoints', () => {
  test('POST /api/auth/login/ with bad creds returns 401', async ({ request }) => {
    const res = await request.post(`${env.apiURL}/api/auth/login/`, {
      data: { username: 'definitely-not-a-real-user-e2e', password: 'wrong-password' },
    });
    expect(res.status()).toBe(401);
    const json = await res.json();
    expect(json.status).toBe('error');
  });

  test('POST /api/auth/login/ with missing fields fails fast', async ({ request }) => {
    const res = await request.post(`${env.apiURL}/api/auth/login/`, {
      data: {},
    });
    // Pydantic schema validation surfaces a 500 with the validation message in
    // the current backend implementation; we accept any non-2xx.
    expect(res.ok()).toBe(false);
  });

  test('POST /api/auth/refresh/ with garbage token fails', async ({ request }) => {
    const res = await request.post(`${env.apiURL}/api/auth/refresh/`, {
      data: { refresh: 'not-a-real-jwt' },
    });
    expect(res.ok()).toBe(false);
  });

  test('GET /api/auth/google/login/ issues a redirect to Google', async ({ request }) => {
    // Don't auto-follow — we want to inspect the 302.
    const res = await request.get(`${env.apiURL}/api/auth/google/login/`, {
      maxRedirects: 0,
    });
    // If GOOGLE_CLIENT_ID is missing, the view returns 302 -> /login?error=google_not_configured.
    // Either way it's a 302; the Location header tells us which.
    expect(res.status()).toBe(302);
    const location = res.headers()['location'] ?? '';
    expect(location.length).toBeGreaterThan(0);
    expect(
      /accounts\.google\.com|\/login\?error=google_not_configured/.test(location),
    ).toBe(true);
  });
});

test.describe('api - authenticated flow (requires E2E_TEST_USERNAME/PASSWORD)', () => {
  test.skip(
    !hasRealTestUser(),
    'Set E2E_TEST_USERNAME and E2E_TEST_PASSWORD to run authenticated API tests.',
  );

  test('login + list goals returns success envelope', async ({ request }) => {
    const tokens = await loginViaApi(request);
    expect(tokens).not.toBeNull();
    const res = await request.get(`${env.apiURL}/api/goals/list/`, {
      headers: { Authorization: `Bearer ${tokens!.access}` },
    });
    expect(res.ok()).toBe(true);
    const json = await res.json();
    expect(json.status).toBe('success');
    expect(Array.isArray(json.data)).toBe(true);
  });

  test('creating a draft goal persists and returns goal_id', async ({ request }) => {
    const tokens = await loginViaApi(request);
    expect(tokens).not.toBeNull();
    const res = await request.post(`${env.apiURL}/api/goals/`, {
      headers: { Authorization: `Bearer ${tokens!.access}` },
      data: {
        is_draft: true,
        prompt: 'E2E draft prompt',
        country: 'CZ',
        city: 'Prague',
      },
    });
    expect(res.status()).toBe(201);
    const json = await res.json();
    expect(json.status).toBe('success');
    expect(typeof json.data.goal_id).toBe('number');
  });
});
