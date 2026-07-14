# QA Prod Report — 2026-07-14

**VERDICT: NO-GO** (one real finding on the primary funnel; site otherwise healthy)

Run type: **public-only dry run** (Flow B skipped — no QA creds in this session).
Base URL: https://eatalnicek.eu · Runner: /qa-prod validation (main loop, Playwright).

## Results

| Flow | Check | Result | Notes |
|---|---|---|---|
| A | Landing `/` renders (hero, CTAs, nav, footer) | PASS | Title, H1, CTAs, footer legal links all present |
| A | Landing console errors (initial load) | PASS | 0 errors |
| A | Consent banner appears + both buttons | PASS | "Odmítnout" / "Přijmout" present; banner dismisses on click (client-side) |
| A | Consent server persistence (anonymous) | **FAIL** | Clicking "Odmítnout" fires `POST /api/analytics/consent/` → **401**; console error on the main funnel |
| A | `/recepty` cards render + link to detail | PASS | ~26 real cards w/ images, discount badges, pagination (Strana 1 z 2); links resolve to `/recepty/<id>/<slug>/` |
| A | `/recepty` console errors | PASS | 0 errors |
| A | Recipe detail renders | PASS | Image, title, description, discount summary, ingredients/steps, CTA; 0 errors |
| A | `/pricing` tiers + FAQ | PASS | 3 tier cards, FAQ accordion, CTA; 0 errors |
| A | Legal page `/privacy` | PASS | Real content renders; 0 errors |
| A | Mobile (390×844) hamburger | PASS | Nav collapses; "Otevřít menu" opens Recepty/Ceník/Přihlásit se/Vytvořit jídelníček; consent banner correctly does NOT re-show once chosen |
| B | Login → onboarding → plan → checkout | SKIP | No `QA_TEST_USERNAME`/`QA_TEST_PASSWORD` — authed flow not exercised |

## Console errors

```
[ERROR] Failed to load resource: 401 @ https://eatalnicek.eu/api/analytics/consent/
        (fired on clicking "Odmítnout" as an anonymous visitor)
```
Raw log: `.playwright-mcp/console-2026-07-14T20-25-51-588Z.log`

All other pages: 0 console errors.

## Blocking finding

**Anonymous consent POST returns 401.** The consent banner posts to
`/api/analytics/consent/`, which is `IsAuthenticated`-only, so every anonymous
visitor who clicks Přijmout/Odmítnout gets a 401 + a console error. The banner
still dismisses and the choice is honored client-side (localStorage gates the
pixel), so the UX is not visibly broken — but:
- This is the exact audience the ad campaign pays to acquire (all anonymous), so
  the console noise lands on the primary funnel.
- If the intent was to capture consent/fbp/fbc server-side pre-signup, that
  capture silently fails for anonymous traffic.

**Likely by design** (anonymous users have no `MarketingAttribution` row yet), in
which case the fix is to **not POST when anonymous** (rely on localStorage until
signup) rather than to open the endpoint. Decide before ad spend. Relates to the
known "consent-via-login gap" follow-up in the analytics feature.

## Minor / advisory (non-blocking)

- **Duplicate recipes** on `/recepty`: Kulajda (`/31`, `/32`), Kuřecí parmigiana
  (`/29`, `/30`, `/39`), Bramborové halušky (`/33`, `/36`), Smažená rýže s vejcem
  (`/34`, `/43`) appear as separate cards. Corpus dedup candidate.
- **Grammar/i18n:** cards show "1 porcí" (should be "1 porce"); pluralization not
  applied for the singular case.
- **Savings claim on `/pricing`:** "Průměrný uživatel ušetří **850 Kč měsíčně**"
  is a hard number — check it survives the honest-framing stance (savings are
  currently informational-only per the pricing pivot).

## Dry-run meta

This run validated the QA tooling end-to-end (Playwright reaches prod, flows are
executable, report is produced). Flow B (authed: login → generate plan → reach
Stripe) is unexercised here and should be run once the DO-secret QA account is
provisioned.
