import { test, expect } from '../fixtures/auth';

/**
 * Visual capture pass for the auth-app → Market Paper re-skin.
 * Not an assertion suite — it drives each authenticated page (via the fake-JWT
 * + mocked-API auth fixture, so no real creds/backend are needed) and saves
 * desktop + mobile PNGs into ../ux-review/ for manual light-theme review.
 *
 * Run: npx playwright test tests/reskin-screenshots.spec.ts --project=chromium
 */

const OUT = '../ux-review';
const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };

// Three goals to exercise every Badge status colour: completed (green),
// failed (paprika), processing (blue/pending).
const seededGoals = [
  { id: 1, prompt: 'Mediterranean cutting protocol', city: 'Prague', num_days: 7, status: 'completed', created_at: new Date().toISOString() },
  { id: 2, prompt: 'High protein bulk', city: 'Brno', num_days: 14, status: 'processing_meal_plan', created_at: new Date().toISOString() },
  { id: 3, prompt: 'Keto reset week', city: 'Ostrava', num_days: 5, status: 'failed', created_at: new Date().toISOString() },
];

test.use({ mockOptions: { goals: seededGoals } });

/**
 * Endpoints the shared helpers/mocks.ts predates: the HomeRoute onboarding
 * gate (/auth/profile/) and PlanView's meal-instances fetch. Without these the
 * authed data pages hang on the LoadingScreen. onboarding_completed:true so the
 * HomeRoute renders Dashboard instead of bouncing to /onboarding.
 */
async function addMissingMocks(page: import('@playwright/test').Page) {
  await page.route('**/api/auth/profile/', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        data: { onboarding_completed: true, free_generations_remaining: 3, email: 'e2e@example.com' },
        error: null,
      }),
    }),
  );
  await page.route(/.*\/api\/goals\/\d+\/meal-instances\/$/, (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: [], error: null }),
    }),
  );
  // The shared fixture stubs /auth/refresh/ as a hard 401, so any stray 401 on
  // these data pages bounces the app to /login. Make refresh succeed instead so
  // the interceptor retries into the mocked endpoint and the page renders.
  await page.route('**/api/auth/refresh/', (r) =>
    r.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access: 'e2e-refreshed-access-token' }),
    }),
  );
}

async function shoot(page: import('@playwright/test').Page, name: string) {
  await page.setViewportSize(DESKTOP);
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/reskin-app-${name}-desktop.png`, fullPage: true });
  await page.setViewportSize(MOBILE);
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/reskin-app-${name}-mobile.png`, fullPage: true });
}

test('dashboard', async ({ authedPage: page }) => {
  await addMissingMocks(page);
  await page.goto('/');
  await expect(page.getByText(/Mediterranean cutting protocol/i)).toBeVisible({ timeout: 30_000 });
  await shoot(page, 'dashboard');
});

test('dashboard keyboard focus ring', async ({ authedPage: page }) => {
  await page.setViewportSize(DESKTOP);
  await addMissingMocks(page);
  await page.goto('/');
  await expect(page.getByText(/Mediterranean cutting protocol/i)).toBeVisible({ timeout: 30_000 });
  await page.keyboard.press('Tab');
  await page.keyboard.press('Tab');
  await page.waitForTimeout(300);
  await page.screenshot({ path: `${OUT}/reskin-app-focus-ring-desktop.png`, fullPage: false });
});

test('create plan', async ({ authedPage: page }) => {
  await addMissingMocks(page);
  await page.goto('/create');
  await expect(page.getByText(/plán/i).first()).toBeVisible({ timeout: 30_000 });
  await shoot(page, 'create');
});

test('plan view', async ({ authedPage: page }) => {
  await addMissingMocks(page);
  await page.goto('/plan/42');
  await expect(page.getByText(/Mocked Oats/i)).toBeVisible({ timeout: 30_000 });
  await shoot(page, 'plan');
});

test('recipe page', async ({ authedPage: page }) => {
  await addMissingMocks(page);
  await page.goto('/plan/42/recipe/42:1:breakfast:0');
  await expect(page.getByRole('heading', { name: /mocked oats/i })).toBeVisible({ timeout: 30_000 });
  await shoot(page, 'recipe');
});

test('onboarding', async ({ authedPage: page }) => {
  await addMissingMocks(page);
  await page.goto('/onboarding');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  await shoot(page, 'onboarding');
});

test('billing success', async ({ authedPage: page }) => {
  await addMissingMocks(page);
  await page.goto('/billing/success');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);
  await shoot(page, 'billing-success');
});
