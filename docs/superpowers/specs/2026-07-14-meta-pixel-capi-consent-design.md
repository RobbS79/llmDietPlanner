# Meta Pixel + Conversions API + Consent — Design

**Date:** 2026-07-14
**Status:** Approved (pending user spec review)
**Jira:** llmMealPlanner — Phase I (Pilot), task #3 (see `docs/phase-1-pilot-preflight.md` §P0.3)
**Context:** Last remaining P0 blocker before the FB/IG ad campaign. Prod currently has zero analytics — no pixel, no consent banner, no funnel measurement.

## Goal

Instrument the acquisition funnel so the FB/IG pilot produces real learning — which campaigns drive signups and paid conversions, and the willingness-to-pay signal — while staying GDPR/ePrivacy-correct for the Czech market.

## Decisions (locked in brainstorming)

1. **Measurement depth:** Browser Meta Pixel for client events **+ server-side Conversions API (CAPI) for the money events** (`signup`, `plan_generated`, `paid`). Rationale: FB/IG pilot traffic skews iOS + in-app browser, where browser-Pixel attribution degrades most; CAPI with hashed email restores attribution on exactly the events we care about.
2. **Event split is clean — no dedup.** No event fires from both client and server, so there is no client/server deduplication to manage.
3. **Consent:** first-party **binary banner** (Přijmout / Odmítnout), equal prominence. Prior opt-in — nothing tracking-related loads until Accept. Built in-house (not a third-party CMP) because the CSP is strict `self`-only and there is a single tracking purpose.
4. **`signup` is server-only** (CAPI). We have the real email server-side → better match quality than a browser event, and it keeps the no-dedup property. A browser-visible signup event can be added later with a shared `event_id` if wanted.

## Event architecture

| Funnel event | Fires from | Channel | Meta event | Match keys |
|---|---|---|---|---|
| `landing_view` | client, landing mount | Pixel | `PageView` | `fbp` |
| `quiz_started` | client, onboarding quiz start | Pixel | custom `QuizStarted` | `fbp` |
| `checkout_started` | client, before Stripe redirect | Pixel | `InitiateCheckout` | `fbp`, `fbc` |
| `signup` | server, on account create | CAPI | `CompleteRegistration` | hashed email, `fbp`, `fbc`, IP, UA |
| `plan_generated` | server, plan gen complete | CAPI | custom `PlanGenerated` | hashed email, `fbp`, `fbc` |
| `paid` | server, Stripe webhook | CAPI | `Purchase` (value, `CZK`) | hashed email, `fbp`, `fbc` |

