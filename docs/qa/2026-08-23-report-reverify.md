# QA Prod Report — 2026-08-23 (re-verification after da53cf2)

**VERDICT: GO**

Re-verification run after deploy of commit `da53cf2`, targeting the earlier NO-GO
(catalog-ID / brand-token leak in ingredient lists of recipes 70, 71, 72).
Flow B skipped — QA_TEST_USERNAME/QA_TEST_PASSWORD not available for this run.

## Primary regression check — ingredient leak (recipes 70/71/72)

| Flow | Check | Result | Notes |
|---|---|---|---|
| Regression | /recepty grid — regex `\(#\d+\)` in rendered text | PASS | 0 matches in hydrated DOM (24 cards) and in SSR HTML of `/recepty/` |
| Regression | Recipe 70 detail (hydrated) | PASS | Ingredients: `tofu, rýže jasmínová, cuketa, cibule` — clean human names, no IDs/brands |
| Regression | Recipe 71 detail (hydrated) | PASS | Ingredients: `ovesné vločky, banány, mléko polotučné` |
| Regression | Recipe 72 detail (hydrated) | PASS | Ingredients: `tofu, špenát, rýže jasmínová` |
| Regression | Recipe 74 detail (newest card, hydrated) | PASS | Amount-carrying list (`0,3 l mléko, 60 g ovesné vločky, …`), clean |
| Regression | SSR raw HTML (curl, no JS) for 70/71/72/74 | PASS | `\(#\d+\)` = 0 matches; `pappudia\|kitchin\|vilgain` = 0 matches in all four |
| Regression | `recipeIngredient` JSON-LD in SSR (70, 72) | PASS | e.g. recipe 70: `tofu / rýže jasmínová / cuketa / cibule`; recipe 72: `tofu / špenát / rýže jasmínová` |
| Regression | Full sweep — all 24 published detail pages (SSR) | PASS | All HTTP 200, 0 leak matches, 0 brand-token matches |

Note: SSR pages require trailing-slash canonical URLs (`/recepty/<pk>/<slug>/`);
slash-less URLs serve the SPA shell. This matches the routing in
`llm_diet_planner_project/urls.py` and is not a regression.

## Flow A — Public smoke

| Flow | Check | Result | Notes |
|---|---|---|---|
| A1 | Landing hero + copy renders | PASS | H1 "Zhubnout, nabrat, nebo jen jíst líp?…", sample plan/shopping-list mock renders |
| A1 | Primary CTA routes correctly | PASS | "Vytvořit jídelníček zdarma" → `/login` with working login/registration form |
| A1 | Consent banner — "Odmítnout" | PASS | Banner dismissed, `mkt_consent_v1` stored with `consent:false` |
| A1 | Consent banner — "Přijmout" | PASS | Banner dismissed, consent stored |
| A2 | /recepty grid renders | PASS | 24 cards, no stuck skeletons; all 24 images load (lazy-load below fold, verified after scroll; spot curl 200 image/webp) |
| A2 | Card links resolve | PASS | All 24 detail URLs HTTP 200 (curl sweep) |
| A3 | Recipe detail content + deals headline | PASS | Recipe 70: full recipe + "1 z 4 surovin ve slevě tento týden" |
| A4 | /pricing tiers | PASS | Zdarma 0 Kč / Standard 99 Kč/měsíc / Premium 199 Kč/měsíc + FAQ |
| A5 | Legal page /privacy | PASS | Real content, 7 sections (Správce údajů … Zabezpečení) |
| A6 | Mobile 390x844 hamburger nav | PASS | "Otevřít menu" opens (Recepty/Ceník/Přihlásit/Vytvořit), Recepty link navigates |

## Flow B — Authed

| Flow | Check | Result | Notes |
|---|---|---|---|
| B1 | Login as QA account | SKIP | QA_TEST_USERNAME/QA_TEST_PASSWORD not provided for this run |
| B2 | Onboarding + plan generation | SKIP | Depends on B1 |
| B3 | Reach Stripe Checkout | SKIP | Depends on B1 |

## Console errors

Only two entries across the whole session, both on anonymous landing load:

```
401 https://eatalnicek.eu/api/auth/profile/
401 https://eatalnicek.eu/api/auth/refresh/
```

These are the app's expected logged-out auth probe (session check), not a defect.
No console errors on /recepty, recipe details, /pricing, /privacy, or mobile nav.

## Screenshots

No failures — no failure screenshots taken. Page snapshots from the run are in
the local `.playwright-mcp/` directory (gitignored, not committed).
