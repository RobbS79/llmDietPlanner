# User Profile / Account & Settings Page — Design

**Date:** 2026-07-16
**Ticket:** Phase I (Pilot) backlog #4 (`docs/phase-1-pilot-backlog.md`)
**Status:** Design approved; ready for implementation plan.

## Problem

After onboarding, a user has no way to view or change their preferences, language,
subscription, or marketing consent. Preferences are collected once in the onboarding quiz
(`UserProfile.dietary_preferences`) and only ever overridden per-plan (which does **not**
write back). A returning, paid-for user has nowhere to manage their account. Three of the
gaps — **delete account (GDPR erasure)**, **subscription self-service**, and **marketing
consent withdrawal** — are arguably required *before* running paid ads.

## Goal

One auth-gated Settings page (`/nastaveni`) grouping five sections: Preferences, Account &
auth, Subscription & usage, Privacy/consent, and Data export. Plus the small backend and
navigation work needed to support it.

## Locked decisions (2026-07-16 brainstorming + Fable-5 design review)

- **Scope:** full page, all five sections (user chose complete build over a lean slice).
- **Delete = hard delete**, irreversible, no grace period. Genuine GDPR Art. 17 erasure.
- **Delete re-auth:** email users re-enter password; **Google users complete a fresh Google
  OAuth re-auth** (emailed confirmation is out — SMTP is a known P0 blocker). Endpoint is
  rate-limited and writes an anonymized audit record.
- **Stripe on delete:** cancel the subscription, **do NOT delete the Stripe customer**
  (Czech VAT/accounting invoice retention; GDPR Art. 17(3)(b) permits it). Idempotent flow.
- **Preferences PATCH:** change `PATCH /api/auth/profile/` from whole-dict **replace** to
  **merge** server-side, so system-set keys (`shop`) and future keys (`num_days`) survive.
- **Preferences editing UI:** extract onboarding option sets into a shared module; build
  fresh compact settings controls fed by it. (Kills the current 2–3-way enum duplication.)
- **Data export:** keep self-serve — a proper authenticated **axios blob download**, not a
  bare `<a href>` (which would 401 with no auth header).
- **Two-PR split** to isolate ad-funnel regression risk (see Phasing).

## Existing code this builds on (verified)

- **Routing:** `frontend/src/App.tsx` (react-router v6). Auth routes wrap `<ProtectedRoute>`
  (`frontend/src/components/auth/ProtectedRoute.tsx`, client-side JWT check).
- **Nav:** `frontend/src/components/layout/Navbar.tsx` — `navLinks` L6–10; logout is a bare
  icon (L47), no account menu today.
- **Profile API:** `UserProfileView` (`login_app/views.py:302–344`), routed
  `login_app/urls.py:56`, mounted `/api/auth/`. `GET` returns `{email, username,
  free_generations_remaining, total_generations, onboarding_completed, dietary_preferences}`
  (omits `primary_auth_provider`, `email_verified`). `PATCH` updates `dietary_preferences`
  by **whole-dict replace** (`views.py:333`).
- **Prefs shape** (authoritative: `frontend/src/pages/Onboarding.tsx:57–84`): `goal`,
  `dietary_styles[]`, `allergies[]`, `household_size`, `weekly_budget`, `cooking_skill`,
  `cooking_time`, `country`, `shop` (system-set, never user-editable).
  Model help_text keys are stale — trust the Onboarding interface.
- **Onboarding enums:** inline, **not exported** (`Onboarding.tsx:18–55`). `CreatePlan.tsx`
  duplicates label maps (`CreatePlan.tsx:46–50`).
- **Billing:** `GET /api/billing/me/` → `{subscription|null, free_generations_remaining}`
  (`billing/views.py:141–155`, wrapper `frontend/src/lib/billing.ts:41`).
  `POST /api/billing/portal/` → Stripe portal session, locale `cs`, 404 if no customer
  (`billing/views.py:106–138`, wrapper `billing.ts:33`). Tiers: Free / Standard 99 Kč /
  Premium 199 Kč. Frontend pricing hardcoded in `Pricing.tsx`.
