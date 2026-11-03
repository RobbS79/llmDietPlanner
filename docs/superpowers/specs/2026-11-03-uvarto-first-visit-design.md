# Uvařto first visit: design

Date: 2026-11-03. Status: approved by owner in conversation, pending spec review.
Branch: `feat/uvarto-launch` (stacked on `feat/rename-uvarto`, which renames Vařto to Uvařto).

## Goal

A stranger lands on the site, asks a cooking question, sees real recipes within seconds, collects dishes into one shopping list that shows what is on sale, and signs up only to keep what they built. The structured week plan becomes a second path, not the front door.

Today's first visit requires a 2-step form (prompt + country + city, then five meal-type steppers), a forced 5-step onboarding quiz, and up to 4 minutes of generation before a single dish is shown.

Reference material:
- Clickable mockup: https://claude.ai/artifact/YF3fvtdfDhsP3dqEGN7BBP
- UX design: session scratchpad `ux/ux-design.md`. Its decisions are folded in below.
- Copy deck: session scratchpad `ux/copy.md`. All Czech strings below come from it.

## Decisions made with the owner

| Topic | Decision |
|---|---|
| Visual system | Keep Market Paper (colours, fonts, components). Drop the shouting style: no `uppercase`/`italic`/`font-black`/`tracking-widest` labels on the touched pages. |
| Voice | Informal "ty" everywhere user-facing (the copy deck's rules). "Uvařto" is neuter and does not decline: "v Uvařto", "Uvařto vybralo". |
| Two paths | Everyone starts with dishes. The week plan is offered twice: a link under the search box ("Chceš mít jasno na celý týden? Poskládej mi plán") and "Udělat z toho celý týden" after picking dishes. There is no fork question at the door. |
| What is free | Search, recipes and deals are free and unlimited (rate-limited against bots). Free accounts get **3 saved shopping lists per calendar month** and the existing **2 free week plans**. |
| What is paid | Standard 99 Kč: unlimited saved lists + 7 plans/month. Premium 199 Kč: unlimited saved lists + 30 plans/month. These are the existing plan quotas plus the new list entitlement. |
| Deals | Always free. Show what is on sale, at which shop and until when. Never prices or savings. |
| Anonymous AI | Anonymous search makes one Gemini call (prompt understanding) and selects from the published collection. Gemini never writes recipes for anonymous visitors. |

## User flow

1. **Landing (`/`):** "Co dnes uvařit?" with one text box ("Najít recepty") and six example chips. Below it are a "Tento týden v akci" deals strip, where each item starts the search "Co uvařit z {item}", and a "Z naší sbírky" row of 4 recipes. The current receipt hero, stat row, "three steps" and "built for people who…" sections are removed.
2. **Results (same page, URL `/?q=…`):** a "Hledám:" line shows removable tags for what was understood, then 4 recipe cards with photo, name, time, kcal when known, a deals badge when ≥1 ingredient is on sale, and "Chci tohle". "Ukaž mi něco jiného" shows the next 4.
3. **Recipe sheet:** opens over the results so the basket and scroll position survive. It shows the photo, time, kcal and macros, the source credit, the "Tento týden v akci" line, the ingredients with deal markers, and the first 2 steps followed by "… a dalších N kroků". Primary button "Chci tohle".
4. **Tray:** a sticky bar appears after the first pick: "{n} jídla · {m} surovin · {k} v akci" with a "Nákupní seznam" button.
5. **Combined shopping list (`/nakup`, works anonymously):** headed "Nákup na {n} jídla", with a people stepper ("Pro kolik lidí", 1–6, default 2). Deal items come first, showing shop and end date, then everything else. Each row has a checkbox and "mám doma", and rows needed by several dishes say "do {n} jídel". Buttons "Uložit si to" and "Udělat z toho celý týden".
6. **Signup sheet:** triggered only by keeping something (Uložit, a plan, or "Přihlásit se"). It shows thumbnails of the visitor's own dishes, with "Pokračovat přes Google" as the main button and "Nebo e-mailem" below. Fine print: "Zdarma, bez karty. První 2 plány máš u nás zadarmo." The basket survives the Google round-trip and email verification because it lives in localStorage until it is attached to the account.
7. **After signup:** the list is saved and attached to the account, and the user lands on it with the welcome message from the copy deck. If the search carried a restriction, a card asks "Pamatovat si „bez masa“ i příště?". The forced `/onboarding` redirect is removed.
8. **Week plan sheet:** asks "O co ti jde?" (4 chips, skippable) and "Kolik jídel chceš mít připravených?" (5 večeří / 5 obědů a 5 večeří / Nastavím si sám). Picked dishes, the prompt and the understood restrictions carry over. "Sestavit můj plán" creates a pool goal through the existing generation path. Country defaults to CZ and city is no longer asked.

## Architecture

### Backend (Django, `diet_planner` unless noted)

**`POST /api/discover/`** (anonymous allowed). Input `{q: str, page: int}`. Output `{understood: [label], exact: bool, recipes: [card], has_more: bool, fallback: bool}`.
- Reads the request with `extract_prompt_facets` (existing; one Gemini call). It has a hard 5 s timeout; on timeout, error or an exhausted daily budget, it falls back to a plain text match over names and ingredients (`fallback: true`).
- Selects from published `CuratedRecipe` main-dish candidates using the existing hard gate (`recipe_matches_facets` plus dietary and time gates) and `score_recipe`, with no Gemini gap filling.
- With no exact match, it returns the nearest popular recipes with `exact: false`.
- Cards use a new compact serializer for `CuratedRecipe`: id, slug, name, image (dish image else category image, same rule as `serializers.py` `get_image_url`), time, kcal when computed, and the deals summary from `recipe_deals` with one `active_deal_index()` per request. Macros and the source credit are on the recipe sheet only.
- `understood` is built from facets as Czech display labels (e.g. `low_carb` → "méně sacharidů", with a not-medical note flag when the prompt mentions diabetes).

**`GET /api/discover/recipe/<id>/`**. Full sheet data for one published recipe: ingredients (via `ingredient_display`), steps, nutrition, source and deals.

**`GET /api/deals/this-week/`**. The top N active deals from `active_deal_index()`, with canonical, display name, shop and valid_until. The frontend builds the search phrase ("Co uvařit z …") from the canonical. It returns an empty list when nothing is active or nothing is still valid. The frontend then hides the strip. A stale deal is never shown.

**`POST /api/shopping-list/compose/`** (anonymous allowed). Input `{recipe_ids: [int], people: int}`. Output: the merged lines.
- Lines merge only when canonical and unit both match; otherwise they stay as separate lines.
- Amounts are scaled by `people` and rounded for shopping: pieces and cloves round up to whole numbers, g/ml to a sensible step, and spoon or "to taste" units show no amount.
- Each line says how many dishes need it and carries its deal.

**Saved lists:** a new model `SavedShoppingList(user, recipe_ids JSON, people, at_home JSON, created_at)` with `POST/GET /api/shopping-lists/`. Creating one enforces the entitlement: free accounts get 3 per calendar month, and an active subscription is unlimited. Over the limit the endpoint returns 402 `LIST_LIMIT` with the copy "Tento měsíc už máš uložené 3 seznamy. S předplatným bez omezení."

**Plan creation:** `DietaryGoalCreateRequest.city` becomes optional (default ""), `country` defaults to CZ and `language_code` defaults to `cs`. The plan sheet maps its answers to the pool counts: "5 večeří" → dinners 5; "5 obědů a 5 večeří" → lunches 5, dinners 5; "Nastavím si sám" → the existing steppers. Picked recipe ids are passed through and pre-fill pool slots before selection.

**Abuse protection (the "nobody takes it again and again" rule):**
- **Rate limit:** a DRF `ScopedRateThrottle` scope `discover` at 20/day per visitor, plus a burst scope at 6/minute.
- **Bot check:** a Cloudflare Turnstile token is required on `/api/discover/` after the first 3 searches of a session. Verification happens server-side.
- **Daily Gemini budget:** a counter for discover calls is kept in Redis, through Django's cache. Past `DISCOVER_DAILY_LLM_BUDGET`, search uses only the text fallback.
- **Caching:** the discover output (understood labels, flags, ranked recipe ids) is cached per normalised query for 24 h, or 5 minutes when it came from the text fallback. Pages are sliced from it, and cards and deals are built fresh per request, so an expired deal is never served from cache. Chip queries are not pre-warmed; the first visitor's search fills the cache. Django `CACHES` is configured to the existing Redis, on a separate DB index from the Celery broker.
- **Spend alert:** a Slack alert fires when the daily discover LLM count crosses 80% of the budget. It reuses the `check_llm_health` Slack plumbing.
- **One free allowance per person:**
  - Registration normalises email (lowercase; for gmail.com and googlemail.com, drop dots and the `+tag`) and rejects a normalised duplicate.
  - Registration rejects disposable-email domains from a bundled blocklist.
  - A `signup` throttle scope allows 5 registrations per day per IP.

### Frontend (React, `frontend/src`)

- **`pages/Landing.tsx`:** rebuilt around the flow above. It is split into components under `components/discover/`: `SearchBox`, `ExampleChips`, `UnderstoodTags`, `RecipeCard`, `RecipeSheet`, `BasketTray`, `DealsStrip`.
- **`lib/basket.ts`:** the basket store (recipe ids, people, at-home marks), persisted in localStorage with versioned keys. `attachBasketAfterLogin()` runs on the first authenticated load: it posts the saved list, then clears the key.
- **`pages/ShoppingList.tsx`:** the route `/nakup` is public and is registered in BOTH `App.tsx` and `entry-server.tsx`.
- **`components/auth/SignupSheet.tsx`:** wraps the existing Google redirect and email registration. It sets a return path so the Google callback lands back on `/nakup`.
- **`components/plan/PlanSheet.tsx`:** the two questions, posting to the existing goal-create endpoint. `CreatePlan.tsx` keeps only the "Nastavím si sám" stepper path, without country or city.
- **Onboarding:** the forced redirect in `App.tsx` (`!profile.onboarding_completed`) is removed. The route stays reachable from Settings.
- **Copy:** the strings come from the copy deck in "ty" voice. The phrases on the deck's ban list are removed from every touched page, and from `prerender.mjs` and the SSR meta.
- **Analytics** (Meta Pixel + CAPI, existing consent gate): `Search`, `ViewContent` (recipe sheet), `AddToCart` (Chci tohle), `InitiateCheckout` (open list), `CompleteRegistration` (existing), `Lead` (plan started).

### Data fixes in scope

- **Wrong photos:** audit public and published recipes whose category image contradicts the dish, e.g. "Kuře Hasselback Primavera" (spaghetti image) and "Tradiční kuře na paprice" (soup image). Fix their `food_category`, or exclude them from discover until fixed.
- **"Krabičky" requests:** prompt understanding must parse "krabičky do práce na celý týden" into a meal-prep style facet; today it returns empty. Add the style to the facet prompt and vocabulary, with a test.

## Error and empty states

| Situation | Behaviour |
|---|---|
| No exact match | "Na tohle jsme ve sbírce nic přesného nenašli. Tady je, co je nejblíž." plus nearest recipes. For signed-in users, a link to a plan where Gemini can write the missing dish. |
| Nothing understood | "Vybrali jsme pár oblíbených receptů. Zkus napsat surovinu, třeba „z cukety“." |
| LLM slow, failing or over budget | Silent text-search fallback. Never an error screen. |
| Rate limit or bot check | A Turnstile challenge in place. On a hard limit: "Na dnešek už je hledání dost. Zkus to zase zítra." |
| Deals empty or stale | Strip and badges hidden. |
| No kcal for a recipe | Line hidden, never 0. |
| Free list limit reached | 402 → the paywall sheet with the copy above and a link to /pricing. The list is still shown, only not saved. |

## Testing

- **Backend:** TDD per endpoint.
  - Discover: facets → gate → ranking, the fallback path, budget exhaustion and the throttle.
  - Compose: merge rules, people scaling, rounding.
  - Saved lists: the entitlement boundary at the 3rd/4th list and the calendar-month reset.
  - Registration: email normalisation and the disposable-domain block.
  - Plan schema: optional city.
  - Run with the CI env (`python -m pytest diet_planner billing analytics login_app social`).
- **Frontend:** vitest for the basket store, the attach-after-login flow and the plan-sheet answer mapping; `tsc --noEmit`.
- **End to end:** the e2e smoke covers landing → chip → add → list → signup sheet visible.
- **Prod:** `/qa-prod` on the deployed release, using the 28 real-demand prompts (memory `real-demand-test-prompts`) as the search test set.

## Success measures

- p50 time from submit to results under 5 s on prod.
- The six chips and the 28 real-demand prompts return at least one exact match, except a documented list.
- A funnel is visible in Meta Events Manager: Search → AddToCart → InitiateCheckout → CompleteRegistration.

## Owner actions (outside the repo)

- Create a Cloudflare Turnstile widget for the site and put its keys in the DO app env:
  - `TURNSTILE_SITE_KEY` (runtime, backend) and `VITE_TURNSTILE_SITE_KEY` (BUILD-TIME env in DigitalOcean, baked into the frontend bundle by `Dockerfile.prod`) must both be set, to the same site key.
  - `TURNSTILE_SECRET_KEY` (runtime).
  - The backend asks for the challenge only when both `TURNSTILE_SECRET_KEY` and `TURNSTILE_SITE_KEY` are set. Without them the bot check is skipped and only the throttles apply. If the build-time key is missing while the runtime keys are set, visitors past the free searches see "Teď to nejde ověřit. Zkus to prosím za chvíli." instead of a widget.
- Rename the Stripe products, the Facebook Page and the Pinterest board to Uvařto.
- Set `DISCOVER_DAILY_LLM_BUDGET` in the DO app env. It defaults to 500 calls/day.

## Out of scope

- The domain move to uvarto.eu. It is a separate rollout after the owner registers the domain.
- Prices or savings, a store picker, budget and household-size questions, and a diabetes chip.
- Live Gemini recipe writing for anonymous visitors.
- Refine chat on the landing page. It stays inside saved plans.
- Aisle grouping of the shopping list (there is no ingredient category data yet).
- Editable servings on a single recipe. The people count applies only to the combined list.
- Deferred from v1 to keep the build small: the "Z naší sbírky" recipe row on the landing page, and the "Pamatovat si „bez masa“ i příště?" card after signup. The chips and the deals strip already give a zero-typing start, and dietary preferences stay editable in Settings.
