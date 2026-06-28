import { test as base, expect, Page } from '@playwright/test';
import { mockApi, MockOptions } from '../helpers/mocks';
import { env } from '../helpers/env';

/**
 * Auth fixture.
 *
 * The app is JWT-based and stores `access_token` / `refresh_token` in
 * localStorage. For most UI tests we don't need a backend-valid token, but the
 * React `ProtectedRoute` guard now decodes the access token and checks its
 * `exp` claim (see frontend/src/lib/auth.ts `isAccessTokenValid`). A non-JWT
 * placeholder fails that check, makes the guard attempt a token refresh, and —
 * since `/auth/refresh/` is mocked as a 401 — bounces the page to /login. So we
 * inject a structurally-valid, unsigned JWT with a far-future `exp` and mock
 * the `/api/...` calls.
 *
 * If you set E2E_TEST_USERNAME + E2E_TEST_PASSWORD the helper below
 * `loginViaApi` will use the real /api/auth/login/ endpoint and return real
 * tokens — useful for tests that hit the real backend.
 */

/**
 * A structurally-valid (but unsigned) JWT whose payload carries an `exp` far in
 * the future, so `isAccessTokenValid()` returns true. The signature segment is
 * a placeholder — the app never verifies it client-side; it only base64-decodes
 * the payload to read `exp`.
 */
export function makeFakeJwt(expSeconds = 4102444800 /* 2100-01-01 */): string {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString('base64');
  return `${b64({ alg: 'HS256', typ: 'JWT' })}.${b64({ user_id: 1, exp: expSeconds })}.e2e-not-a-real-signature`;
}

type Fixtures = {
  authedPage: Page;
  mockOptions: MockOptions;
};

export const test = base.extend<Fixtures>({
  // Allow per-test override of mock data by re-declaring `mockOptions`.
  mockOptions: [{}, { option: true }],

  authedPage: async ({ page, mockOptions }, use) => {
    await mockApi(page, mockOptions);

    // Seed a valid-looking JWT before any app code runs. Computed in Node (Buffer)
    // and passed into the browser, since the guard now decodes the token's exp.
    const accessToken = makeFakeJwt();
    await page.addInitScript((token) => {
      window.localStorage.setItem('access_token', token);
      window.localStorage.setItem('refresh_token', 'e2e-fake-refresh-token');
    }, accessToken);

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