- **Consent:** localStorage `mkt_consent_v1` via `getConsent()`/`setConsent()`
  (`frontend/src/lib/analytics.ts`); server sync `POST /api/analytics/consent/`
  (`analytics/views.py:9–23`, `IsAuthenticated`) → `MarketingAttribution`. Pixel loads once
  per session and is **not** torn down on withdrawal (only re-load is gated; `track()`
  respects consent immediately).
- **Change password:** `dj_rest_auth` `POST /api/auth/password/change/` (included at
  `login_app/urls.py:59`), not surfaced in UI. Google users have no usable password.
- **Provider:** `UserProfile.primary_auth_provider` (`email`/`google`/`facebook`).
- **Greenfield:** delete-account, data-export — no endpoints exist.
- **Auth:** JWT bearer from localStorage via axios client (`frontend/src/lib/api.ts`),
  `withCredentials:true`, `Authorization: Bearer` interceptor.

## Design

### Route, entry point, structure
- New page `frontend/src/pages/Settings.tsx` at `/nastaveni`, wrapped in `<ProtectedRoute>`.
- **Account dropdown** added to `Navbar.tsx`: shows email, a "Nastavení" link, and moves
  Logout inside it.
- **Layout:** single responsive scrolling page, five labeled section cards, sticky in-page
  section anchors on desktop. Not tabs (simpler for five sections, mobile-friendly).
- **Load:** parallel `GET /api/auth/profile/` + `GET /api/billing/me/` on mount; hydrate all
  sections. **Per-section saves** (each section owns its save button + inline Czech errors),
  not one giant form submit.

### Section 1 — Předvolby (Preferences)
- Editable form over `dietary_preferences`: goal · dietary styles · allergies · household
  size · weekly budget · cooking skill · cooking time · country + language (cs/sk) · default
  number of days (`num_days`, ties to backlog Ticket 2).
- Controls fed by **new shared module `frontend/src/lib/preferences.ts`** (option sets +
  label maps extracted from `Onboarding.tsx`). `Onboarding.tsx` and `CreatePlan.tsx`
  refactored to import from it.
- Saves via `PATCH /api/auth/profile/` sending only the edited keys — safe because the
  endpoint now **merges** (see backend change B3).

