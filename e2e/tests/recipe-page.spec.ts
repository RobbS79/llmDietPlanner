import { test, expect } from '../fixtures/auth';

/**
 * Recipe detail page — navigated from a meal card in the plan view.
 * Tests rendering of ingredients, instructions, and nutritional info.
 */

test.describe('recipe page', () => {
  test.use({
    mockOptions: {
      statusSequence: [{ goal_status: 'completed' }],
    },
  });

  test('renders recipe with ingredients and step-by-step instructions', async ({
    authedPage: page,
  }) => {
    await page.goto('/plan/42/recipe/42:1:breakfast:0');

    // Recipe heading
    await expect(page.getByRole('heading', { name: /mocked oats/i })).toBeVisible({
      timeout: 10_000,
    });

    // Description
    await expect(page.getByText(/satiating bowl of oats/i)).toBeVisible();

    // Ingredients section
    await expect(page.getByText(/ingredients/i).first()).toBeVisible();
    await expect(page.getByText(/oats/i).first()).toBeVisible();
    await expect(page.getByText(/milk/i).first()).toBeVisible();
    await expect(page.getByText(/honey/i).first()).toBeVisible();

    // Instructions section
    await expect(page.getByText(/instructions/i)).toBeVisible();
    await expect(page.getByText(/bring milk to a simmer/i)).toBeVisible();
    await expect(page.getByText(/add oats and stir/i)).toBeVisible();
    await expect(page.getByText(/drizzle with honey/i)).toBeVisible();
    await expect(page.getByText(/serve warm/i)).toBeVisible();

    // Nutritional info
    await expect(page.getByText(/nutrition facts/i)).toBeVisible();
    await expect(page.getByText(/450/)).toBeVisible();
  });

  test('shows prep time and cook time badges', async ({ authedPage: page }) => {
    await page.goto('/plan/42/recipe/42:1:breakfast:0');

    await expect(page.getByRole('heading', { name: /mocked oats/i })).toBeVisible({
      timeout: 10_000,
    });

    // Prep time: 10 min
    await expect(page.getByText(/10 min prep/i)).toBeVisible();
    // Cook time: 5 min
    await expect(page.getByText(/5 min cook/i)).toBeVisible();
    // Servings: 1
    await expect(page.getByText(/1 serving/i)).toBeVisible();
  });

  test('"Back to Plan" button navigates back to plan view', async ({ authedPage: page }) => {
    await page.goto('/plan/42/recipe/42:1:breakfast:0');

    await expect(page.getByRole('heading', { name: /mocked oats/i })).toBeVisible({
      timeout: 10_000,
    });

    await page.getByText(/back to plan/i).click();
    await expect(page).toHaveURL(/\/plan\/42$/);
  });

  test('full flow: plan view -> click meal -> recipe page -> back to plan', async ({
    authedPage: page,
  }) => {
    // Start at the plan view
    await page.goto('/plan/42');
    await expect(page.getByText(/your plan/i).first()).toBeVisible({ timeout: 30_000 });

    // Click on Mocked Oats meal card
    await page.getByText(/Mocked Oats/i).click();
    await expect(page).toHaveURL(/\/plan\/42\/recipe\/42:1:breakfast:0$/);

    // Verify recipe loaded
    await expect(page.getByRole('heading', { name: /mocked oats/i })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/bring milk to a simmer/i)).toBeVisible();

    // Navigate back
    await page.getByText(/back to plan/i).click();
    await expect(page).toHaveURL(/\/plan\/42$/);
    await expect(page.getByText(/Mocked Oats/i)).toBeVisible();
  });
});
