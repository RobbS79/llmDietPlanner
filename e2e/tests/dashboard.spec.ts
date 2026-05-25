import { test, expect } from '../fixtures/auth';

/**
 * Authenticated dashboard tests.
 */

test.describe('dashboard', () => {
  test('renders empty state when no goals exist', async ({ authedPage: page }) => {
    await page.goto('/');

    // Dashboard heading "Your Plans."
    await expect(page.getByText(/your/i).first()).toBeVisible();
    await expect(page.getByText(/plans/i).first()).toBeVisible();
    await expect(page.getByText(/no meal plans yet/i)).toBeVisible();
    await expect(page.getByText(/create your first plan/i)).toBeVisible();
  });

  test.describe('with seeded goals', () => {
    test.use({
      mockOptions: {
        goals: [
          {
            id: 1,
            prompt: 'Mediterranean cutting protocol',
            city: 'Prague',
            num_days: 7,
            status: 'completed',
            created_at: new Date().toISOString(),
          },
          {
            id: 2,
            prompt: 'High protein bulk',
            city: 'Brno',
            num_days: 14,
            status: 'processing_meal_plan',
            created_at: new Date().toISOString(),
          },
        ],
      },
    });

    test('lists existing goals as clickable cards', async ({ authedPage: page }) => {
      await page.goto('/');

      await expect(page.getByText(/Mediterranean cutting protocol/i)).toBeVisible();
      await expect(page.getByText(/High protein bulk/i)).toBeVisible();
      // Status badges
      await expect(page.getByText(/completed/i).first()).toBeVisible();
      // ID format: #1
      await expect(page.getByText(/#1/)).toBeVisible();
    });

    test('clicking a goal card navigates to /plan/:id', async ({ authedPage: page }) => {
      await page.goto('/');
      await page.getByText(/Mediterranean cutting protocol/i).click();
      await expect(page).toHaveURL(/\/plan\/1$/);
    });

    test('"New Plan" button navigates to /create', async ({ authedPage: page }) => {
      await page.goto('/');
      await page.getByRole('button', { name: /new plan/i }).click();
      await expect(page).toHaveURL(/\/create$/);
    });
  });
});
