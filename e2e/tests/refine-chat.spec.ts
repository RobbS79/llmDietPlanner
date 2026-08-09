import { test, expect } from '../fixtures/auth';
import type { Page, Route } from '@playwright/test';

/**
 * Refine chat: the way out of a meal you don't like.
 *
 * Covers the entry point (invite card + intent chips + plan deep link), the
 * 1–3 candidate choice, the web-research waiting state, and undo. The refine
 * endpoints are mocked here — routes registered after the fixture's broad
 * `/api/recipes/.*` handler take precedence, so these win.
 */

const MEAL_ID = '42:1:breakfast:0';
const RECIPE_URL = `/plan/42/recipe/${MEAL_ID}`;

const candidate = (id: number, name: string, why: string | null = null) => ({
  curated_recipe_id: id,
  name,
  description: '',
  food_category: 'breakfast',
  preparation_time: 15,
  calories: 420,
  why,
});

/** The consent banner is fixed to the bottom and swallows clicks aimed at
 * anything underneath it. Decide it up front so it never renders. */
async function settleConsent(page: Page) {
  // Shape must match analytics.setConsent — a bare string parses to null and
  // the banner shows anyway.
  await page.addInitScript(() => window.localStorage.setItem(
    'mkt_consent_v1', JSON.stringify({ consent: false, version: 1, ts: 0 }),
  ));
}

/** Mock POST refine (preview + accept) and GET research status. */
async function mockRefine(page: Page, opts: {
  preview?: Record<string, unknown>;
  /** Successive research-status payloads; the last one sticks. */
  research?: Array<Record<string, unknown>>;
  accept?: Record<string, unknown>;
  onAccept?: (body: Record<string, unknown>) => void;
} = {}) {
  let researchIdx = 0;

  await page.route(/.*\/api\/recipes\/research\/\d+\/$/, async (route: Route) => {
    const seq = opts.research ?? [];
    const payload = seq[Math.min(researchIdx, seq.length - 1)] ?? { status: 'searching', reply_text: null, candidate: null };
    researchIdx += 1;
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ status: 'success', data: payload }),
    });
  });

  await page.route(/.*\/api\/recipes\/.*\/refine\/$/, async (route: Route) => {
    const body = route.request().postDataJSON() ?? {};
    if (body.accept !== undefined) {
      opts.onAccept?.(body);
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          data: opts.accept ?? {
            replaced: true,
            recipe: { meal_identifier: MEAL_ID, name: 'Kuřecí salát', description: '',
                      ingredients: [], instructions: ['Smíchej.'], servings: 1,
                      nutritional_info: {} },
            previous: { curated_recipe_id: 3, name: 'Mocked Oats' },
          },
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({
        status: 'success',
        data: opts.preview ?? {
          reply_text: 'Co třeba Kuřecí salát?',
          candidate: candidate(7, 'Kuřecí salát', 'Rychlé a lehké'),
          alternatives: [],
          research_job_id: null, question: null, hint_matched: null,
        },
      }),
    });
  });
}

test.describe('refine chat entry point', () => {
  test('the recipe page invites a conversation instead of showing a bare swap button', async ({
    authedPage: page,
  }) => {
    await settleConsent(page);
    await mockRefine(page);
    await page.goto(RECIPE_URL);

    await expect(page.getByRole('heading', { name: /Nesedí vám tohle jídlo\?/ })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/Napište naší kuchařce/)).toBeVisible();
    await expect(page.getByRole('button', { name: /Poradit se s kuchařkou/ })).toBeVisible();
    // The old mechanical label is gone.
    await expect(page.getByRole('button', { name: 'Vyměnit recept' })).toHaveCount(0);
  });

  test('an intent chip opens the chat and sends itself as the first message', async ({
    authedPage: page,
  }) => {
    const sent: string[] = [];
    await settleConsent(page);
    await page.route(/.*\/api\/recipes\/.*\/refine\/$/, async (route: Route) => {
      const body = route.request().postDataJSON() ?? {};
      (body.messages ?? []).forEach((m: { text: string }) => sent.push(m.text));
      await route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          status: 'success',
          data: { reply_text: 'Jasně, něco rychlého.',
                  candidate: candidate(7, 'Kuřecí salát'), alternatives: [],
                  research_job_id: null, question: null, hint_matched: null },
        }),
      });
    });
    await page.goto(RECIPE_URL);

    await page.getByRole('button', { name: 'Chci něco rychlejšího' }).click();

    await expect(page.getByText('Jasně, něco rychlého.')).toBeVisible({ timeout: 15_000 });
    expect(sent).toEqual(['Chci něco rychlejšího']);
  });

  test('the plan meal card deep-links straight into the chat', async ({ authedPage: page }) => {
    await settleConsent(page);
    await mockRefine(page);
    await page.goto('/plan/42');

    const nesedi = page.getByRole('button', { name: /Nesedí vám tohle jídlo\? Otevřít chat/ }).first();
    await expect(nesedi).toBeVisible({ timeout: 15_000 });
    await nesedi.click();

    await expect(page).toHaveURL(/\?chat=1$/);
    // Arrives with the conversation already open, no second click needed.
    await expect(page.getByPlaceholder('Napište, na co máte chuť…')).toBeVisible({
      timeout: 15_000,
    });
  });
});

