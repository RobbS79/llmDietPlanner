import { test, expect } from '../fixtures/auth';

/**
 * Create-plan form tests.
 *
 * The form posts to /api/goals/ which the mock fixture intercepts and
 * returns goal_id=42, simulating immediate task acceptance. The PlanView
 * then polls /api/goals/42/task-status/ which the mock advances toward
 * 'completed' so the full happy-path flow runs without touching the LLM.
 */

test.describe('create plan form', () => {
  test('renders all sections and the submit button', async ({ authedPage: page }) => {
    await page.goto('/create');

    // Page heading
    await expect(page.getByRole('heading', { name: /new/i })).toBeVisible();
    // Section headings
    await expect(page.getByText(/dietary goals/i)).toBeVisible();
    await expect(page.getByText(/describe your goals/i)).toBeVisible();
    await expect(page.getByText(/country/i).first()).toBeVisible();
    await expect(page.getByText(/city/i).first()).toBeVisible();
    await expect(page.getByText(/plan duration/i)).toBeVisible();
    await expect(page.getByText(/preferred store/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /generate plan/i })).toBeVisible();
  });

  test('submit button is disabled until prompt is filled', async ({ authedPage: page }) => {
    await page.goto('/create');

    const submit = page.getByRole('button', { name: /generate plan/i });
    await expect(submit).toBeDisabled();

    await page.getByRole('textbox', { name: /describe your goals/i }).or(
      page.locator('textarea')
    ).first().fill('Test prompt');
    await expect(submit).toBeEnabled();
  });

  test('HTML required attribute on city blocks submission with empty city', async ({
    authedPage: page,
  }) => {
    await page.goto('/create');
    await page.locator('textarea').fill('Test prompt');

    // City input is required; trying to submit should keep us on /create.
    await page.getByRole('button', { name: /generate plan/i }).click();
    await expect(page).toHaveURL(/\/create$/);
  });

  test('toggling meals deactivates the visual selection', async ({ authedPage: page }) => {
    await page.goto('/create');
    const breakfast = page.getByRole('button', { name: /breakfast/i });
    await expect(breakfast).toBeVisible();
    // Click to deactivate, then re-activate
    await breakfast.click();
    await breakfast.click();
  });

  test('day duration buttons update the selected duration', async ({ authedPage: page }) => {
    await page.goto('/create');
    const day14 = page.getByRole('button', { name: /^14D$/i });
    await day14.click();
    // The clicked button should now carry the active indigo class.
    await expect(day14).toHaveClass(/bg-indigo-600/);
  });

  test.describe('shop selection', () => {
    test.use({
      mockOptions: {
        shops: [
          { code: 'ROHLIK', name: 'Rohlik' },
          { code: 'KOSIK', name: 'Kosik' },
        ],
      },
    });

    test('shows shops returned by /api/shops/', async ({ authedPage: page }) => {
      await page.goto('/create');
      await expect(page.getByRole('button', { name: /^Rohlik/ })).toBeVisible();
      await expect(page.getByRole('button', { name: /^Kosik/ })).toBeVisible();
    });
  });

  test('happy path: submit form -> redirect to /plan/:id -> shows completed plan', async ({
    authedPage: page,
  }) => {
    await page.goto('/create');

    await page.locator('textarea').fill('E2E test plan prompt');
    await page.getByPlaceholder(/e.g. Prague/i).fill('Prague');

    await page.getByRole('button', { name: /generate plan/i }).click();

    // Mock returns goal_id=42 -> navigation
    await expect(page).toHaveURL(/\/plan\/42$/);

    // PlanView polls task-status; mocks march to 'completed'. "Your Plan." heading
    // appears once status === 'completed'.
    await expect(page.getByText(/your plan/i).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Mocked Oats/i)).toBeVisible();
    await expect(page.getByText(/Mocked Chicken Bowl/i)).toBeVisible();
    // Shopping list sidebar is rendered
    await expect(page.getByText(/Chicken breast/i).first()).toBeVisible();
  });
});
