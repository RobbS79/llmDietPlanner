# QA Prod Report — 2026-07-17

**VERDICT: GO**

Post-deploy verification of https://eatalnicek.eu after commit `b51a00e` (replace-recipe swap + pricing test/docstring fix) went ACTIVE. Public surface only (Flow A); Flow B skipped — QA credentials not available in this environment.

## Results

| Flow | Check | Result | Notes |
|------|-------|--------|-------|
| A | Landing `/` renders, goal-based hero | PASS | H1 "Zhubnout, nabrat, nebo jen jíst líp? Naplánujeme vám celý týden jídla." renders with badge, subhead, mock shopping-list card. |
| A | Landing hero — no fabricated Kč savings | PASS | Hero shows only deals framing ("2 z 5 surovin ve slevě tento týden", "Ušetříte na tom, co je zrovna v akci") — no absolute Kč amounts. |
| A | Primary CTA routes correctly | PASS | "Vytvořit jídelníček zdarma" → `/login` with working Přihlášení/Registrace form. |
| A | Consent banner appears fresh | PASS | Dialog "Souhlas s cookies" renders on first visit (had to clear persisted `mkt_consent_v1` from a prior QA session in the browser profile — expected, not a bug). |
| A | "Odmítnout" dismisses, no Pixel | PASS | Banner dismissed, `mkt_consent_v1 = {"consent":false}` stored, `window.fbq` undefined, zero requests to facebook domains. |
| A | "Přijmout" dismisses, Pixel loads only after accept | PASS | Banner dismissed, `{"consent":true}` stored, `fbevents.js` + signals config (pixel 1573455420886048) loaded 200 only after click. No Pixel traffic pre-consent. |
| A | `/recepty` cards render + link to detail | PASS | Cards render with images, descriptions, "N ve slevě" badges, time/portions; API `GET /api/recipes/public/?page=1` → 200. Not skeleton-stuck. |
| A | Recipe detail (`/recepty/46/gulasova-polevka-z-mleteho-masa/`) | PASS | Title, "3 z 8 surovin ve slevě", Ingredience, Postup, Nutriční hodnoty all render; `GET /api/recipes/public/46/` → 200. SSR title correct ("… — Recept \| Vařto"). |
| A | `/pricing` tiers render | PASS | Three tiers: Zdarma 0 Kč / Standard 99 Kč/měsíc / Premium 199 Kč/měsíc, CTAs + FAQ render. |
| A | Legal page `/privacy` | PASS | Full policy renders incl. §4 Cookies (Meta Pixel consent disclosure). |
| A | Mobile 390×844 hamburger nav | PASS | "Otevřít menu" opens (aria-expanded), links Recepty/Ceník/Přihlásit se/Vytvořit jídelníček present; navigating to Recepty works. |
| A | Console errors / failed requests (all pages) | PASS | 0 console errors/warnings on every page; no 4xx/5xx network responses observed anywhere. |
| B | Login as QA account | SKIP | Flow B disabled — QA_TEST_USERNAME/QA_TEST_PASSWORD not present in this environment. |
| B | Onboarding + plan generation | SKIP | Flow B disabled (no credentials). |
| B | Reach Stripe Checkout | SKIP | Flow B disabled (no credentials). |
| B | Replace-recipe swap ("Vyměnit recept") | SKIP | New feature in `b51a00e` is behind login; cannot be exercised on public surface. Not reported as broken — needs an authed Flow B run to verify. |

## Console errors

None. Zero console errors or warnings on landing, /recepty, recipe detail, /pricing, /privacy, and mobile landing/nav.

## Failed network requests

None. All page/API/asset requests returned 200 across every page visited.

## Observations (non-blocking)

- `/pricing` copy claims "Průměrný uživatel ušetří **850 Kč měsíčně** na nákupech." This is a pre-existing marketing claim (not introduced by `b51a00e`), but given the project's move away from fabricated savings numbers it may warrant review.
- The deploy's headline feature (replace-recipe swap) is unverified in production until a Flow B run with QA credentials is possible.

## Screenshots

No failures — no failure screenshots taken. Page snapshots from the run are in the local `.playwright-mcp/` directory (gitignored).