test.describe('choosing between alternatives', () => {
  test('offers three cards and commits the one the user picks', async ({ authedPage: page }) => {
    let accepted: number | null = null;
    await settleConsent(page);
    await mockRefine(page, {
      preview: {
        reply_text: 'Co třeba Kuřecí salát?',
        candidate: candidate(7, 'Kuřecí salát'),
        alternatives: [candidate(8, 'Těstoviny s pestem'), candidate(9, 'Zeleninové rizoto')],
        research_job_id: null, question: null, hint_matched: null,
      },
      onAccept: (body) => { accepted = body.accept as number; },
    });
    await page.goto(RECIPE_URL);
    await page.getByRole('button', { name: /Poradit se s kuchařkou/ }).click();
    await page.getByPlaceholder('Napište, na co máte chuť…').fill('něco lehčího');
    await page.getByRole('button', { name: 'Odeslat' }).click();

    const choice = page.getByRole('region', { name: 'Vyberte, co vám sedí nejvíc' });
    await expect(choice).toBeVisible({ timeout: 15_000 });
    // Scope to the card group: the assistant bubble also names the first dish.
    await expect(choice.getByRole('article')).toHaveCount(3);
    await expect(choice.getByText('Kuřecí salát')).toBeVisible();
    await expect(choice.getByText('Těstoviny s pestem')).toBeVisible();
    await expect(choice.getByText('Zeleninové rizoto')).toBeVisible();

    await page.getByRole('button', { name: 'Použít recept Zeleninové rizoto' }).click();

    await expect.poll(() => accepted).toBe(9);
  });
});

test.describe('web research waiting state', () => {
  test('shows the real stage the backend reports, then the found recipe', async ({
    authedPage: page,
  }) => {
    await settleConsent(page);
    await mockRefine(page, {
      preview: {
        reply_text: 'Podívám se na web.', candidate: null, alternatives: [],
        research_job_id: 44, question: null, hint_matched: null,
      },
      research: [
        { status: 'searching', reply_text: null, candidate: null },
        { status: 'curating', reply_text: null, candidate: null },
        { status: 'ready', reply_text: 'Našla jsem: Pravý ramen.',
          candidate: candidate(11, 'Pravý ramen') },
      ],
    });
    await page.goto(RECIPE_URL);
    await page.getByRole('button', { name: /Poradit se s kuchařkou/ }).click();
    await page.getByPlaceholder('Napište, na co máte chuť…').fill('pravý ramen');
    await page.getByRole('button', { name: 'Odeslat' }).click();

    // Before the first poll lands we can only honestly claim it's queued.
    await expect(page.getByText('Chystám hledání…')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: 'Zrušit hledání' })).toBeVisible();
    await expect(page.getByText('Hledám recepty na webu…')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/Čtu nalezený recept/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/Našla jsem: Pravý ramen/)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: 'Použít tento recept' })).toBeVisible();
  });

  test('a search survives leaving the page and coming back', async ({ authedPage: page }) => {
    await settleConsent(page);
    await mockRefine(page, {
      preview: {
        reply_text: 'Podívám se na web.', candidate: null, alternatives: [],
        research_job_id: 44, question: null, hint_matched: null,
      },
      research: [
        { status: 'searching', reply_text: null, candidate: null },
        { status: 'ready', reply_text: 'Našla jsem: Pravý ramen.',
          candidate: candidate(11, 'Pravý ramen') },
      ],
    });
    await page.goto(RECIPE_URL);
    await page.getByRole('button', { name: /Poradit se s kuchařkou/ }).click();
    await page.getByPlaceholder('Napište, na co máte chuť…').fill('pravý ramen');
    await page.getByRole('button', { name: 'Odeslat' }).click();
    await expect(page.getByText('Chystám hledání…')).toBeVisible({ timeout: 15_000 });

    // The Celery job outlives the page; before the job id was parked, this
    // reload orphaned it and the "come back later" promise was false.
    await page.reload();

    await expect(page.getByText(/Pokračuju v hledání receptu na webu/)).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/Našla jsem: Pravý ramen/)).toBeVisible({ timeout: 20_000 });
  });
});

test.describe('undo', () => {
  test('the confirmation persists and swaps back to the previous recipe', async ({
    authedPage: page,
  }) => {
    const acceptedIds: number[] = [];
    await settleConsent(page);
    await mockRefine(page, { onAccept: (body) => { acceptedIds.push(body.accept as number); } });
    await page.goto(RECIPE_URL);
    await page.getByRole('button', { name: /Poradit se s kuchařkou/ }).click();
    await page.getByPlaceholder('Napište, na co máte chuť…').fill('něco s kuřecím');
    await page.getByRole('button', { name: 'Odeslat' }).click();
    await page.getByRole('button', { name: 'Použít tento recept' }).click();

    const banner = page.getByRole('status').filter({ hasText: 'Hotovo — místo' });
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toContainText('Mocked Oats');
    await expect(banner).toContainText('Kuřecí salát');

    // Well past a 4s toast's lifetime — long enough to actually read the new
    // recipe and change your mind, which is the whole point.
    await page.waitForTimeout(6_000);
    await expect(page.getByRole('button', { name: 'Vrátit původní recept' })).toBeVisible();

    await page.getByRole('button', { name: 'Vrátit původní recept' }).click();

    await expect.poll(() => acceptedIds).toEqual([7, 3]);
    await expect(page.getByText('Vrátili jsme původní recept.')).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole('button', { name: 'Vrátit původní recept' })).toHaveCount(0);
  });
});