### Section 2 — Účet (Account & auth)
- Email + **passive** verified state (no resend action — SMTP is a P0 blocker; a
  resend/verify CTA we can't fulfill would be a dead end).
- Login method: email vs Google (from the extended profile payload).
- **Change password** form for email users via `POST /api/auth/password/change/`; hidden for
  Google users. Note: SimpleJWT tokens remain valid after a password change — accepted and
  documented for the pilot (no token blacklist rotation in scope).
- **Delete account** button → confirmation modal (see Delete flow).

### Section 3 — Předplatné (Subscription & usage)
- From `GET /api/billing/me/`: current tier (Free / Standard 99 / Premium 199 Kč), plans
  used vs monthly quota, free generations remaining.
- "Spravovat předplatné" → `openBillingPortal()` (Stripe portal). No sub → show Free + link
  to `/pricing`. Portal 404 (no customer) → fall back to Free display.

### Section 4 — Soukromí (Privacy / consent)
- Marketing-cookies toggle. **Initial state hydrated from the server consent record**
  (`marketing_consent` in the extended profile payload — see B4), reconciled with
  localStorage — so it doesn't lie after a device switch. Flipping calls `setConsent(...)` +
  `POST /api/analytics/consent/`.
- Honest caveat in copy/comment: an already-loaded Meta Pixel isn't torn down mid-session;
  withdrawal fully applies on next page load (`track()` gate respects it immediately).

### Section 5 — Moje data (Data export)
- "Stáhnout moje data" → `GET /api/auth/export/` via **axios blob download** (auth header
  required). Returns a JSON file: profile, prefs, plan list, subscription status, consent
  record. Authenticated, returns only the requesting user's data.

### Backend changes (login_app + billing)

- **B1. `DELETE /api/auth/account/`** (new, login_app):
  - Re-auth: email users → verify password; Google users → require a fresh Google OAuth
    re-auth completed within a short window (reuse existing Google flow).
  - **Rate-limited**; writes an **anonymized deletion audit record** (timestamp, Stripe
    customer ID, tier) — retained for chargeback defense (no PII).
  - Calls `billing/services.py::cancel_and_purge(user)` (new helper) to **cancel** the Stripe
    subscription (idempotent: already-canceled = success). **Does not delete the Stripe
    customer.** Snapshot Stripe IDs into the audit record *before* mutating.
  - Then `user.delete()` (cascade). If Stripe cancel raises a non-idempotent/real error →
    abort the local delete and surface it (never delete locally while a live paid sub
    remains). Verify SimpleJWT does a per-request DB user lookup so the access token dies on
    next call; client clears tokens + hard-redirects to `/`.
  - **Pre-implementation task:** enumerate the full `User.delete()` cascade (plans,
    `DietaryGoal`s, `MarketingAttribution`, curated-recipe interactions, billing rows) and
    confirm no FK `PROTECT` blocks deletion.
  - **Webhook check:** confirm the Stripe webhook handler returns 200 (not 500-retry) on
    `customer.subscription.deleted` / unknown-customer events after the user row is gone.
- **B2. `GET /api/auth/export/`** (new, login_app): assemble the requesting user's data as a
  downloadable JSON. Authenticated; PII limited to the caller.
- **B3. `PATCH /api/auth/profile/`** (modify): **merge** incoming keys into
  `dietary_preferences` instead of whole-dict replace. Preserves `shop` and future keys.
- **B4. Extend `GET /api/auth/profile/`**: also return `primary_auth_provider`,
  `email_verified`, and the current `marketing_consent` (+ `consent_version`) from
  `MarketingAttribution` — the consent endpoint is POST-only today, so this is how Section 4
  hydrates the toggle from the server record.

## Data flow
Mount → parallel profile + billing fetch → hydrate sections. Each section saves
independently (optimistic + loading state) over the existing JWT axios client. Delete flow:
re-auth → Stripe cancel (idempotent) → audit record → `user.delete()` → client token clear +
redirect.

## Error handling
- Per-section save errors shown inline in Czech (no global toast).
- Delete: re-auth failure → inline error; Stripe cancel real-failure → abort delete, surface
  error; already-canceled → proceed. Portal 404 → Free display fallback. Export 401 (missing
  auth) prevented by using the axios blob path, not a bare link.

## Testing
- **Backend (pytest):** delete paths (email w/ correct & wrong password; Google re-auth;
  with active sub, without sub, already-canceled sub — idempotency); rate-limit; audit
  record written; cascade actually removes dependents. Export payload shape + auth isolation
  (user A cannot fetch user B). Profile-extension fields present. Prefs PATCH **merge**
  (partial update preserves `shop`).
- **Frontend:** enum-refactor must not change onboarding/CreatePlan behavior (generated
  prompt strings identical before/after). Per-section save/error states.
- **Post-deploy:** `/qa-prod` on prod (always-test-prod rule); manual delete-account check on
  a throwaway account. Verify built Tailwind CSS after moving option-rendering code (Tailwind
  silently drops unknown classes).

## Czech copy
All UI strings finalized by Claude with EN gloss for review — written during implementation
planning, not here.

## Phasing (two PRs)
- **PR A — shared-enum refactor:** extract `preferences.ts`; refactor `Onboarding.tsx` +
  `CreatePlan.tsx` to consume it. No behavior change. Ship + QA on prod *first* (this touches
  the signup→onboarding→first-plan ad funnel).
- **PR B — Settings page + backend:** B1–B4, the five sections, Navbar account dropdown,
  built on top of the merged, QA'd PR A.

## Non-goals
Avatar/social profile. Notification preferences (no notifications exist). Refunds/proration
on delete (modal warns the paid period is forfeited). Re-enabling `PRICE_DISPLAY_ENABLED`.
Raising the 30-day plan cap. JWT blacklist rotation on password change.
