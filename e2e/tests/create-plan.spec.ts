import { test, expect } from '../fixtures/auth';

/**
 * Create-plan form tests.
 *
 * The form is a 2-step wizard:
 *   Step 1 ("Cíle"):  prompt textarea, country, city — gated "Další krok" button.
 *   Step 2 ("Jídla"): per-slot count steppers (five slots), presets
 *                     (Pracovní týden / Víkend), "Vygenerovat plán" submit.
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
    await expect(page.getByRole('button', { name: 'Pracovní týden' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Víkend' })).toBeVisible();
    await expect(page.locator('#count-breakfasts')).toBeVisible();
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

  test('stepper increments and decrements a slot count', async ({ authedPage: page }) => {
    await page.goto('/create');
    await goToStepTwo(page);

    const breakfasts = page.locator('#count-breakfasts');
    await expect(breakfasts).toHaveValue('5');
    await page.getByRole('button', { name: 'Více: Snídaně' }).click();
    await expect(breakfasts).toHaveValue('6');
    await page.getByRole('button', { name: 'Méně: Snídaně' }).click();
    await expect(breakfasts).toHaveValue('5');
  });

  test('weekend preset fills the counts', async ({ authedPage: page }) => {
    await page.goto('/create');
    await goToStepTwo(page);

    await page.getByRole('button', { name: 'Víkend' }).click();
    await expect(page.locator('#count-breakfasts')).toHaveValue('2');
    await expect(page.locator('#count-lunches')).toHaveValue('2');
    await expect(page.locator('#count-dinners')).toHaveValue('2');
    await expect(page.locator('#count-small_meals')).toHaveValue('0');
    await expect(page.locator('#count-snacks')).toHaveValue('2');
  });

  test('zero total meals blocks submit', async ({ authedPage: page }) => {
    await page.goto('/create');
    await goToStepTwo(page);

    for (const f of ['breakfasts', 'lunches', 'dinners', 'small_meals', 'snacks']) {
      await page.locator(`#count-${f}`).fill('0');
    }
    await expect(page.getByRole('alert').filter({ hasText: 'Vyberte alespoň jedno jídlo.' })).toBeVisible();
    await expect(page.getByRole('button', { name: /vygenerovat plán/i })).toBeDisabled();
  });

  test('happy path: submit form -> redirect to /plan/:id -> shows completed plan', async ({
    authedPage: page,
  }) => {
    await page.goto('/create');

    await fillStepOne(page, 'E2E test plan prompt', 'Praha');
    await page.getByRole('button', { name: /další krok/i }).click();

    const postReq = page.waitForRequest(
      (r) => r.method() === 'POST' && /\/api\/goals\/$/.test(r.url()),
    );
    await page.getByRole('button', { name: /vygenerovat plán/i }).click();
    const body = (await postReq).postDataJSON();
    expect(body).toMatchObject({ breakfasts: 5, lunches: 5, dinners: 5, small_meals: 5, snacks: 0 });
    expect(body).not.toHaveProperty('num_days');

    // Mock returns goal_id=42 -> navigation
    await expect(page).toHaveURL(/\/plan\/42$/);

    // PlanView polls task-status; mocks march to 'completed'. "Váš plán." heading
    // appears once status === 'completed'.
    await expect(page.getByText(/váš plán/i).first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(/Mocked Oats/i)).toBeVisible();
    await expect(page.getByText(/Mocked Chicken Bowl/i)).toBeVisible();
  });
});
