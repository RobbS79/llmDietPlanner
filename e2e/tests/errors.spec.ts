import { test, expect } from '../fixtures/auth';

/**
 * Error-state coverage for the React app:
 *  - network failure on the dashboard list endpoint
 *  - 401 on goals/list causes the axios interceptor to bounce to /login
 *  - 404 catch-all (unknown route) redirects to / (then /login if anon)
 *
 * The frontend does not currently render an explicit 404 page; the catch-all
 * route does <Navigate to="/" replace />. We assert that behaviour rather than
 * a 404 component.
 */

test.describe('error handling', () => {
  test('dashboard handles network failure on /api/goals/list/ gracefully', async ({
    authedPage: page,
  }) => {
    // Override the default mock: simulate a network failure.
    await page.route('**/api/goals/list/', (route) => route.abort('failed'));

    await page.goto('/');

    // App shouldn't crash to a white screen. The dashboard chrome (heading +
    // skeletons) still renders even though the goals list never resolves.
    await expect(page.locator('body')).toBeVisible();
    // Dashboard heading "Vaše plány." is always rendered — graceful degradation.
    await expect(page.getByText(/plány/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test('401 from goals/list redirects user to /login (axios interceptor)', async ({
    authedPage: page,
  }) => {
    // First call returns 401; refresh call returns 401 too -> localStorage cleared, /login.
    await page.route('**/api/goals/list/', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'expired' }),
      }),
    );
    await page.route('**/api/auth/refresh/', (route) =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'bad refresh' }),
      }),
    );

    await page.goto('/');
    await expect(page).toHaveURL(/\/login$/, { timeout: 45_000 });
  });

  test('unknown route while authed lands on / (the dashboard)', async ({ authedPage: page }) => {
    await page.goto('/nope/does/not/exist');
    await expect(page).toHaveURL(/\/$/);
    // Dashboard should render
    await expect(page.getByText(/plány/i).first()).toBeVisible();
  });
});
