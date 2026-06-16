# QA Report — Subscription / Payment Gateway Path Mapping

**Target:** https://eatalnicek.eu (production)
**Date:** 2026-06-10
**Tester:** Senior QA (Playwright-driven, live prod)
**Scope:** Map every path by which a user could attempt to perform a subscription/payment, and pinpoint where each path works or dead-ends.

---

## 1. Summary Verdict

**Can a user perform a subscription/payment on prod today? NO — CONFIRMED.**

There is **no payment or subscription gateway wired anywhere in production**. Every "buy / upgrade / select tier / start" call-to-action — including the paid **Standard (99 CZK/měsíc)** and **Premium (199 CZK/měsíc)** tiers — performs a pure client-side `navigate('/login')`. No Shopify checkout, no payment provider, no checkout API call is ever issued. The Shopify backend (`shopifyin`) is **not mounted** in Django. The meal-plan funnel behind login has **no paywall / entitlement gate** wired to any payment.

The journey dead-ends at the very first paid step: clicking a paid tier sends the user to a login form, not a checkout. Money can never change hands.

A secondary, unrelated blocker also exists: **new accounts require email verification before login**, which blocked completing the authenticated funnel during this test (see §5).

---

## 2. Gateway Path Inventory

| # | Path | Entry point | Steps | Reaches payment? | Where it dead-ends | Expected vs Actual |
|---|------|-------------|-------|------------------|--------------------|--------------------|
| P1 | Pricing → **Free** ("Začít zdarma") | `/pricing` Free tier CTA | click → `/login` | **No** | `/login` | Expected: free signup. Actual: dumped to login, no signup-from-pricing context. Acceptable for free. |
| P2 | Pricing → **Standard 99 CZK/měsíc** ("Vybrat Standard") | `/pricing` Standard tier CTA | click → `/login` | **No** | `/login` (zero network calls) | Expected: Shopify recurring checkout. Actual: `navigate('/login')`, no checkout. **BROKEN** |
| P3 | Pricing → **Premium 199 CZK/měsíc** ("Vybrat Premium") | `/pricing` Premium tier CTA | click → `/login` | **No** | `/login` (zero network calls) | Expected: Shopify recurring checkout. Actual: `navigate('/login')`, no checkout. **BROKEN** |
| P4 | Navbar "Začít zdarma" | Landing navbar | click → `/login` | **No** | `/login` | Expected: signup. Actual: login. As-designed for free entry. |
| P5 | Hero "Vytvořit jídelníček zdarma" | Landing hero | click → `/login` | **No** | `/login` | Free-entry CTA. As-designed. |
| P6 | Final CTA "Vytvořit můj první plán" / "Vytvořit jídelníček zdarma" | Landing & pricing footers | client-side nav → `/login` | **No** | `/login` | Free-entry CTA. As-designed. |
| P7 | Navbar/footer "Ceník" | Landing | click → `/pricing` | **No** (it's the pricing page) | `/pricing` | Correct — routes to pricing. |
| P8 | Authenticated funnel `/onboarding` → `/create` → `/plan/:id` | Inside app (post-login) | requires verified login | **No payment step exists** | n/a (no paywall) | Expected (per intended doc): entitlement gate before generation. Actual: ProtectedRoute redirects unauth to `/login`; no payment gate observed in routing. **COULD NOT FULLY TEST** — login blocked by email verification (§5). |
| P9 | Direct backend probe `/api/shopify/*` | URL/API | GET/POST probes | **No** | endpoints not mounted | Expected: 404 / not-mounted. Actual: SPA HTML fallback (not a registered Django route). **CONFIRMED not mounted.** |

---

## 3. Per-Path Detailed Findings (observed evidence)

### P2 / P3 — Paid tier CTAs (the core failure)
- On `/pricing` the three tiers render: **Zdarma 0 CZK**, **Standard 99 CZK/měsíc** ("Doporučeno"), **Premium 199 CZK/měsíc**. Screenshot: `qa-02-pricing.png`.
- Clicking **"Vybrat Standard"** → URL changed to `https://eatalnicek.eu/login`.
- Clicking **"Vybrat Premium"** → URL changed to `https://eatalnicek.eu/login`.
- Clicking Free **"Začít zdarma"** → `https://eatalnicek.eu/login`.
- **Network observation:** `browser_network_requests` after each paid-tier click showed **zero non-static requests** (only 3 static resources). No request to any Shopify domain, no `/api/shopify/...`, no checkout URL, no payment provider. The CTA is a pure client-side route change.
- **Conclusion:** All three pricing CTAs are wired identically to `navigate('/login')`. The paid tiers are visually present but functionally inert — they sell nothing.

### P4–P6 — Landing entry CTAs
- Navbar "Začít zdarma", hero "Vytvořit jídelníček zdarma" both → `/login`. Consistent free-entry funnel. No payment intent on landing.

### P7 — "Ceník" navigation
- Navbar "Ceník" → `/pricing` correctly. Footer "Ceník" links to `/pricing`. Both fine.

### P8 — Authenticated funnel & paywall
- ProtectedRoute confirmed: direct navigation to `/create` and `/onboarding` while unauthenticated both **redirected to `/login`**.
- Could not walk the full funnel because the test account could not log in (email verification blocker, §5). Therefore the presence/absence of an in-app paywall on plan generation **could not be positively observed end-to-end**. However, no client-side payment code path was ever exercised, and the backend has no Shopify endpoints (§4), so any entitlement gate — if present — cannot be tied to a real payment.
- Login form (`qa-03-login.png`) offers: Přihlášení (login), Registrace (register), Google OAuth ("Pokračovat přes Google"), forgot-password.

---

## 4. Backend Probe Results (`/api/shopify/*`)

Probed from the browser against the live API. **Key discriminator:** a *registered* Django/DRF route returns a JSON error on a wrong method (e.g. 405 `{"detail":"Method ... not allowed."}`); an *unregistered* route falls through to the SPA `index.html` (the frontend catch-all).

| Endpoint | Method | Status | Content-Type | Body | Interpretation |
|----------|--------|--------|--------------|------|----------------|
| `/api/auth/login/` | GET | **405** | application/json | `{"detail":"Method \"GET\" not allowed."}` | Real Django route (registered) |
| `/api/auth/register/` | GET | **405** | application/json | `{"detail":"Method \"GET\" not allowed."}` | Real Django route (registered) |
| `/api/auth/register/` | POST | **201** | — | account created | Real, working |
| `/api/auth/login/` | POST | **401** | — | invalid credentials (unverified) | Real, working |
| `/api/shopify/test/` | GET | 200 | text/html | SPA `index.html` | **NOT a Django route** — SPA fallback |
| `/api/shopify/test/` | POST | 403 | text/html | SPA/CSRF HTML | **NOT a Django route** — handled by frontend layer, not DRF |
| `/api/shopify/checkouts/` | GET | 200 | text/html | SPA `index.html` | **NOT a Django route** |
| `/api/shopify/checkouts/` | POST | 403 | text/html | SPA/CSRF HTML | **NOT a Django route** |
| `/api/shopify/webhooks/orders/paid/` | POST | 403 | text/html | SPA/CSRF HTML | **NOT a Django route** |

**Conclusion (confirmed by observation):** The `shopifyin` app is **NOT mounted**. Unlike `/api/auth/*` (which returns DRF JSON 405 proving registration), all `/api/shopify/*` paths return the SPA HTML fallback — i.e. Django/DRF has no URL pattern for them; the frontend static service answers instead. The hypothesis was "expect 404"; the *actual* behavior is "SPA HTML fallback (200 GET / 403 POST)," which is functionally equivalent to "route does not exist" but is a more precise finding worth noting.

---

## 5. Test Account Used

- **Identity:** username `qasubtest8x3k`, email `qa.subscription.test+8x3k@example.com`, throwaway password.
- **Completed:** Registration via `/login` → Registrace tab → "Vytvořit účet". `POST /api/auth/register/` returned **201**. UI showed: *"Account created! Check your email to verify, then log in."*
- **BLOCKER:** Login attempt with the new credentials returned `POST /api/auth/login/` **401 "Invalid credentials"**. The account requires **email verification before first login**. I do not control the `example.com` mailbox, so verification could not be completed.
- **Consequence:** The authenticated funnel (onboarding → create → plan view) could **NOT** be walked. Per instructions, only ONE account was created; no second attempt was made. No meal-plan generation was triggered.
- Note: one stray account now exists on prod in unverified state and can be cleaned up if desired.

---

## 6. Gap Analysis — Intended Journey vs Reality

| Intended (per internal plan doc) | Reality observed on prod |
|----------------------------------|--------------------------|
| `/pricing` tier → pays on Shopify (recurring) | Tier CTAs `navigate('/login')`; no checkout, no Shopify call |
| Shopify `orders/paid` webhook provisions entitlement in Django | `/api/shopify/webhooks/orders/paid/` not a registered route (SPA fallback); `shopifyin` not mounted |
| Entitlement gate passes before first plan generation | No payment-linked entitlement gate exists; only ProtectedRoute auth gate |
| Recurring subscription model (99 / 199 CZK/měsíc) | Pricing copy says "/měsíc" and FAQ says "zrušit kdykoliv" (cancel anytime), implying recurring — but nothing is wired to collect it |
| Welcome email post-purchase | No purchase event can fire; not testable |

The pricing page is **marketing-complete but commerce-empty**: it advertises monthly recurring tiers and savings ("ušetří 850 CZK měsíčně", "méně než jedno kafe týdně") yet has no mechanism to charge anyone.

---

## 7. Severity-Ranked Findings

**S1 — CRITICAL (blocks all revenue).** Paid-tier CTAs ("Vybrat Standard" 99 CZK, "Vybrat Premium" 199 CZK) do not initiate any checkout; they `navigate('/login')` with zero network activity. Users cannot pay. — *Evidence: P2/P3, zero non-static requests captured.*

**S2 — CRITICAL.** Shopify backend (`shopifyin`) is not mounted: `/api/shopify/test/`, `/api/shopify/checkouts/`, `/api/shopify/webhooks/orders/paid/` are not registered Django routes (SPA fallback, not DRF 405/JSON). No checkout creation and no payment webhook can be received. — *Evidence: §4 table.*

**S3 — HIGH.** No payment-linked entitlement/paywall exists in the funnel. The only gate is auth (ProtectedRoute). Even if a tier were "selected," nothing enforces tier limits via payment. — *Evidence: P8; routing redirects on auth only.*

**S4 — MEDIUM (process blocker for QA, also a real UX gate).** New registrations require email verification before login (`register`→201 then `login`→401 + "Check your email to verify"). This is correct security behavior but blocked end-to-end funnel testing and would block any auto-provisioned post-purchase login flow if not coordinated. — *Evidence: §5.*

**S5 — LOW.** Pricing copy promises a recurring monthly subscription with "cancel anytime" that does not exist, a potential consumer-protection/expectation mismatch once live. — *Evidence: §6.*

---

## 8. Recommendations (to make the gateway functional)

1. **Wire the paid-tier CTAs to a real checkout.** On "Vybrat Standard"/"Vybrat Premium", call a backend endpoint that creates a Shopify checkout (or subscription) and redirect the browser to the Shopify-hosted checkout URL. Decide model: Shopify native subscriptions vs. one-off per-goal — pricing says "/měsíc" so recurring is implied; align code to copy.
2. **Mount the `shopifyin` app** in Django root URLConf so `/api/shopify/...` resolves (verify by GET → DRF JSON 405, not SPA HTML).
3. **Implement and register the `orders/paid` webhook** with HMAC verification; on receipt, provision/update the user's entitlement (tier, plan/edit quotas) in Django.
4. **Add a real entitlement gate** on plan generation (`/create`) that checks the provisioned tier and enforces the advertised quotas (2 / 7 / 30 plans, etc.). Today generation is reportedly permissive.
5. **Coordinate account provisioning with email verification** so a post-purchase user can log in without a manual verify step (e.g. auto-verify on confirmed Shopify order, or magic-link).
6. **Add an authenticated "upgrade" surface** (account/billing page) so existing free users can reach checkout from inside the app, not just from `/pricing`.

---

## 9. Reproduction Steps

**S1 (paid CTA dead-ends):**
1. Open `https://eatalnicek.eu/pricing`.
2. Open browser devtools Network tab; clear it.
3. Click "Vybrat Standard" (or "Vybrat Premium").
4. Observe URL becomes `/login` and **no** XHR/fetch to any checkout/Shopify endpoint fires.

**S2 (shopify not mounted):**
1. In console: `fetch('/api/auth/login/').then(r=>r.text()).then(t=>console.log(t))` → JSON `{"detail":"Method \"GET\" not allowed."}` (route exists).
2. `fetch('/api/shopify/checkouts/').then(r=>r.text()).then(t=>console.log(t.slice(0,80)))` → `<!DOCTYPE html>` SPA fallback (route does NOT exist).

**S3 (auth-only gate):**
1. While logged out, navigate to `https://eatalnicek.eu/create` → redirected to `/login`. No payment step encountered.

**S4 (verification blocker):**
1. `/login` → Registrace → fill username/email/password → "Vytvořit účet" → 201 + "Check your email to verify".
2. Switch to Přihlášení, enter same credentials → 401 "Invalid credentials" (cannot log in until verified).

---

## 10. Evidence / Artifacts

- `/opt/llmDietPlanner/qa-01-landing.png` — Landing page (entry CTAs).
- `/opt/llmDietPlanner/qa-02-pricing.png` — Pricing page, all 3 tiers (full page).
- `/opt/llmDietPlanner/qa-03-login.png` — Login/Registration page (dead-end of all paid CTAs).
- Network captures: paid-tier clicks produced only static requests; observed API calls were `POST /api/auth/register/ → 201` and `POST /api/auth/login/ → 401`.
- Console: only probe-induced errors (401/403/405/404), no organic app errors.

**Confirmed by observation:** S1, S2, S4, all path-inventory rows except P8.
**Could not fully test (and why):** P8 authenticated funnel & in-app paywall — blocked by email verification (S4).
