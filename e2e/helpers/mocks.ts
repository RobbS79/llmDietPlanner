import type { Page, Route } from '@playwright/test';

/**
 * Network-layer mocks for the React app. We mock the `/api/...` calls
 * so LLM-backed flows are deterministic and don't burn API credits.
 *
 * The frontend calls these endpoints (see frontend/src/App.tsx):
 *   GET  /api/goals/list/
 *   GET  /api/shops/?country=CZ
 *   POST /api/goals/
 *   GET  /api/goals/:id/task-status/
 *   GET  /api/goals/:id/
 *   GET  /api/recipes/:mealId/
 *   POST /api/auth/refresh/
 */

export interface MockOptions {
  /** Goals returned by /api/goals/list/. Default = []. */
  goals?: any[];
  /** Shops returned by /api/shops/?country=...   Default = ROHLIK + KOSIK. */
  shops?: Array<{ code: string; name: string }>;
  /**
   * Status sequence emitted by /api/goals/:id/task-status/. Each call to the
   * endpoint advances one step (then sticks on the last entry). Default ends
   * with 'completed' so PlanView can render.
   */
  statusSequence?: Array<{ goal_status: string }>;
  /** Full plan returned by /api/goals/:id/ once completed. */
  goalDetail?: any;
  /** Goal id returned from POST /api/goals/. Default 42. */
  createdGoalId?: number;
  /** Recipe returned by /api/recipes/:mealId/. Default = mock recipe for Mocked Oats. */
  recipe?: any;
  /**
   * Profile returned by /api/auth/profile/ (HomeRoute onboarding gate +
   * Dashboard entitlement). Default = onboarding complete with free generations.
   */
  profile?: any;
  /** Meal instances returned by /api/goals/:id/meal-instances/. Default = []. */
  mealInstances?: any[];
}

const defaultShops = [
  { code: 'ROHLIK', name: 'Rohlik' },
  { code: 'KOSIK', name: 'Kosik' },
];

const defaultStatusSequence = [
  { goal_status: 'pending' },
  { goal_status: 'processing_meal_plan' },
  { goal_status: 'processing_shopping_list' },
  { goal_status: 'completed' },
];

const defaultGoalDetail = {
  id: 42,
  prompt: 'Mocked metabolic protocol',
  city: 'Prague',
  num_days: 3,
  language_code: 'cs',
  status: 'completed',
  dietary_plan: {
    total_price: 1234,
    currency: 'CZK',
    days: [
      {
        day_number: 1,
        breakfast: {
          name: 'Mocked Oats',
          description: 'A satiating bowl of oats',
          preparation_time: 10,
          nutritional_info: { kcal: '450', protein: '20g', carbs: '60g', fat: '12g' },
          meal_identifier: '42:1:breakfast:0',
          ingredients: [
            { name: 'Oats', quantity: '100', unit: 'g' },
            { name: 'Milk', quantity: '200', unit: 'ml' },
            { name: 'Honey', quantity: '1', unit: 'tbsp' },
          ],
        },
        lunch: {
          name: 'Mocked Chicken Bowl',
          description: 'Protein-forward lunch',
          preparation_time: 25,
          nutritional_info: { kcal: '650', protein: '45g', carbs: '55g', fat: '18g' },
          meal_identifier: '42:1:lunch:0',
          ingredients: [
            { name: 'Chicken breast', quantity: '200', unit: 'g' },
            { name: 'Rice', quantity: '150', unit: 'g' },
          ],
        },
        dinner: {
          name: 'Mocked Salmon',
          description: 'Omega-rich dinner',
          preparation_time: 20,
          nutritional_info: { kcal: '700', protein: '50g', carbs: '30g', fat: '30g' },
          meal_identifier: '42:1:dinner:0',
          ingredients: [
            { name: 'Salmon fillet', quantity: '250', unit: 'g' },
            { name: 'Asparagus', quantity: '200', unit: 'g' },
          ],
        },
      },
    ],
    shopping_list: [
      {
        ingredient: 'Oats',
        quantity: '500',
        unit: 'g',
        price: 49,
        currency: 'CZK',
        matched_product_name: 'Oats Rolled 500g',
      },
      {
        ingredient: 'Chicken breast',
        quantity: '600',
        unit: 'g',
        price: 199,
        currency: 'CZK',
        matched_product_name: 'Chicken breast fillet',
      },
      {
        ingredient: 'Salmon fillet',
        quantity: '250',
        unit: 'g',
        price: 289,
        currency: 'CZK',
        matched_product_name: 'Atlantic Salmon 250g',
      },
    ],
  },
};

