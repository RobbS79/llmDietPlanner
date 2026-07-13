# Phase I (Pilot) — Pre-flight Audit & Fix List

**Audit date:** 2026-07-13
**Method:** Full prod funnel walkthrough on https://eatalnicek.eu (Playwright, desktop 1440×900 + mobile 390×844): landing → /recepty → recipe detail → /pricing → email signup → onboarding quiz → plan generation (plan #120) → in-app recipe → Stripe Checkout (live session, aborted before payment). Prod logs and DO app spec inspected. Test account: `preflight0713` (user id 23), activated manually via prod console because of blocker #1.

**Verdict:** Not ready for the FB/IG campaign until P0 items are closed. Core machinery works (discounts fresh, plan gen ~60–85 s, live checkout reachable); the failures are in the signup path, the landing↔product promise, and measurement.

**Jira:** this list feeds *llmMealPlanner — Phase I (Pilot)*. Meta Pixel (#3) is its own Jira task there.

---

## P0 — Launch blockers

### 1. Email signup dead — SMTP credentials invalid
- **Observed:** Registration creates the account (`is_active=False`) but the verification email never sends. Prod logs: `SMTPAuthenticationError 535 BadCredentials` for `admin@zentaktestin.com` via smtp.gmail.com. Celery retries 3× then gives up silently. Every email signup dead-ends; only Google OAuth works.
- **Fix:** Switch sender to the current ops mailbox **admin@kentakin.eu**:
  - Generate a fresh Gmail/Workspace app password for admin@kentakin.eu.
  - Update DO App Platform env vars on `squid-app`: `EMAIL_HOST_USER`, `DEFAULT_FROM_EMAIL`, `EMAIL_HOST_PASSWORD` (secret).
  - Verify end-to-end with a real signup after deploy (email must arrive in inbox, not spam — check SPF/DKIM alignment for kentakin.eu if it lands in spam).
  - Consider a transactional provider (Resend/Postmark) later; not a Phase I requirement.

### 2. Shopping list with price range must return (landing↔product gap)
- **Observed:** Landing hero promises "nákupní seznam s reálnými cenami z vašeho obchodu" and shows a weekly total (1 247 Kč mock). In the app there is currently **no shopping list and no prices at all** — the whole-plan shopping list was removed 2026-06-23 (`fcd6a43`) and the per-recipe price surface was never shipped when recipes pivoted to the deals headline. A recipe today shows ingredients + quantities, kupi.cz deal links, and nutrition only.
- **Decision (2026-07-13):** Re-introduce a **per-recipe shopping list with an honest from–to price range**, powered by the already-built dormant price engine (model B: low = consumed amounts at price-book medians, high = ×1.25 whole-pack). Catalog-constrained prices only (catalog_id/canonical resolution — never name matching, never LLM estimates).
- Also align landing copy with what ships: if the surfaced unit is per-recipe range + deals, the hero mock should show that, not a whole-week priced list.

### 3. Meta Pixel + consent + funnel events → separate Jira task (Phase I)
- **Observed:** Zero analytics on prod — no pixel, no GA/Plausible, no cookie consent banner. The campaign would produce no learning (including the 5 €/8 € willingness-to-pay question).
- **Scope for the Jira task:** Meta Pixel + Conversions API; funnel events: `landing_view`, `quiz_started`, `signup`, `plan_generated`, `checkout_started`, `paid`; UTM capture on signup; GDPR-correct consent banner (CZ market) gating the pixel.

---

## P1 — Fixes incorporated into Phase I (before launch)

### 4. Brand fonts blocked by CSP — whole site renders in fallback fonts
- The Django middleware CSP (`llm_diet_planner_project/middleware.py`) sends `style-src 'self' 'unsafe-inline'` without `https://fonts.googleapis.com`, overriding the correct meta CSP in `frontend/index.html`. Browsers enforce the stricter policy → Google Fonts stylesheet blocked → Bricolage Grotesque / Hanken Grotesk / Space Mono never load.
- **Fix:** add `https://fonts.googleapis.com` to `style-src` and `https://fonts.gstatic.com` to `font-src` in the middleware header.

### 5. Stripe Checkout branding/locale
- Live checkout shows: business name "**mealPlanner**", product "**Eatalníček Standard**", English UI, EUR exchange-rate disclaimer ("1 CZK = 0.0429 EUR").
- **Fix:** Stripe Dashboard → public business name → **Vařto**; rename products (`prod_UhIrrRjOFqgNOX` Standard, `prod_UhJ97VKht7zYJg` Premium) to Vařto Standard/Premium; pass `locale: 'cs'` when creating the Checkout Session (`billing/stripe_client.py`). EUR disclaimer stems from account settlement currency — verify whether CZK settlement is available; if not, accept (minor once page is Czech).

### 6. Plan generation ignores stated constraints
Test input: "Chci šetřit za jídlo. Pro 4 osoby. Rozpočet 1500 CZK/týden. středně náročné recepty. **Max 30 minut** na přípravu." + snacks 2/den + drobné snacky 1/den.
- **Time constraint violated:** 5 of 9 recipes are 35–60 min (Chana Masala 55, Šakšuka 35, arašídová polévka 45, thajské kari 45, halušky-class picks). RAG retrieval/selection must filter or the prompt must enforce `max_prep_time`.
- **Snacks silently dropped:** requested 2+1/day, plan contains 0 snacks (9 meals = 3/day × 3 days) with no message. Either honor them or say why not.
- **Budget feedback absent:** goal was saving money on 1 500 Kč/week; the finished plan gives zero cost signal (ties into #2).

### 7. Portion/nutrition incoherence on meal cards
- Plan #120 mixes per-portion and whole-recipe values on equal-looking cards: breakfast omelette 260 kcal next to dinner "1 700 kcal" (Italský sekaný salát, fat 120 g) and breakfast "2 160 kcal" (francouzský toast). "Prům. kcal/den 2 632" is computed over the mix — meaningless.
- Public recipe 39 (Kuřecí parmigiana) shows "1 porce" with 680 g chicken / 2 008 kcal.
- **Fix:** normalize servings on the `Recipe` showcase model (same class of bug the portion-plausibility gate fixed for `CuratedRecipe`) and always display per-portion values scaled by plan household size.

### 8. Public /recepty duplicates and junk entries
- Duplicates: Kuřecí parmigiana ×3 (ids 29, 30, 39), Kulajda ×2 (31, 32), Bramborové halušky ×2 (33, 36).
- Junk from the early generation era: "Mandle" (id 7), "Tmavá čokoláda 85 %" (id 10), "Hami příkrm zelenina s kuřecími prsy" (id 40 — a baby-food jar).
- **Fix:** dedupe + unpublish junk in the `Recipe` showcase table (NOT `CuratedRecipe` — don't conflate the models).

---

## P2 — Polish (fast wins, also Phase I)

| # | Item | Where |
|---|------|-------|
| 9a | Nutrition labels in English: "fat / carbs / protein / calories" → Tuky / Sacharidy / Bílkoviny / Kalorie | plan cards, recipe pages (public + app) |
| 9b | Signup success toast in English: "Account created! Check your email to verify, then log in." → CZ | login/registration |
| 9c | Plan status chip "completed" in English → "hotový" (or hide) | dashboard plan cards |
| 9d | US date format "7/13/2026" → "13. 7. 2026" | dashboard plan cards |
| 9e | Grammar: "1 plánů zdarma zbývá" → "Zbývá 1 jídelníček zdarma" (needs 1/2–4/5+ declension) | dashboard header |

(Czech strings above to be finalized by Claude per the usual CZ-copy workflow.)

---

## Verified working (no action)

- Discount layer fresh on audit day: every checked recipe showed 2–4 active leaflet deals with kupi.cz links; headline "N z M surovin ve slevě tento týden" renders on public and in-app recipe pages.
- RAG recipe quality surface: "Ověřený recept" badge, source attribution with link, portion stepper defaulting to household size (4).
- Onboarding quiz → /create prefill of goals text works.
- Plan generation ~60–85 s (near the "<60 s" landing claim; acceptable).
- Free-tier metering ("2 jídelníčky zdarma", counter decremented to 1).
- Pricing page: Free / Standard 99 Kč / Premium 199 Kč; one click to live Stripe Checkout.
- Stripe live mode real: both prices active; **1 paying subscriber** (user 20, Standard 99 Kč) — first renewal ≈ **2026-07-15**; verify the renewal webhook provisions/extends entitlement (Dashboard → Developers → Webhooks → deliveries).

## Audit artifacts

- Test account `preflight0713` (user 23, soroka.robert8+preflight0713@gmail.com), plan #120 — safe to delete after Phase I QA.
- Screenshots: `preflight-landing-desktop.jpeg`, `preflight-landing-mobile.jpeg` (repo root, untracked).
- Prod console access pattern: DO exec websocket API (`do_exec.py`, session scratchpad) — doctl 1.116 has no `apps console` subcommand; handshake requires `Origin: https://cloud.digitalocean.com`.
