# QA Prod Report — 2026-07-18

**VERDICT: GO**

Post-deploy verification of the refine-chat feature (PR #40) on https://eatalnicek.eu, run with the throwaway QA account (fresh, no prior plan). The initial run found one user-visible copy defect ("Odpovídá: czech" — raw English cuisine slug); a hotfix (commit 7567ca2) was deployed and re-verified same day at ~18:08 UTC. All checks now pass.

## Results

| Flow | Check | Result | Notes |
|---|---|---|---|
| Sanity | Landing `/` renders | PASS | Hero, CTA, footer all render; no console errors |
| Sanity | Consent banner | PASS | Appeared after clearing prior state; "Odmítnout" clicked, banner dismissed, `mkt_consent_v1 consent:false` stored (QA traffic excluded from analytics) |
| Sanity | `/recepty` renders | PASS | ~25 recipe card links, real hrefs (e.g. `/recepty/50/ovesna-kase/`); no console errors |
| Sanity | Login | PASS | QA account logged in, redirected to `/onboarding` |
| Setup | Onboarding quiz (5 steps) | PASS | All steps in Czech, completed; profile summary correct |
| Setup | Plan generation | PASS | 3-day plan (id 125), 9 meals, generated in ~60 s; all task-status polls 200; coherent Czech recipes with macros |
| 1 | Open recipe from plan | PASS | Meal card → `/plan/125/recipe/125:1:breakfast:0` ("Perfektní omeleta"), full detail: ingredients, 5-step postup, nutrition, attribution, deals headline |
| 2 | "Vyměnit recept" opens chat panel | PASS | Exact spec strings: intro "Na co máte chuť? Poradíme vám s výběrem.", placeholder "Napište, na co máte chuť…", send button aria-label "Odeslat", "Zavřít" button. Old single-hint input gone |
| 3 | First message → candidate | PASS | "něco s kuřecím" → user bubble + honest fallback "Přesně podle vašeho přání jsme nic nenašli, ale co třeba: Americké lívance?" + Czech follow-up question; candidate card with image, name, chips (30 min / 1452 kcal), "Použít tento recept". Response in ~2 s |
| 3 | Preview does NOT mutate plan/page | PASS | After turns, underlying page still "Perfektní omeleta." with original ingredients; plan slot unchanged until apply |
| 3 | "Odpovídá: …" line is Czech | PASS (after fix 7567ca2) | Initial run leaked raw English slug **"Odpovídá: czech"** (`_candidate_why` appended `recipe.cuisine.lower()` untranslated). Re-tested after hotfix — see "Re-test" below: cuisine slugs now map through Czech dictionary, no raw slugs observed |
| 4 | Second message → different candidate | PASS | "něco jiného, spíš vegetariánské" → new candidate "Venkovské snídaňové misky" (first candidate implicitly rejected), card updated |
| 5 | "Zavřít" + fresh reopen | PASS | Chat closed, "Vyměnit recept" button returned; on reopen no prior messages/candidate — state discarded |
| 6 | "Použít tento recept" applies swap | PASS | Toast "Recept byl vyměněn.", chat closed, page swapped in place to "Jemné tvarohové palačinky." (new ingredients, postup, deals); no full-page error |
| 7 | Plan view shows swapped slot | PASS | Day 1 breakfast now "Jemné tvarohové palačinky"; "Perfektní omeleta" gone |
| 8 | Console clean during feature flow | PASS | No JS errors during chat/swap (both runs); only pre-login session-probe 401/403 (benign, see below) |
| 9 | No 5xx | PASS | All `POST /api/recipes/…/refine/` calls → 200 across both runs; all other API calls 200/201 |

## Re-test of the failing row (2026-07-18 ~18:08 UTC, after commit 7567ca2, deployment ACTIVE)

Logged back in as the QA account (session still valid), opened plan 125 breakfast recipe, "Vyměnit recept", sent cuisine-flavored wishes:

- "něco českého" → candidate "Ovesná kaše" with **"Odpovídá: česká kuchyně"** — proper Czech, no slug.
- "něco italského" → candidate "Zeleninová frittata" with **"Odpovídá: italská kuchyně"** — proper Czech, no slug.

No raw English slug anywhere in the chat; assistant follow-ups fully Czech; both refine calls 200; console clean. PASS criteria met (Czech label shown; unmapped slugs would be dropped rather than leaked per the fix). Chat closed without applying — no plan mutation during re-test.

Evidence: `.playwright-mcp/refine-chat-odpovida-ceska-kuchyne-fixed.png`

## Console errors

Whole-session errors (none during the refine-chat flow itself, either run):

- `401` × 2 — `https://eatalnicek.eu/api/auth/login/` (pre-login session probe on page load; benign)
- `403` × 1 — `https://eatalnicek.eu/api/goals/` (pre-auth fetch before login; benign)

## Screenshots (local, not committed — authed session data)

- `.playwright-mcp/refine-chat-odpovida-czech-leak.png` — original defect: candidate card showing "Odpovídá: czech"
- `.playwright-mcp/refine-chat-odpovida-ceska-kuchyne-fixed.png` — after fix: "Odpovídá: česká kuchyně"

## Minor observations (not blocking, pre-existing)

- Plan/recipe macro labels are English lowercase ("fat / carbs / protein / calories") — pre-existing, not part of PR #40.
- Candidate kcal chip shows whole-recipe values (e.g. "1452 kcal" for lívance vs plan's per-portion figures) — worth a look for consistency.
- Recipe page `<title>` stays a static marketing title throughout the authed app (was "Přihlášení — Vařto" in run 1, "Vařto — Jídelníček na míru…" in run 2).