const defaultRecipe = {
  id: 1,
  meal_identifier: '42:1:breakfast:0',
  dietary_goal_id: 42,
  name: 'Mocked Oats',
  description: 'A satiating bowl of oats',
  instructions: [
    'Bring milk to a simmer in a small saucepan.',
    'Add oats and stir continuously for 5 minutes.',
    'Remove from heat and drizzle with honey.',
    'Serve warm and enjoy.',
  ],
  ingredients: [
    { name: 'Oats', quantity: '100', unit: 'g' },
    { name: 'Milk', quantity: '200', unit: 'ml' },
    { name: 'Honey', quantity: '1', unit: 'tbsp' },
  ],
  preparation_time: 10,
  cooking_time: 5,
  servings: 1,
  nutritional_info: { kcal: '450', protein: '20g', carbs: '60g', fat: '12g' },
};

export async function mockApi(page: Page, opts: MockOptions = {}): Promise<void> {
  const goals = opts.goals ?? [];
  const shops = opts.shops ?? defaultShops;
  const statusSequence = opts.statusSequence ?? defaultStatusSequence;
  const goalDetail = opts.goalDetail ?? defaultGoalDetail;
  const createdGoalId = opts.createdGoalId ?? 42;
  const recipe = opts.recipe ?? defaultRecipe;
  const profile = opts.profile ?? { onboarding_completed: true, free_generations_remaining: 3, email: 'e2e@example.com' };
  const mealInstances = opts.mealInstances ?? [];

  // Shared mutable index for the status sequence
  let statusIdx = 0;

  await page.route('**/api/goals/list/', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: goals, error: null }),
    });
  });

  await page.route('**/api/shops/**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        data: { country: 'CZ', shops },
        error: null,
      }),
    });
  });

  await page.route('**/api/goals/', async (route: Route) => {
    if (route.request().method() !== 'POST') return route.continue();
    await route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        data: { goal_id: createdGoalId, status: 'pending' },
        error: null,
      }),
    });
  });

  await page.route(/.*\/api\/goals\/\d+\/task-status\/$/, async (route: Route) => {
    const next = statusSequence[Math.min(statusIdx, statusSequence.length - 1)];
    statusIdx += 1;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: next, error: null }),
    });
  });

  await page.route(/.*\/api\/goals\/\d+\/$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: goalDetail, error: null }),
    });
  });

  // Recipe detail endpoint
  await page.route(/.*\/api\/recipes\/.*/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: recipe, error: null }),
    });
  });

  // Profile — HomeRoute's onboarding gate + Dashboard entitlement banner.
  await page.route('**/api/auth/profile/', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: profile, error: null }),
    });
  });

  // Per-meal cooked state for PlanView.
  await page.route(/.*\/api\/goals\/\d+\/meal-instances\/$/, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: mealInstances, error: null }),
    });
  });

  // Auth refresh — keep silent; just 401 so the app falls back to login if invoked.
  await page.route('**/api/auth/refresh/', async (route: Route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'mock-refresh-disabled' }),
    });
  });
}

/**
 * Mock just enough to short-circuit the Google OAuth redirect so it doesn't
 * leave localhost. We catch the navigation to /api/auth/google/login/ and
 * return a small HTML stub instead of a real 302 to accounts.google.com.
 */
export async function stubGoogleOAuthRedirect(page: Page): Promise<void> {
  await page.route('**/api/auth/google/login/', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body><h1 id="oauth-stub">Mocked Google OAuth screen</h1></body></html>',
    });
  });
}
