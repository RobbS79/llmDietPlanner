import { test, expect } from '@playwright/test';
import { stubGoogleOAuthRedirect } from '../helpers/mocks';

/**
 * Smoke tests — verify the app loads and the public surface renders
 * without JS errors. No auth required.
 */

test.describe('smoke', () => {
  test('login page renders the brand and Google sign-in button', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.goto('/login');

    // Brand wordmark: "vařto."
    await expect(page.getByText(/vařto/i).first()).toBeVisible();

    // Sign-in form elements (tab "Přihlášení" / submit "Přihlásit se")
    await expect(page.getByText(/přihlá/i).first()).toBeVisible();

    // Google OAuth button
    await expect(page.getByRole('button', { name: /pokračovat přes google/i })).toBeVisible();

    // Filter out noisy 3rd-party warnings; surface any real app errors.
    const fatal = consoleErrors.filter(
      (e) =>
        !/Failed to load resource.*favicon/i.test(e) &&
        !/Download the React DevTools/i.test(e),
    );
    expect(fatal, `unexpected console errors:\n${fatal.join('\n')}`).toEqual([]);
  });

  test('unauthenticated users see the public landing page at /', async ({ page }) => {
    // HomeRoute now renders a public <Landing /> for anonymous visitors instead
    // of bouncing to /login.
    await page.goto('/');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText(/Víte, co budete jíst/i).first()).toBeVisible();
  });

  test('unauthenticated users are bounced from /create to /login', async ({ page }) => {
    await page.goto('/create');
    await expect(page).toHaveURL(/\/login$/);
  });

  test('unknown routes redirect to / (the public landing page when anon)', async ({ page }) => {
    await page.goto('/this-route-does-not-exist');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText(/Víte, co budete jíst/i).first()).toBeVisible();
  });

  test('Google button triggers the backend OAuth redirect endpoint', async ({ page }) => {
    await stubGoogleOAuthRedirect(page);
    await page.goto('/login');

    await Promise.all([
      page.waitForURL(/\/api\/auth\/google\/login\//),
      page.getByRole('button', { name: /pokračovat přes google/i }).click(),
    ]);

    // We stub the response so the page lands on our placeholder, not Google.
    await expect(page.locator('#oauth-stub')).toBeVisible();
  });
});
