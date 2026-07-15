# Phase I (Pilot) — Backlog Tickets (drafted 2026-07-15)

Paste-ready tickets for the **`llmMealPlanner — Phase I (Pilot)`** Jira epic (the same
epic the [2026-07-13 preflight audit](phase-1-pilot-preflight.md) feeds). No Jira MCP
is connected to the working session, so these are drafted here for copy-paste; connect
the Atlassian integration to have them filed directly.

Priority order (recommended): **#4 Profile/account** (unblocks GDPR consent-withdrawal +
subscription self-service — arguably needed before paid ads) → **#1 Landing value clarity**
(pre-ad-campaign conversion) → **#2 Day-count picker** (cheap win) → **#3 Replace-recipe**.

---

## Ticket 1 — Landing value clarity: lead with goal-based hero, demote deals to honest supporting proof

- **Type:** Story  |  **Priority:** High (pre-ad-campaign)
- **Epic:** llmMealPlanner — Phase I (Pilot)

**Problem**
The landing page (`frontend/src/pages/Landing.tsx`) makes three co-equal core promises —
save time, save money (deals), eat well — so a cold visitor gets no single sharp reason to
sign up. The *loudest* promise (deals) is also the vaguest: we can only say how many
ingredients are on sale, never a Kč amount (informational-only deals;
`PRICE_DISPLAY_ENABLED=false`). It also mismatches the **Fitness** ad audience the pilot
targets: the click promises goals/macros, the page shouts grocery discounts.

**Decision (locked 2026-07-15)**
- ONE hero promise: *"a meal plan built around YOUR goal."* Matches the Fitness ad; absorbs
  time + nutrition + deals as supporting proof.
- Deals stay, reframed honestly: *"u některých surovin vidíte aktuální slevy"* — **never a
  fabricated Kč savings figure.** (Real Kč savings = separate dormant pricing-data project,
  out of scope here.)

