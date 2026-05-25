import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for the LLM Diet Planner e2e suite.
 *
 * Environment variables:
 *   E2E_BASE_URL          - URL the browser tests run against (default http://localhost:5173)
 *   E2E_API_URL           - Django backend URL used for API/request tests (default http://localhost:8000)
 *   E2E_AUTO_START_SERVERS - "1" to let Playwright start `npm run dev` + Django (default off,
 *                            since most devs already have those running). See README.
 *   CI                    - standard CI flag, enables retries and disables headed.
 */

const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173';
const apiURL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8000';
const autoStart = process.env.E2E_AUTO_START_SERVERS === '1';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],

  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL,
    navigationTimeout: 30_000,
    trace: process.env.CI ? 'retain-on-failure' : 'off',
    screenshot: 'only-on-failure',
    video: process.env.CI ? 'retain-on-failure' : 'off',
  },

  // Chromium is the only project enabled by default to keep CI install size small.
  // Firefox and WebKit are configured but require `npx playwright install firefox webkit`.
  // Run them explicitly with `npx playwright test --project=firefox` etc.
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
      testIgnore: process.env.E2E_ENABLE_FIREFOX === '1' ? undefined : /.*/,
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
      testIgnore: process.env.E2E_ENABLE_WEBKIT === '1' ? undefined : /.*/,
    },
  ],

  // Auto-start servers only if explicitly requested. By default we assume the
  // dev is already running `npm run dev` and `python manage.py runserver`.
  webServer: autoStart
    ? [
        {
          command: 'python manage.py runserver 0.0.0.0:8000',
          cwd: '..',
          url: `${apiURL}/health/`,
          reuseExistingServer: true,
          timeout: 60_000,
          stdout: 'pipe',
          stderr: 'pipe',
        },
        {
          command: 'npm run dev -- --host 0.0.0.0 --port 5173',
          cwd: '../frontend',
          url: baseURL,
          reuseExistingServer: true,
          timeout: 60_000,
          stdout: 'pipe',
          stderr: 'pipe',
        },
      ]
    : undefined,
});

export { apiURL, baseURL };
