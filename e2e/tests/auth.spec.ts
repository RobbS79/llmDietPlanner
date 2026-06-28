import { test, expect } from '@playwright/test';
import { makeFakeJwt } from '../fixtures/auth';

/**
 * Client-side auth behaviour: route guards, /login-success token handling,
 * logout flow.
 *
 * The real Google OAuth callback (3rd-party redirect) can't be exercised
 * headlessly without a mock IDP — see the fixme test at the bottom.
 */

test.describe('auth - client side', () => {
  test('/login-success persists tokens from query string and redirects home', async ({ page }) => {
    // Stub the dashboard's API call so the redirect succeeds and the spinner clears.
    await page.route('**/api/goals/list/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success', data: [], error: null }),
      }),
    );

    await page.goto('/login-success?access=test-access-token&refresh=test-refresh-token');

    await expect(page).toHaveURL(/\/$/);

    const tokens = await page.evaluate(() => ({
      access: localStorage.getItem('access_token'),
      refresh: localStorage.getItem('refresh_token'),
    }));
    expect(tokens.access).toBe('test-access-token');
    expect(tokens.refresh).toBe('test-refresh-token');
  });

  test('/login-success without tokens redirects back to /login with an error', async ({ page }) => {
    await page.goto('/login-success');
    await expect(page).toHaveURL(/\/login\?error=auth_failed/);
  });

  test('logout clears tokens and returns user to /login', async ({ page }) => {
    // Seed a structurally-valid JWT (the guard decodes exp) + stub API so the
    // dashboard renders.
    await page.addInitScript((token) => {
      localStorage.setItem('access_token', token);
      localStorage.setItem('refresh_token', 'e2e-fake-refresh-token');
    }, makeFakeJwt());
    await page.route('**/api/goals/list/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success', data: [], error: null }),
      }),
    );
    await page.route('**/api/auth/profile/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success', data: { onboarding_completed: true }, error: null }),
      }),
    );

    await page.goto('/');
    // Dashboard heading: "Vaše plány."
    await expect(page.getByText(/plány/i).first()).toBeVisible();

    // Logout button — inside the desktop nav area, after the separator.
    const logoutBtn = page.locator('header .hidden.md\\:flex button');
    await logoutBtn.click();

    await expect(page).toHaveURL(/\/login$/);
    const tokenAfter = await page.evaluate(() => localStorage.getItem('access_token'));
    expect(tokenAfter).toBeNull();
  });

  // The full OAuth callback round-trip needs a mock Google IDP (or a real one
  // with a test account). We document the gap rather than fake the flow.
  test.fixme(
    'full Google OAuth callback round-trip — needs mock IDP',
    async () => {
      // To implement, run a small fake-google server that the Django callback
      // can hit, and seed GOOGLE_CLIENT_ID/SECRET pointing at it.
    },
  );
});