**Scope / Acceptance criteria**
1. **Hero rewrite** (`Landing.tsx` ~L63–77):
   - Badge → `"Jídelníček podle vašeho cíle"` (*A meal plan for your goal*)
   - H1 → `"Zhubnout, nabrat, nebo jen jíst líp?"` / `"Naplánujeme vám celý týden jídla."`
     (*Lose weight, build muscle, or just eat better? We'll plan your whole week of meals.*)
   - Sub → order: goal → nutrition (kalorie a makra) → shopping list → deals as *"navíc"*:
     `"Popíšete svůj cíl vlastními slovy — a dostanete jídelníček na míru s recepty,
     nutričními hodnotami (kalorie a makra) a nákupním seznamem. U některých surovin navíc
     rovnou vidíte aktuální slevy z letáků."`
   - Keep `"Bez kreditní karty. Hotovo za méně než 60 sekund."` + CTA unchanged.
2. **Re-order/relabel sections** so goal + nutrition lead and deals reads as a supporting
   benefit, not a co-headline (stat band L104, "who it's for" L155, features grid L316).
3. *(Stretch)* "Pick your goal" device in the sample-plan section (L246) so the visitor sees
   the plan framed for their goal.
4. All Czech copy finalized by Claude with EN gloss for review.
5. **Prerender/SSR meta** updated to match (`prerender.mjs` + Django SSR — landing meta is
   NOT only in `index.html`).
6. Verify on prod after deploy (Tailwind drops unknown classes silently; dev box OOMs on
   vite build).

**Non-goals:** No Kč savings numbers. No re-enabling `PRICE_DISPLAY_ENABLED`. No per-audience
landing variants (deferred; noted as future option).

---

## Ticket 2 — Flexible meal-plan length: let users pick any number of days

- **Type:** Story  |  **Priority:** Medium  |  **Effort:** Small (frontend-only)
- **Epic:** llmMealPlanner — Phase I (Pilot)

**Problem**
The create-plan form offers only discrete day presets `[1, 3, 7, 14, 30]`
(`frontend/src/pages/CreatePlan.tsx:308`). Users can't request, e.g., a 5-day or 10-day plan.

**Key finding — backend already supports it.** `DietaryGoal.num_days` is a plain integer with
`MinValueValidator(1)` / `MaxValueValidator(30)` (`diet_planner/models/core.py:351`) and the
API schema validates `num_days: int, ge=1, le=30` (`diet_planner/schemas.py:79`). **No backend
change, no migration** — this is purely a frontend control swap.

**Scope / Acceptance criteria**
1. Replace the preset buttons with a numeric picker (stepper or input) accepting **1–30**,
   default **7** (`CreatePlan.tsx:27,308`).
2. Optionally keep 3/7/14 as quick-pick chips *plus* the free input — don't remove the fast path.
3. Client-side validation (1–30, integer); mirror the backend bounds; friendly Czech error copy.
4. Verify a non-preset value (e.g. 5) round-trips: form → API → generated plan shows 5 days.

**Non-goals:** Raising the 30-day cap. Per-day customization of meal counts (separate).

---

## Ticket 3 — Replace a recipe from the recipe/meal view

- **Type:** Story  |  **Priority:** Medium  |  **Effort:** Small–Medium
- **Epic:** llmMealPlanner — Phase I (Pilot)

**Problem**
Once a plan is generated, users can't swap a single meal they don't like — no
swap/replace/regenerate exists anywhere user-facing (confirmed: only the internal
restriction-repair loop calls `regenerate_meal`). A returning user stuck with one disliked
recipe has no recourse short of regenerating the whole plan.

**Cost finding — cheap.** The retrieval machinery already exists:
`eligible_recipes_for_slot` + `score_recipe` + an `exclude_ids` param
(`diet_planner/services/recipe_retrieval.py:138-221`) already do single-slot candidate
selection from the `CuratedRecipe` corpus with **no LLM call**.
- **Primary path (free):** pull an alternative for that slot from the corpus, excluding the
  current recipe id. DB query, $0. Works when `RECIPE_GROUNDING_ENABLED` (on in prod) and the
  slot is covered.
- **Fallback (~$0.001–0.004 / swap):** one Gemini 2.5 Flash single-meal call (the
  `regenerate_meal` pattern) only when the corpus has no alternative.

**Scope / Acceptance criteria**
1. New endpoint, e.g. `POST /api/recipes/<meal_identifier>/replace/`, that returns a
   different recipe for the same slot: retrieval-first (`exclude_ids=[current]`), LLM fallback.
2. Replacement must honor slot constraints re-derived from the parent `DietaryGoal`
   (`meal_type`, dietary tags/restrictions, servings/household) and preserve
   `is_catalog_mapped()` so pricing/shopping stays coherent.
3. Preserve/repoint provenance: re-attach the existing `meal_identifier`, set
   `source`/`curated_recipe_id`/attribution fields (`recipe_retrieval.py:331-338`).
4. Frontend **"Vyměnit recept"** button on the meal card (`PlanView.tsx`) and/or recipe page
   (`RecipePage.tsx`); optimistic swap + loading state; Czech copy.
5. Decide + document a per-plan/per-day swap limit if needed (abuse/cost guard; realistically
   near-zero cost, so a soft limit is fine).

**Non-goals:** Multi-recipe "shuffle whole day." Editing recipe contents. Re-pricing.

---

## Ticket 4 — User profile / account & settings page

- **Type:** Story (likely splits into sub-tasks)  |  **Priority:** High (GDPR + billing self-service)
- **Epic:** llmMealPlanner — Phase I (Pilot)

**Problem**
There is **no user-facing profile/settings page.** Preferences are collected once in the
onboarding quiz and stored in `UserProfile.dietary_preferences`
(`login_app/models.py:12,51` — `goal, dietary_styles, allergies, household, budget, cooking,
shop`), then prefilled into each new plan (`CreatePlan.tsx:43-73`). After onboarding a user
**cannot view or change** their preferences, language, subscription, or consent — only
override prefs per-plan (which doesn't write back). A returning, paid-for user has nowhere to
manage their account.

**Scope / Acceptance criteria** — new page + route (e.g. `/profil` or `/nastaveni`), grouped:
1. **Preferences** (editable; persist back to `UserProfile.dietary_preferences`): goal ·
   dietary styles · allergies · household size / default servings · budget · cooking skill ·
   preferred shop · country + language (cs/sk) · default number of days *(ties to Ticket 2)*.
   Needs a backend endpoint to update `dietary_preferences` (GET `/auth/profile/` already exists).
2. **Account & auth:** email + verified status · auth provider (email/Google) · change password
   (email users) · **delete account** (GDPR).
3. **Subscription & usage** (billing app exists): current tier (Free / 99 / 199 Kč) · free
   generations remaining · **"Spravovat předplatné" → Stripe billing portal**.
4. **Privacy / consent:** **"Nastavení cookies"** toggle to view/withdraw marketing consent —
   this is the deferred GDPR follow-up #4 from the analytics rollout; a profile page is its home.
5. **Data:** export my data (GDPR nicety).
6. All Czech copy finalized by Claude with EN gloss; verify on prod.

**Why High:** items 2–4 (delete account, subscription management, consent withdrawal) are
things you arguably need **before running paid ads** — users must be able to manage a
subscription they paid for and withdraw tracking consent.

**Non-goals:** Avatar/social profile. Notification preferences (no notifications yet).

---

*Design decisions and code anchors above captured during the 2026-07-15 session. Ticket 1's
full hero copy + EN gloss is finalized; Tickets 2–4 are scoped but their Czech UI strings are
to be written when picked up.*
