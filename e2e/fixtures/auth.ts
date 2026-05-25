import { test as base, expect, Page } from '@playwright/test';
import { mockApi, MockOptions } from '../helpers/mocks';
import { env } from '../helpers/env';

/**
 * Auth fixture.
 *
 * The app is JWT-based and stores `access_token` / `refresh_token` in
 * localStorage. For most UI tests we don't actually need a backend-valid
 * token — we just need the React `ProtectedRoute` guard to pass, which only
 * checks `localStorage.getItem('access_token')`. So we inject a fake token
 * and mock the `/api/...` calls.
 *
 * If you set E2E_TEST_USERNAME + E2E_TEST_PASSWORD the helper below
 * `loginViaApi` will use the real /api/auth/login/ endpoint and return real
 * tokens — useful for tests that hit the real backend.
 */

type Fixtures = {
  authedPage: Page;
  mockOptions: MockOptions;
};

export const test = base.extend<Fixtures>({
  // Allow per-test override of mock data by re-declaring `mockOptions`.
  mockOptions: [{}, { option: true }],

  authedPage: async ({ page, mockOptions }, use) => {
    await mockApi(page, mockOptions);

    // Seed a fake JWT before any app code runs. The string contents don't matter
    // because we mock /api/* — the React guard only checks presence.
    await page.addInitScript(() => {
      window.localStorage.setItem('access_token', 'e2e-fake-access-token');
      window.localStorage.setItem('refresh_token', 'e2e-fake-refresh-token');
    });

    await use(page);
  },
});

export { expect };

/**
 * Hit Django's /api/auth/login/ to get real JWTs. Only works if you've
 * provisioned a test user (see e2e/README.md). Returns null if creds aren't set.
 */
export async function loginViaApi(
  request: import('@playwright/test').APIRequestContext,
): Promise<{ access: string; refresh: string } | null> {
  if (!env.testUser.username || !env.testUser.password) return null;
  const res = await request.post(`${env.apiURL}/api/auth/login/`, {
    data: {
      username: env.testUser.username,
      password: env.testUser.password,
    },
  });
  if (!res.ok()) return null;
  const body = await res.json();
  if (body?.status !== 'success') return null;
  return { access: body.data.access, refresh: body.data.refresh };
}
