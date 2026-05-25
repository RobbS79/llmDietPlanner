import { test, expect } from '../fixtures/auth';

/**
 * Shopping list page — full-page view with checkable items,
 * print button, and total cost.
 */

test.describe('shopping list page', () => {
  test.use({
    mockOptions: {
      statusSequence: [{ goal_status: 'completed' }],
    },
  });

  test('renders all shopping list items with prices', async ({ authedPage: page }) => {
    await page.goto('/plan/42/shopping-list');

    // Page heading
    await expect(page.getByRole('heading', { name: /your list/i })).toBeVisible({
      timeout: 10_000,
    });

    // Items from mock data
    await expect(page.getByText(/^Oats$/i)).toBeVisible();
    await expect(page.getByText(/chicken breast/i).first()).toBeVisible();
    await expect(page.getByText(/salmon fillet/i).first()).toBeVisible();

    // Prices
    await expect(page.getByText(/49/).first()).toBeVisible();
    await expect(page.getByText(/199/).first()).toBeVisible();
    await expect(page.getByText(/289/).first()).toBeVisible();

    // Item count
    await expect(page.getByText(/3 items/i)).toBeVisible();

    // Total
    await expect(page.getByText(/estimated total/i)).toBeVisible();
    await expect(page.getByText(/1234/)).toBeVisible();
  });

  test('clicking items toggles checkmark and updates count', async ({ authedPage: page }) => {
    await page.goto('/plan/42/shopping-list');
    await expect(page.getByRole('heading', { name: /your list/i })).toBeVisible({
      timeout: 10_000,
    });

    // Initially 0 checked
    await expect(page.getByText(/0 checked off/i)).toBeVisible();

    // Click on Oats item card
    await page.getByText(/^Oats$/i).click();

    // Now 1 checked
    await expect(page.getByText(/1 checked off/i)).toBeVisible();

    // Click again to uncheck
    await page.getByText(/^Oats$/i).click();
    await expect(page.getByText(/0 checked off/i)).toBeVisible();
  });

  test('print button exists', async ({ authedPage: page }) => {
    await page.goto('/plan/42/shopping-list');
    await expect(page.getByRole('heading', { name: /your list/i })).toBeVisible({
      timeout: 10_000,
    });

    await expect(page.getByRole('button', { name: /print/i })).toBeVisible();
  });

  test('"Back to Plan" navigates back to plan view', async ({ authedPage: page }) => {
    await page.goto('/plan/42/shopping-list');
    await expect(page.getByRole('heading', { name: /your list/i })).toBeVisible({
      timeout: 10_000,
    });

    await page.getByText(/back to plan/i).click();
    await expect(page).toHaveURL(/\/plan\/42$/);
  });

  test('full flow: plan view -> shopping list -> back', async ({ authedPage: page }) => {
    // Start at plan view
    await page.goto('/plan/42');
    await expect(page.getByText(/your plan/i).first()).toBeVisible({ timeout: 30_000 });

    // Click "View Full List"
    await page.getByRole('button', { name: /view full list/i }).click();
    await expect(page).toHaveURL(/\/plan\/42\/shopping-list$/);

    // Verify shopping list loaded
    await expect(page.getByRole('heading', { name: /your list/i })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/^Oats$/i)).toBeVisible();

    // Navigate back
    await page.getByText(/back to plan/i).click();
    await expect(page).toHaveURL(/\/plan\/42$/);
  });
});
