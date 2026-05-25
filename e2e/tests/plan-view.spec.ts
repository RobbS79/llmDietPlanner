import { test, expect } from '../fixtures/auth';

/**
 * /plan/:id rendering — loading, failed, and completed states.
 */

test.describe('plan view', () => {
  test.describe('completed plan renders meals, shopping list, and total', () => {
    test.use({
      mockOptions: {
        statusSequence: [{ goal_status: 'completed' }],
      },
    });

    test('renders the full plan immediately when status starts at completed', async ({
      authedPage: page,
    }) => {
      await page.goto('/plan/42');
      // "Your Plan." heading
      await expect(page.getByText(/your plan/i).first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(/Mocked Oats/i)).toBeVisible();
      // Shopping list sidebar
      await expect(page.getByText(/shopping list/i).first()).toBeVisible();
      // Total price from mock
      await expect(page.getByText(/1234/)).toBeVisible();
    });

    test('meal cards are clickable and navigate to recipe detail', async ({
      authedPage: page,
    }) => {
      await page.goto('/plan/42');
      await expect(page.getByText(/Mocked Oats/i)).toBeVisible({ timeout: 30_000 });

      // Click on the Mocked Oats meal card
      await page.getByText(/Mocked Oats/i).click();

      // Should navigate to recipe page
      await expect(page).toHaveURL(/\/plan\/42\/recipe\/42:1:breakfast:0$/);
    });

    test('"View Full List" button navigates to shopping list page', async ({
      authedPage: page,
    }) => {
      await page.goto('/plan/42');
      await expect(page.getByText(/your plan/i).first()).toBeVisible({ timeout: 30_000 });

      const listBtn = page.getByRole('button', { name: /view full list/i });
      await expect(listBtn).toBeVisible();
      await listBtn.click();

      await expect(page).toHaveURL(/\/plan\/42\/shopping-list$/);
    });
  });

  test.describe('failed plan shows error UI', () => {
    test.use({
      mockOptions: {
        statusSequence: [{ goal_status: 'failed' }],
      },
    });

    test('renders the error screen with a "Back to Plans" button', async ({
      authedPage: page,
    }) => {
      await page.goto('/plan/42');
      await expect(page.getByRole('heading', { name: /generation failed/i })).toBeVisible({
        timeout: 10_000,
      });
      const back = page.getByRole('button', { name: /back to plans/i });
      await expect(back).toBeVisible();
      await back.click();
      await expect(page).toHaveURL(/\/$/);
    });
  });

  test.describe('pending plan shows loading screen', () => {
    test.use({
      mockOptions: {
        // Stays pending forever
        statusSequence: [{ goal_status: 'pending' }],
      },
    });

    test('shows the Generating screen and the status tracker', async ({
      authedPage: page,
    }) => {
      await page.goto('/plan/42');
      await expect(page.getByRole('heading', { name: /generating/i })).toBeVisible();
      // StatusTracker shows "Starting" for pending status
      await expect(page.getByText(/starting/i)).toBeVisible();
    });
  });
});
