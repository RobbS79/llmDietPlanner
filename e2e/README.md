# LLM Diet Planner — Playwright e2e suite

End-to-end QA suite for the React frontend and the Django REST API.
Lives outside `frontend/` so it doesn't touch the app's `npm run build`
or `npm run lint` pipeline.

## Install (first run only)

```bash
cd e2e
npm install
# Downloads Chromium + system deps. Skip --with-deps if you already have them.
npx playwright install --with-deps chromium
# Optional, only if you want to use the firefox/webkit projects:
# npx playwright install firefox webkit
```

## Running

By default the tests expect the dev servers to already be running:

* Vite dev server  — `http://localhost:5173` (from `frontend/`: `npm run dev`)
* Django dev server — `http://localhost:8000` (from repo root: `python manage.py runserver`)

Then:

```bash
# Headless run, all tests
npm run test:e2e

# Playwright UI mode (best DX)
npm run test:e2e:ui

# Headed (watch the browser)
npm run test:e2e:headed

# Open the HTML report from the last run
npm run test:e2e:report
```

### Letting Playwright start the servers for you

Set `E2E_AUTO_START_SERVERS=1` and Playwright will boot Django + Vite via
its `webServer` blocks. It assumes `python` and `npm` are on PATH and the
Django app can serve `/health/` within 60s.

```bash
E2E_AUTO_START_SERVERS=1 npm run test:e2e
```

## Environment variables

| Variable | Default | What it does |
| --- | --- | --- |
| `E2E_BASE_URL` | `http://localhost:5173` | URL the browser tests run against. |
| `E2E_API_URL` | `http://localhost:8000` | Django backend URL for API tests. |
| `E2E_AUTO_START_SERVERS` | _unset_ | Set to `1` to auto-start Django + Vite. |
| `E2E_TEST_USERNAME` | _unset_ | Optional pre-provisioned test user for live auth tests. |
| `E2E_TEST_PASSWORD` | _unset_ | Password for the above user. |
| `E2E_TEST_EMAIL` | _unset_ | Email for the above user (unused today, reserved). |
| `E2E_RUN_REAL_LLM` | _unset_ | Set to `1` to run tests that would hit OpenAI. **Costs money.** |
| `CI` | _unset_ | Standard. Enables retries, disables `.only`. |

## What's covered

| File | What it tests |
| --- | --- |
| `tests/smoke.spec.ts` | App boots, login page renders, route guards, OAuth trigger fires. |
| `tests/auth.spec.ts` | `/login-success` token persistence, logout clears tokens. |
| `tests/dashboard.spec.ts` | Empty Vault, populated goal cards, navigation to `/create` and `/plan/:id`. |
| `tests/create-plan.spec.ts` | Form rendering, validation, meal toggles, duration buttons, submit happy-path. |
| `tests/plan-view.spec.ts` | Completed plan rendering, failed-plan error UI, pending status tracker. |
| `tests/errors.spec.ts` | Network failure handling, 401 → /login bounce, unknown-route catch-all. |
| `tests/api.spec.ts` | Live Django: `/health/`, `/api/shops/`, auth 401/403 boundaries, login, optional authed flow. |

## What's mocked vs. real

* **Browser tests** (`smoke`, `auth`, `dashboard`, `create-plan`, `plan-view`,
  `errors`) intercept all `/api/...` calls via `page.route()` and serve
  deterministic fixtures from `helpers/mocks.ts`. They do **not** hit the
  Django backend, so they run without OpenAI, Celery, or Redis.
* **API tests** (`api.spec.ts`) hit the real Django backend at `E2E_API_URL`.
  Only the unauthenticated/boundary tests run by default; the authenticated
  flow requires `E2E_TEST_USERNAME` + `E2E_TEST_PASSWORD`.

## Known gaps

* **Full Google OAuth callback** can't be exercised headlessly without a
  mock Google IDP. `auth.spec.ts` contains a `test.fixme` placeholder with
  a note. To close this, run a stub OAuth server and point
  `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` at it during the test run.
* **LLM-generated content** is never exercised in this suite. The
  create-plan happy path mocks `/api/goals/:id/task-status/` to march
  straight to `completed` and serves a fixture plan. Set `E2E_RUN_REAL_LLM=1`
  later if you wire up a long-running test that lets Celery do real work.
* **Test user seeding** is not automated. If you want to run the authed
  API tests, create a user manually:

  ```bash
  python manage.py shell -c "
  from django.contrib.auth.models import User
  u = User.objects.create_user('e2e_test', email='e2e@example.com', password='e2e_pass_123!')
  u.is_active = True
  u.save()
  "
  export E2E_TEST_USERNAME=e2e_test
  export E2E_TEST_PASSWORD=e2e_pass_123!
  ```

  A future improvement would be a Django management command (`python
  manage.py seed_e2e_user`) that the suite's global-setup invokes.

## Updating snapshots

This suite doesn't use visual snapshots today. If you add `toMatchSnapshot`
calls later, update them with:

```bash
npm run test:e2e -- --update-snapshots
```

## Useful Playwright invocations

```bash
# Single file
npx playwright test tests/smoke.spec.ts

# Single test by name
npx playwright test -g "happy path"

# Just one browser project
npx playwright test --project=chromium
```
