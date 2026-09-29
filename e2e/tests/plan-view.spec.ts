import { test, expect } from '../fixtures/auth';
import { legacyGoalDetail } from '../helpers/mocks';

/**
 * /plan/:id rendering — loading, failed, and completed states.
 */

test.describe('plan view', () => {
  test.describe('completed plan renders meals', () => {
    test.use({
      mockOptions: {
        statusSequence: [{ goal_status: 'completed' }],
      },
    });

    test('renders the full plan immediately when status starts at completed', async ({
      authedPage: page,
    }) => {
      await page.goto('/plan/42');
      // "Váš plán." heading
      await expect(page.getByText(/váš plán/i).first()).toBeVisible({ timeout: 30_000 });
      await expect(page.getByText(/Mocked Oats/i)).toBeVisible();
      await expect(page.getByText(/Mocked Chicken Bowl/i)).toBeVisible();
    });

    test('meal cards are clickable and navigate to recipe detail', async ({
      authedPage: page,
    }) => {
      await page.goto('/plan/42');
      await expect(page.getByText(/Mocked Oats/i)).toBeVisible({ timeout: 30_000 });

      // Click on the Mocked Oats meal card
      await page.getByText(/Mocked Oats/i).click();

      // Should navigate to recipe page
      await expect(page).toHaveURL(/\/plan\/42\/recipe\/42:breakfast:0$/);
    });

    test('pool plan renders slot sections, not day cards', async ({ authedPage: page }) => {
      await page.goto('/plan/42');
      await expect(page.getByText(/Mocked Salmon/i)).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('#slot-dinner')).toBeVisible();
      await expect(page.locator('#slot-dinner').getByRole('heading', { name: 'Večeře · 1' })).toBeVisible();
      await expect(page.locator('#den-1')).toHaveCount(0);
    });

    test('dinner card links to its pool meal id', async ({ authedPage: page }) => {
      await page.goto('/plan/42');
      await expect(page.getByText(/Mocked Salmon/i)).toBeVisible({ timeout: 30_000 });
      await page.getByText(/Mocked Salmon/i).click();
      await expect(page).toHaveURL(/\/plan\/42\/recipe\/42:dinner:0$/);
    });

  });

  test.describe('legacy day plan still renders', () => {
    test.use({
      mockOptions: {
        statusSequence: [{ goal_status: 'completed' }],
        goalDetail: legacyGoalDetail,
      },
    });

    test('renders #den-1 with "Den 1"', async ({ authedPage: page }) => {
      await page.goto('/plan/42');
      await expect(page.getByText(/Mocked Oats/i)).toBeVisible({ timeout: 30_000 });
      await expect(page.locator('#den-1')).toBeVisible();
      await expect(page.getByText('Den 1').first()).toBeVisible();
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
      await expect(page.getByRole('heading', { name: /generování selhalo/i })).toBeVisible({
        timeout: 10_000,
      });
      const back = page.getByRole('button', { name: /zpět na plány/i });
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
      await expect(page.getByRole('heading', { name: /generujeme/i })).toBeVisible();
      // StatusTracker shows "Analyzujeme vaše preference" for pending status
      await expect(page.getByText(/analyzujeme/i).first()).toBeVisible();
    });
  });
});
