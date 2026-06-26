# Auth App Re-skin → Market Paper — Design

**Date:** 2026-06-26
**Status:** Approved (brainstorm), pending implementation plan
**Predecessor:** Public re-skin shipped 2026-06-25 (PRs #25/#26/#27); brand leftovers PR #28. See `docs/superpowers/SESSION-CHECKPOINT-2026-06-25.md`.

## Goal

Carry the light "Market Paper" identity into the **logged-in product** so Vařto has one
visual identity end-to-end. Today the public site + auth-adjacent pages (Login, Forgot/Reset,
Pricing, Terms, Privacy, About, recipe pages) are light; the actual app behind login is still
dark slate. This closes that seam.

## Decisions (locked in brainstorm)

1. **Direction:** Full light Market Paper for the app (not a rebranded-dark variant).
2. **Depth:** *Considered recolor* — token swap to paper/ink/green as the base, **plus**
   per-page polish so cards, buttons, and type match the public site's styling. Existing
   layouts and flows stay as-is. Not a mechanical invert; not a per-page redesign.
3. **Onboarding:** Included — the multi-step quiz (`Onboarding.tsx`, 384 lines) gets the same
   treatment, so signup → onboarding → dashboard is seamless light.
4. **Verification login:** User provides a throwaway dev test account; Claude logs in locally
   and screenshots the real authenticated pages.

## Scope

**In scope — surfaces still dark:**

- Pages: `Dashboard.tsx`, `CreatePlan.tsx`, `PlanView.tsx`, `RecipePage.tsx`, `Onboarding.tsx`,
  `BillingSuccess.tsx`
- Shared chrome: `components/layout/Navbar.tsx`, `MainLayout.tsx`, `ui/LoadingScreen.tsx`,
  `ui/Toast.tsx`, App-level `ErrorBoundary` (in `App.tsx`)
- Components with dark defaults: `ProtocolUpload.tsx`, `ui/StatusTracker.tsx`, `ui/Skeleton.tsx`,
  `ui/Card.tsx`, `recipe/PortionStepper.tsx`, `recipe/RecipeIngredients.tsx`
- Token source: `src/lib/theme.ts`

**Out of scope:**

- Already-light public/auth-adjacent pages (no changes).
- Any layout redesign, copy changes, or new features.
- A user-facing dark-mode toggle (not requested).
- Backend / `DEFAULT_FROM_EMAIL` domain (tracked separately).

## Architecture — flip the token source, then migrate hardcoded tokens

The leverage point is `src/lib/theme.ts`. Many app components read `THEME.surface`,
`THEME.border`, `THEME.textPrimary`, etc. **Repoint `THEME` from dark slate to the light
tokens** and every consumer flips for free:

| THEME key      | Old (dark)        | New (light, Tailwind token) |
|----------------|-------------------|------------------------------|
| `bg`           | `bg-[#1e293b]`    | `bg-paper`                   |
| `surface`      | `bg-slate-700/50` | `bg-card`                    |
| `border`       | `border-slate-600`| `border-line`                |
| `textPrimary`  | `text-zinc-100`   | `text-ink`                   |
| `textSecondary`| `text-zinc-300`   | `text-muted`                 |
| `accent`       | `emerald`         | `green`                      |

`Card`'s `variant="app"` resolves through `THEME`, so it flips automatically; keep the
`variant` prop for source compatibility but both `app` and `paper` now render light.

Hardcoded dark utility classes (`slate-*`, `zinc-*`, `#1e293b`, `#334155`, `emerald-*`,
`rose-*`) do **not** go through `THEME` and must be migrated explicitly, page by page, to
semantic light tokens.

## Color migration map

- `emerald-*` (app accent) → `green` (brand): `emerald-600`→`green`, `emerald-500`→`green-mid`,
  hover/active scaled accordingly.
- `rose-*` / red errors → `paprika` (`paprika.strong` for text on paper to hold AA).
- `slate`/`zinc` neutrals → `paper` / `card` / `kraft` (surfaces), `line` (borders),
  `ink` / `muted` (text).
- Headings adopt `font-display` (Bricolage Grotesque) to match public pages; body `font-body`.

## Work units (each independently buildable + verifiable)

1. **Token foundation** — repoint `theme.ts`; confirm `Card` defaults light. Verify every
   `THEME.*` consumer renders sane.
2. **Shared chrome** — `Navbar` becomes a paper header matching the public `PublicHeader`
   (same `vařto.` wordmark + green accent, keeps the logged-in nav links + logout);
   `MainLayout` bg; `LoadingScreen`; `ErrorBoundary` crash screen; `Toast`.
3. **Dashboard**
4. **CreatePlan**
5. **PlanView**
6. **RecipePage**
7. **Onboarding** (quiz flow)
8. **Stragglers** — `BillingSuccess`, `ProtocolUpload`, `StatusTracker`, `Skeleton`,
   `PortionStepper`, `RecipeIngredients`.

Each page unit: token swap → Bricolage headings → Card/Button matched to public styling →
emerald→green / rose→paprika, with layout untouched.

## Accessibility

- Reuse the already-AA-darkened `muted` (#5E564C) for secondary text on paper.
- Body text uses `ink` (#241E1A) on `paper`/`card` — high contrast.
- Error text uses `paprika.strong` (#B23E1C), not the lighter default, to hold AA on paper.
- Global `:focus-visible` ring already exists from the public re-skin; verify it shows on app
  controls.

## Verification

1. `tsc` typecheck clean.
2. `vite build` succeeds; **grep the built CSS** for the expected rgb tokens (paper/ink/green) —
   Tailwind silently drops unknown classes, so a green build can still hide a broken theme.
3. **Playwright local**, logged in with the user-provided test account: screenshot
   Dashboard, CreatePlan, PlanView, RecipePage, Onboarding at **desktop + mobile**. Confirm:
   no dark slate remnants, brand consistent with public site, AA contrast, focus rings visible.
4. Save screenshots under `ux-review/` for eyeballing (untracked artifact).

## Ship

Single PR → `develop` (same flow as #25–28), then rolls to prod. Result: the two-identity
split is gone — Vařto is light end-to-end.

## Risks

- **Dense data UI on light paper** — meal plans, ingredient lists, and steppers are
  information-dense; verify they stay legible and not washed-out (sufficient surface/line
  contrast). Mitigated by `card` white surfaces over `paper` for data blocks.
- **Hardcoded-token misses** — the CSS-token grep + per-page screenshots catch stragglers a
  `THEME` flip won't.
- **Auth-gated verification** — requires the test account; without it, verification drops to
  build + code review only.
