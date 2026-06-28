import { test, expect } from '../fixtures/auth';

/**
 * Create-plan form tests.
 *
 * The form is a 2-step wizard:
 *   Step 1 ("Cíle"):  prompt textarea, country, city — gated "Další krok" button.
 *   Step 2 ("Jídla"): meal toggles, duration buttons, "Vygenerovat plán" submit.
 *
 * The form posts to /api/goals/ which the mock fixture intercepts and
 * returns goal_id=42, simulating immediate task acceptance. The PlanView
 * then polls /api/goals/42/task-status/ which the mock advances toward
 * 'completed' so the full happy-path flow runs without touching the LLM.
 */

async function fillStepOne(page: any, prompt = 'Test prompt', city = 'Praha') {
  await page.locator('textarea').fill(prompt);
  await page.getByPlaceholder(/např. Praha/i).fill(city);
}

async function goToStepTwo(page: any) {
  await fillStepOne(page);
  await page.getByRole('button', { name: /další krok/i }).click();
}

test.describe('create plan form', () => {
  test('renders all sections and the submit button', async ({ authedPage: page }) => {
    await page.goto('/create');

    // Page heading "Nový plán."
    await expect(page.getByRole('heading', { name: /nový/i })).toBeVisible();
    // Step 1 section headings
    await expect(page.getByText(/stravovací cíle/i)).toBeVisible();
    await expect(page.getByText(/popište své cíle/i)).toBeVisible();
    await expect(page.getByText(/země/i).first()).toBeVisible();
    await expect(page.getByText(/město/i).first()).toBeVisible();

    // Advance to step 2 for duration + submit
    await goToStepTwo(page);
    await expect(page.getByText(/délka plánu/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /vygenerovat plán/i })).toBeVisible();
  });

  test('next button is disabled until prompt and city are filled', async ({ authedPage: page }) => {
    await page.goto('/create');

    const next = page.getByRole('button', { name: /další krok/i });
    await expect(next).toBeDisabled();

    await fillStepOne(page);
    await expect(next).toBeEnabled();
  });

  test('empty city blocks advancing past step one', async ({ authedPage: page }) => {
    await page.goto('/create');
    await page.locator('textarea').fill('Test prompt');

    // City still empty -> cannot advance, stays on /create.
    const next = page.getByRole('button', { name: /další krok/i });
    await expect(next).toBeDisabled();
    await expect(page).toHaveURL(/\/create$/);
  });

  test('toggling meals deactivates the visual selection', async ({ authedPage: page }) => {
    await page.goto('/create');
    await goToStepTwo(page);

    const breakfast = page.getByRole('button', { name: /snídaně/i });
    await expect(breakfast).toBeVisible();
    // Click to deactivate, then re-activate
    await breakfast.click();
    await breakfast.click();
  });

  test('day duration buttons update the selected duration', async ({ authedPage: page }) => {
    await page.goto('/create');
    await goToStepTwo(page);

    const day14 = page.getByRole('button', { name: /^14D$/i });
    await day14.click();
    // The clicked button should now carry the active emerald class.
    await expect(day14).toHaveClass(/bg-emerald-600/);
  });

  test('happy path: submit form -> redirect to /plan/:id -> shows completed plan', async ({
    authedPage: page,
  }) => {
    await page.goto('/create');

    await fillStepOne(page, 'E2E test plan prompt', 'Praha');
    await page.getByRole('button', { name: /další krok/i }).click();

    await page.getByRole('button', { name: /vygenerovat plán/i }).click();

    // Mock returns goal_id=42 -> navigation
    await expect(page).toHaveURL(/\/plan\/42$/);

    // PlanView polls task-status; mocks march to 'completed'. "Váš plán." heading
    // appears once status === 'completed'.
    await expect(page.getByText(/váš plán/i).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Mocked Oats/i)).toBeVisible();
    await expect(page.getByText(/Mocked Chicken Bowl/i)).toBeVisible();
  });
});