**Match-key forwarding:** Once the Pixel loads (post-consent) it sets the `_fbp` first-party cookie. `_fbc` is derived from the `fbclid` URL param captured at landing. Both are read server-side for CAPI events. Because `paid` fires at webhook time (no browser present), `_fbp`/`_fbc` are **persisted at `checkout_started`** (on the user's `MarketingAttribution` row) so the webhook can still attach them.

Each CAPI event carries a generated `event_id` (idempotency + future dedup headroom) and `event_source_url`.

## Consent gating

- **Client:** no Pixel script injected, no `_fbp` cookie, no client events until the user clicks **Přijmout**. **Odmítnout** → nothing loads. The choice is stored in `localStorage` under a versioned key (re-askable if the consent version bumps).
- **Server:** consent is **persisted per user** (`MarketingAttribution.marketing_consent`) so the webhook-time `paid` event can honor it. CAPI events fire **only** when the user's stored consent is true.
- Pre-signup events (`landing_view`, `quiz_started`) are anonymous and client-only → naturally gated by the banner, nothing server-side to check.
- **Legal note:** Reject must be as easy as Accept (equal button prominence, no dark pattern). Single purpose = a binary banner is a valid consent form.

## First-party attribution (`MarketingAttribution` model)

New model in the new `analytics` app, one-to-one with `User`, so we can answer "which campaign → paid" in our own Postgres independent of Meta:

- `user` (OneToOne)
- `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`
- `fbclid`, `fbp`, `fbc`
- `landing_at`
- `marketing_consent` (bool), `consent_at` (datetime), `consent_version` (str)

**Capture flow:** UTM params + `fbclid` captured at landing into `localStorage`; attached to the signup request payload; server writes the `MarketingAttribution` row at signup, stamping the consent decision carried in that same payload (from `localStorage`). Anonymous consent lives only in `localStorage` until a user exists — there is no anonymous server row. The consent endpoint (below) then handles *changes* of mind post-authentication.

## Backend components

- **`analytics/` (new app) — CAPI service** (`analytics/capi.py`): builds and POSTs events to `https://graph.facebook.com/<ver>/<pixel_id>/events`. Responsibilities: SHA-256 hashing of email (lowercased, trimmed), payload assembly, consent gate, `test_event_code` passthrough, network send with timeout + best-effort failure logging (never block the request path — fire async via Celery, consistent with existing task infra).
- **`MarketingAttribution` model + migration.**
- **Consent endpoint** (`POST /api/consent/`): records a consent decision (+ version, timestamp) for the current **authenticated** user (handles a post-signup change of mind); idempotent. Anonymous decisions are not stored server-side — they ride the signup payload.
- **Hook points (call the CAPI service):**
  - `login_app/views.py` — registration/account-create → `signup`.
  - `diet_planner/services/meal_plan.py` — plan generation completion → `plan_generated`.
  - `billing/views.py` — Stripe webhook `checkout.session.completed` / subscription paid → `paid` (value + `CZK`).
- **CSP** (`llm_diet_planner_project/middleware.py`): add Facebook hosts (below).
- **Settings/env:** `FB_PIXEL_ID`, `FB_CAPI_ACCESS_TOKEN` (secret), `FB_CAPI_TEST_EVENT_CODE`, `ANALYTICS_ENABLED` flag. CAPI is server→`graph.facebook.com` (outbound), not subject to browser CSP.

## Frontend components

- **`analytics` lib** (`frontend/src/lib/analytics.ts`): Pixel loader (injected only post-consent), typed event helpers (`trackLandingView`, `trackQuizStarted`, `trackCheckoutStarted`), `_fbp`/`_fbc`/UTM readers. All no-op unless consent granted and `VITE_FB_PIXEL_ID` set.
- **UTM/fbclid capture hook** (runs at landing): parse `window.location.search`, persist to `localStorage`.
- **Consent banner component** (`ConsentBanner`): binary Přijmout/Odmítnout, equal prominence, Market-Paper themed to match the public site; writes decision to `localStorage` + `POST /api/consent/`; on Accept, triggers Pixel load.
- **Wiring:** Landing mount (`landing_view` + PageView), onboarding quiz start (`quiz_started`), pre-Stripe-redirect (`checkout_started`); attach UTM/fbclid to the signup request.
- **CSP meta** in `frontend/index.html` updated in lockstep with the middleware (the fonts-bug lesson: middleware header overrides the meta tag; both must agree).

## CSP changes (both `middleware.py` and `index.html`)

- `script-src`: add `https://connect.facebook.net`
- `img-src`: add `https://www.facebook.com`
- `connect-src`: add `https://www.facebook.com`

## Config / env matrix

| Var | Where | Secret | Purpose |
|---|---|---|---|
| `VITE_FB_PIXEL_ID` | frontend build | no | Pixel ID for browser Pixel |
| `FB_PIXEL_ID` | Django env | no | dataset id for CAPI |
| `FB_CAPI_ACCESS_TOKEN` | Django env | **yes** | CAPI auth |
| `FB_CAPI_TEST_EVENT_CODE` | Django env | no | Events Manager test validation |
| `ANALYTICS_ENABLED` | Django env + frontend | no | master flag; ships dark, flip on when Meta is ready |

Applies across `.env`, `docker-compose`, and DO App Platform `squid-app` (per env-config convention; DO handles deploy).

## Prerequisite (user-owned, blocks live validation + campaign, NOT the build)

Meta account is not yet set up. In Meta Events Manager, the user must create:
1. Meta Business account + ad account for eatalnicek.eu
2. Dataset (Pixel) → **Pixel ID**
3. **Conversions API access token**
4. Domain verification for eatalnicek.eu (for iOS Aggregated Event Measurement)

The build proceeds behind `ANALYTICS_ENABLED=false`; IDs are plugged in and the flag flipped once the dataset exists.

## Testing

- **Unit:** CAPI payload build; SHA-256 email hashing (normalization); consent gate (asserts **no** send when consent false); UTM parsing; `MarketingAttribution` write at signup.
- **Manual:** Meta Events Manager "Test Events" via `test_event_code`; Meta Pixel Helper for client events.
- **Prod QA** (per project rule — test against prod, all affected pages, Playwright): walk the full funnel with consent **accepted**, confirm all 6 events land in Events Manager; then walk with consent **rejected**, confirm **zero** events fire (client and server).

## Out of scope

- Full CAPI on all six events (client `landing_view`/`quiz_started`/`checkout_started` stay Pixel-only).
- Third-party consent-management platform.
- GA4 / Plausible / any second analytics vendor.
- iOS Aggregated Event Measurement event prioritization tuning (post-launch, once volume exists).

## Rollout

1. Build behind `ANALYTICS_ENABLED=false` (dark).
2. User completes Meta prerequisite in parallel.
3. Set env (Pixel ID, CAPI token) on `squid-app`; deploy.
4. Validate via Events Manager Test Events, then prod QA both consent paths.
5. Flip `ANALYTICS_ENABLED=true`.
