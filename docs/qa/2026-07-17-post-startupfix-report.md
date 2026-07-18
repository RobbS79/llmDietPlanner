# QA Prod Report — 2026-07-17

**VERDICT: GO**

Post-deploy verification of https://eatalnicek.eu after (1) start.sh reorder (Gunicorn binds before bootstrap seeds) and (2) /pricing copy change removing the fabricated "ušetří 850 Kč měsíčně" claim. Public-only run (Flow B disabled — no QA credentials provided).

| Flow | Check | Result | Notes |
|---|---|---|---|
| A | Landing `/` loads, goal hero renders | PASS | H1 "Zhubnout, nabrat, nebo jen jíst líp? Naplánujeme vám celý týden jídla." + goal-hero badge, sample shopping-list card, deals headline. All requests 200. |
| A | Landing primary CTA routes | PASS | "Vytvořit jídelníček zdarma" → `/login` with login/registration form rendered. |
| A | Consent banner appears on fresh visit | PASS | Dialog "Souhlas s cookies" with Meta Pixel disclosure + link to /privacy. |
| A | "Odmítnout" dismisses, no Pixel | PASS | Banner gone, `mkt_consent_v1` = `{"consent":false}`, `window.fbq` undefined, no facebook requests. |
| A | "Přijmout" dismisses, Pixel loads only after accept | PASS | Pre-consent: no fbq, no fbevents request. Post-accept: `mkt_consent_v1` = `{"consent":true}`, fbevents.js + signals/config both 200. |
| A | `/pricing` loads, three tiers render | PASS | Zdarma 0 Kč / Standard 99 Kč/měsíc (Doporučeno) / Premium 199 Kč/měsíc, FAQ + CTA render. |
| A | `/pricing` — "850 Kč" claim GONE | PASS | "850" absent from rendered DOM, raw SSR HTML, and the JS bundle (`index-BqYpYGTJ.js`, 0 matches). New honest line present: "Stojí méně než jedno kafe týdně. Za to dostanete **celý týden jídelníčku na míru vašemu cíli** — s recepty, nutričními hodnotami a nákupním seznamem, ve kterém rovnou vidíte suroviny aktuálně ve slevě." |
| A | `/recepty` showcase renders (not skeleton-stuck) | PASS | 24 recipe cards, images loaded (webp, naturalWidth 1024), 0 skeletons. API `/api/recipes/public/?page=1` → 200. |
| A | Recipe detail renders | PASS | `/recepty/46/gulasova-polevka-z-mleteho-masa/` — description, 65 min / 6 porcí, deals headline "3 z 8 surovin ve slevě tento týden" with store names, full ingredients + numbered steps. API detail → 200. |
| A | `/privacy` renders real content | PASS | H1 + 6 sections, includes Meta Pixel/marketing disclosure. |
| A | Mobile (390×844) hamburger nav | PASS | "Otevřít menu" opens (toggles to "Zavřít menu", expanded), menu links visible; "Ceník" navigates to /pricing. |
| A | KEY SIGNAL: zero console errors, zero 4xx/5xx | PASS | 0 console errors/warnings across all pages; every network request (pages, static assets, API, fonts, Pixel) returned 200. Startup reorder shows no serving degradation. |
| B | Login as QA account | SKIP | Flow B disabled — QA_TEST_USERNAME/QA_TEST_PASSWORD not provided. |
| B | Onboarding + plan generation | SKIP | Flow B disabled. |
| B | Reach Stripe Checkout | SKIP | Flow B disabled. |

## Console errors

None (0 errors, 0 warnings across landing, /pricing, /recepty, recipe detail, /privacy, mobile landing).

## Screenshots

No failures — no failure screenshots taken.

## Minor observations (non-blocking)

- After SPA navigation to /pricing (via nav link), `document.title` stays the landing title; direct load correctly shows "Ceník — Vařto" via SSR. Cosmetic only.
- Public recipe detail shows no nutrition block (ingredients/steps/deals only) — consistent with the showcase design, noted for awareness.
