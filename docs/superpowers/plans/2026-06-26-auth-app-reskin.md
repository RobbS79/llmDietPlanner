# Auth App Re-skin → Market Paper — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the logged-in product (Dashboard, CreatePlan, PlanView, RecipePage, Onboarding, BillingSuccess + shared chrome) from the dark slate theme to the light "Market Paper" identity, so Vařto is one visual identity end-to-end.

**Architecture:** Flip the shared `THEME` token source in `src/lib/theme.ts` from dark to light (every component reading it flips for free), then migrate hardcoded `slate-*`/`zinc-*`/`emerald-*`/`rose-*` utility classes per file using a single deterministic Migration Map. Layouts and flows are unchanged — this is a recolor + type/Card/Button alignment, not a redesign.

**Tech Stack:** React 18 + Vite + TypeScript, Tailwind CSS (tokens defined in `frontend/tailwind.config.js`), Playwright for verification.

**Spec:** `docs/superpowers/specs/2026-06-26-auth-app-reskin-design.md`

**Working directory for all paths below:** `/opt/llmDietPlanner/frontend` unless stated otherwise.

---

## Migration Map (the single source of truth for every task)

Apply these replacements uniformly. Each old class has exactly one new class — no judgment calls. Tailwind tokens (`paper`, `card`, `kraft`, `line`, `ink`, `muted`, `green`, `green-mid`, `green-soft`, `paprika`, `paprika-strong`, `paprika-soft`) are already defined in `tailwind.config.js`.

**Surfaces / backgrounds**
| Old | New |
|-----|-----|
| `bg-[#1e293b]`, `bg-background` (page bg) | `bg-paper` |
| `bg-slate-700/50`, `bg-slate-700`, `bg-slate-800/60`, `bg-slate-800` (card surface) | `bg-card` |
| `bg-slate-900`, `bg-black/40`, `bg-black/30` (inset inputs/fields) | `bg-paper` |
| `bg-slate-600` (secondary button/chip fill) | `bg-kraft` |
| `from-[#334155]`, `via-[#334155]/60` (image overlay gradient) | `from-paper`, `via-paper/60` |
| `bg-slate-700/10` (faint empty-state fill) | `bg-kraft/40` |

**Borders**
| Old | New |
|-----|-----|
| `border-slate-600`, `border-slate-500`, `border-slate-700` | `border-line` |

**Text** (rule: bright neutrals → `ink`; dim neutrals → `muted`)
| Old | New |
|-----|-----|
| `text-white`, `text-zinc-100`, `text-zinc-200` | `text-ink` |
| `text-zinc-300`, `text-zinc-400`, `text-zinc-500` | `text-muted` |
| `text-black` (only on the old white CTA — see Buttons) | `text-white` |

**Green accent** (app `emerald` → brand `green`)
| Old | New |
|-----|-----|
| `bg-emerald-600`, `bg-emerald-500` (solid) | `bg-green` |
| `hover:bg-emerald-500`, `hover:bg-emerald-400` | `hover:bg-green-mid` |
| `text-emerald-400`, `text-emerald-500`, `text-emerald-300` | `text-green` |
| `hover:text-emerald-400`, `hover:text-emerald-300` | `hover:text-green-mid` |
| `border-emerald-500`, `border-emerald-600`, `border-emerald-500/20`, `border-emerald-500/30` | `border-green/40` |
| `bg-emerald-600/10`, `bg-emerald-500/10`, `bg-emerald-500/5`, `bg-emerald-500/[0.02]` (tint fills) | `bg-green-soft` |
| `ring-emerald-500`, `ring-emerald-600/50` | `ring-green` |
| `from-emerald-600 to-emerald-400`, `from-emerald-600/10 to-teal-600/5` (gradients) | `from-green to-green-mid` |
| `accent-emerald-600` (range input) | `accent-green` |
| `shadow-emerald-500/10` | `shadow-green/10` |

**Error / destructive** (`rose`/`red` → `paprika`)
| Old | New |
|-----|-----|
| `bg-rose-500/10`, `bg-red-600` | `bg-paprika-soft` (tint), `bg-paprika` (solid button) |
| `text-rose-400`, `text-rose-500`, `text-rose-600` | `text-paprika-strong` |
| `border-rose-500/20`, `border-rose-500/30` | `border-paprika/30` |
| `hover:bg-red-500` | `hover:bg-paprika-strong` |
| `hover:bg-rose-500/10 hover:text-rose-400` | `hover:bg-paprika-soft hover:text-paprika-strong` |

**Buttons** (idiom alignment to public site)
| Old pattern | New |
|-------------|-----|
| Primary CTA `bg-white text-black hover:bg-zinc-100/200` | `bg-green text-white hover:bg-green-mid` |
| Secondary `bg-slate-600 text-zinc-300 border-slate-500` | `bg-kraft text-ink border-line` |
| Outline `border border-slate-600 text-zinc-200 hover:text-white` | `border border-line text-ink hover:bg-kraft` |

**Type** (headings adopt the public display face)
- Page hero `<h1>` and section `<h2>`: add `font-display`. Keep existing `uppercase`/`italic`/`tracking` and weight. Recolor accent dots (`<span class="text-emerald-500 not-italic">.</span>`) → `text-paprika` to match the `vařto.` wordmark.
- `selection:bg-emerald-500/30` → `selection:bg-green-soft`.

**Focus rings:** any `focus-visible:ring-emerald-500` → `focus-visible:ring-green`.

> When a class isn't in this table (e.g. `text-rose-400` used as a stat color, `bg-teal-600/5`), apply the nearest rule by family (rose→paprika, teal→green). If genuinely ambiguous, prefer the `muted`/`green`/`paprika` semantic that matches the element's role, and note it in the commit body.

---

## Task 1: Token foundation — flip `THEME` to light

**Files:**
- Modify: `src/lib/theme.ts`
- Modify: `src/components/ui/Card.tsx:16,22`

- [ ] **Step 1: Repoint `THEME` to light tokens**

Replace the entire body of `src/lib/theme.ts` with:

```ts
export const THEME = {
  bg: "bg-paper",
  surface: "bg-card",
  border: "border-line",
  textPrimary: "text-ink",
  textSecondary: "text-muted",
  accent: "green",
};
```

- [ ] **Step 2: Make `Card` focus ring brand-green and `paper` the unified surface**

In `src/components/ui/Card.tsx`, change the focus ring (line ~22) from `focus-visible:ring-emerald-500` to `focus-visible:ring-green`. The `variant='paper'` branch already uses `bg-card border-line`; the `'app'` branch now resolves to the same via `THEME`, which is correct — leave the prop in place for source compatibility.

```tsx
  const focusRing = isInteractive
    ? 'focus-visible:ring-2 focus-visible:ring-green focus-visible:outline-none'
    : '';
```

- [ ] **Step 3: Typecheck**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/lib/theme.ts frontend/src/components/ui/Card.tsx
git commit -m "feat(reskin): flip app THEME tokens to Market Paper light"
```

---

## Task 2: Shared chrome — Navbar, MainLayout, LoadingScreen, ErrorBoundary, Toast

**Files:**
- Modify: `src/components/layout/Navbar.tsx`
- Modify: `src/components/layout/MainLayout.tsx:8`
- Modify: `src/components/ui/LoadingScreen.tsx`
- Modify: `src/App.tsx` (ErrorBoundary render, ~lines 34-42)
- Modify: `src/components/ui/Toast.tsx` (1 dark token)

- [ ] **Step 1: Re-skin the Navbar header to paper**

In `src/components/layout/Navbar.tsx`, the header bar and wordmark are dark. Replace the header shell and brand so it matches the public `PublicHeader` look (paper surface, `vařto.` lowercase wordmark, paprika dot, green active state). Apply to the existing structure:

- Line ~24 `<header className="h-16 border-b border-slate-600 bg-[#1e293b]/80 backdrop-blur-xl ...">` → `<header className="h-16 border-b border-line bg-paper/90 backdrop-blur-xl flex-none z-50">`
- The brand block (lines ~28-33): replace the dark icon-box + uppercase italic `DietPlanner.` with the public wordmark:

```tsx
        <Link to="/" className="flex items-center gap-3 group">
          <span className="font-display font-extrabold text-2xl tracking-tight text-ink lowercase">
            vařto<span className="text-paprika">.</span>
          </span>
        </Link>
```

- Desktop nav pill (lines ~37-50): `bg-slate-700 ... border-slate-600` → `bg-kraft border-line`; active link `bg-emerald-600 text-white` → `bg-green text-white`; inactive `text-zinc-300 hover:text-zinc-200 hover:bg-slate-600` → `text-muted hover:text-ink hover:bg-card`.
- Apply the Migration Map to every remaining `slate-*`/`zinc-*`/`emerald-*` in the file (logout button, mobile drawer). The mobile drawer panel `bg-[#1e293b]` → `bg-card border-line`.

- [ ] **Step 2: MainLayout selection color**

In `src/components/layout/MainLayout.tsx:8`, change `selection:bg-emerald-500/30` → `selection:bg-green-soft`. (`THEME.bg`/`THEME.textPrimary` already resolve light from Task 1.)

- [ ] **Step 3: Re-skin LoadingScreen**

In `src/components/ui/LoadingScreen.tsx`, apply the Migration Map to lines 43-72:
- `bg-[#1e293b]` → `bg-paper`
- `bg-emerald-600/10` (glow) → `bg-green-soft`
- `text-emerald-500`, `text-emerald-400` → `text-green`
- `text-white` heading → `text-ink`; add `font-display` to the `<h2>`
- `text-zinc-300`, `text-zinc-400` → `text-muted`
- `bg-slate-600` (track) → `bg-kraft`
- `from-emerald-600 to-emerald-400` (bar) → `from-green to-green-mid`
- retry button `bg-emerald-600 hover:bg-emerald-500` → `bg-green hover:bg-green-mid`

- [ ] **Step 4: Re-skin the ErrorBoundary crash screen**

In `src/App.tsx` (the `ErrorBoundary.render` fallback, ~lines 34-42), apply the Migration Map:
- `bg-[#1e293b] text-white` → `bg-paper text-ink`
- `text-rose-500` (icon) → `text-paprika-strong`
- heading: add `font-display`; accent `text-rose-600 not-italic` → `text-paprika`
- `text-zinc-300` → `text-muted`
- button `bg-white text-black` → `bg-green text-white`

- [ ] **Step 5: Toast**

In `src/components/ui/Toast.tsx`, find the single dark token (grep below) and apply the Migration Map.
Run: `grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|emerald-|rose-" src/components/ui/Toast.tsx`

- [ ] **Step 6: Typecheck + build**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit && npm run build`
Expected: typecheck clean, build succeeds.

- [ ] **Step 7: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/components/layout/Navbar.tsx frontend/src/components/layout/MainLayout.tsx frontend/src/components/ui/LoadingScreen.tsx frontend/src/App.tsx frontend/src/components/ui/Toast.tsx
git commit -m "feat(reskin): app shared chrome (navbar, layout, loading, error, toast) → Market Paper"
```

---

## Task 3: Dashboard

**Files:**
- Modify: `src/pages/Dashboard.tsx` (dark tokens at lines 101-263; see grep)

- [ ] **Step 1: Apply the Migration Map across the file**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|334155|emerald-|rose-|red-[0-9]|teal-|bg-white|text-black" src/pages/Dashboard.tsx`
Migrate every hit per the Map. Notable cases in this file:
- `<h1 ... text-white ...>` (line ~101) → add `font-display`, `text-white`→`text-ink`; accent `text-emerald-500 not-italic` (line ~102) → `text-paprika`.
- Primary CTA `bg-white text-black hover:bg-zinc-200` (line ~124) → `bg-green text-white hover:bg-green-mid`.
- Secondary buttons `bg-slate-600 text-zinc-300 ... border-slate-500` (line ~117) → `bg-kraft text-ink ... border-line`.
- Delete/destructive `bg-red-600 ... hover:bg-red-500` (line ~153) → `bg-paprika text-white hover:bg-paprika-strong`.
- Cost-callout gradient block (lines ~164-179): `from-emerald-600/10 to-teal-600/5 border-emerald-500/20` → `bg-green-soft border-green/40`; inner `text-emerald-400`/`text-emerald-500` → `text-green`; `text-white`/`text-zinc-*` per Map.
- Empty state (lines ~195-199) and plan cards (lines ~207-263): surfaces `slate-700*` → `card`, borders → `line`, hover `hover:bg-slate-700` → `hover:bg-kraft`, selected `border-emerald-500 bg-emerald-500/5` → `border-green bg-green-soft`.

- [ ] **Step 2: Verify no dark tokens remain**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|334155|emerald-|rose-|red-[0-9]|teal-" src/pages/Dashboard.tsx`
Expected: no output.

- [ ] **Step 3: Typecheck**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(reskin): Dashboard → Market Paper"
```

---

## Task 4: CreatePlan

**Files:**
- Modify: `src/pages/CreatePlan.tsx` (dark tokens at lines 123-330; see grep)

- [ ] **Step 1: Apply the Migration Map across the file**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|334155|emerald-|rose-|red-[0-9]|bg-black|text-black|bg-white" src/pages/CreatePlan.tsx`
Migrate every hit per the Map. Notable cases:
- Hero `<h1>` (line ~123) → `font-display`, `text-white`→`text-ink`, accent dot (line ~124) → `text-paprika`.
- Step indicator (lines ~137-141): active `bg-emerald-600 text-white` → `bg-green text-white`; done `bg-emerald-500/20 text-emerald-400 border-emerald-500/30` → `bg-green-soft text-green border-green/40`; todo `bg-slate-700 text-zinc-400 border-slate-600` → `bg-kraft text-muted border-line`.
- Progress bar (lines ~149-151) → track `bg-slate-600`→`bg-kraft`, fill `from-emerald-600 to-emerald-400`→`from-green to-green-mid`.
- Inputs/textarea/selects (lines ~197, 208, 222): `bg-black/40`/`bg-slate-900` → `bg-paper`, `border-slate-600`→`border-line`, `text-white`→`text-ink`, `placeholder:text-zinc-400`→`placeholder:text-muted`, focus `ring-emerald-600/50`→`ring-green`.
- Numbered step badge `bg-emerald-600` (lines ~186, 262) → `bg-green`; `text-white` wrapper → `text-ink`.
- Meal-type cards (lines ~279-280): selected `bg-emerald-600/10 border-emerald-600 text-white shadow-emerald-500/10` → `bg-green-soft border-green text-ink shadow-green/10`; unselected `bg-slate-900 ... text-zinc-400` → `bg-paper ... text-muted`.
- Range sliders (lines ~295, 302): `bg-slate-600 accent-emerald-600` → `bg-kraft accent-green`.
- Error alert (line ~320): `bg-rose-500/10 border-rose-500/20 text-rose-400` → `bg-paprika-soft border-paprika/30 text-paprika-strong`.
- Nav buttons (line ~330): outline `border-slate-600 text-zinc-200 hover:text-white` → `border-line text-ink hover:bg-kraft`.

- [ ] **Step 2: Verify no dark tokens remain**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|334155|emerald-|rose-|red-[0-9]|bg-black" src/pages/CreatePlan.tsx`
Expected: no output.

- [ ] **Step 3: Typecheck**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/pages/CreatePlan.tsx
git commit -m "feat(reskin): CreatePlan → Market Paper"
```

---

## Task 5: PlanView

**Files:**
- Modify: `src/pages/PlanView.tsx` (dark tokens at lines 98-278; see grep)

- [ ] **Step 1: Apply the Migration Map across the file**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|334155|emerald-|rose-|bg-black|bg-white|text-black" src/pages/PlanView.tsx`
Migrate every hit per the Map. Notable cases:
- Two error/not-found screens (lines ~98-120): `bg-[#1e293b] text-white` → `bg-paper text-ink`; `bg-rose-500/10 text-rose-500 border-rose-500/20` → `bg-paprika-soft text-paprika-strong border-paprika/30`; accent dot `text-rose-600` → `text-paprika`; `text-zinc-*` → `text-muted`; CTA `bg-white text-black` → `bg-green text-white`; headings add `font-display`.
- Hero `<h1>` (line ~138) → `font-display`, `text-white`→`text-ink`, accent `text-emerald-500`→`text-paprika`.
- Meta chips (line ~145) `bg-slate-700 border-slate-600 text-zinc-300` → `bg-card border-line text-muted`; icon `text-emerald-500`→`text-green`.
- Export button (line ~154) `bg-white text-black ... border-zinc-300` → `bg-green text-white ... border-green-mid`.
- Goal/brief block (lines ~162-173) `bg-slate-800/60 border-slate-700` → `bg-card border-line`; `text-emerald-400`→`text-green`; restriction label `text-rose-400`→`text-paprika-strong`.
- Stat cards (lines ~204-210) `bg-slate-700/50 border-slate-600` → `bg-card border-line`; protein stat color `text-rose-400`→`text-paprika-strong`; cooked `text-emerald-400`→`text-green`.
- Day rail + meal cards (lines ~221-278): timeline gradient `from-emerald-600/50 via-zinc-800`→`from-green/50 via-line`; day badge `bg-white text-black`→`bg-green text-white`; `<h2>` add `font-display`, `text-white`→`text-ink`; image overlay `from-[#334155] via-[#334155]/60`→`from-paper via-paper/60`; meal label pill `bg-emerald-600 text-white`→`bg-green text-white`; cooked toggles per green/paprika Map; meal `<h3>` group-hover `group-hover/meal:text-emerald-400`→`group-hover/meal:text-green`, cooked `text-zinc-300`→`text-muted`, uncooked `text-white`→`text-ink`; description `text-zinc-300`→`text-muted`.

- [ ] **Step 2: Verify no dark tokens remain**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|334155|emerald-|rose-|bg-black" src/pages/PlanView.tsx`
Expected: no output.

- [ ] **Step 3: Typecheck**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/pages/PlanView.tsx
git commit -m "feat(reskin): PlanView → Market Paper"
```

---

## Task 6: RecipePage

**Files:**
- Modify: `src/pages/RecipePage.tsx` (dark tokens at lines 75-221; see grep)

- [ ] **Step 1: Apply the Migration Map across the file**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|emerald-|rose-|bg-white|text-black" src/pages/RecipePage.tsx`
Migrate every hit per the Map. Notable cases:
- Loading + not-found blocks (lines ~75-92): `bg-emerald-600/10 border-emerald-500/20`→`bg-green-soft border-green/40`; `text-emerald-500`→`text-green`; `text-white` headings → `text-ink` + `font-display`; `text-zinc-400`→`text-muted`; CTA `bg-white text-black`→`bg-green text-white`.
- Back link (line ~105) `text-zinc-300 hover:text-white` → `text-muted hover:text-ink`.
- Hero `<h1>` (line ~125) → `font-display`, `text-white`→`text-ink`, accent dot `text-emerald-500`→`text-paprika`.
- Meta chips (lines ~134-145) `bg-slate-700 border-slate-600 text-zinc-300` → `bg-card border-line text-muted`; icons `text-emerald-500`→`text-green`.
- Source link (lines ~151-157) `text-zinc-400`→`text-muted`; `text-emerald-400 hover:text-emerald-300`→`text-green hover:text-green-mid`.
- Deals box (lines ~169-175): `bg-emerald-50`→`bg-green-soft`; `text-emerald-800`→`text-green`; `text-emerald-700`→`text-green`. (Already light-ish — normalize to tokens.)
- Steps (lines ~194-210): heading `text-white`→`text-ink`+`font-display`; step number chip `bg-emerald-600/10 border-emerald-500/10 text-emerald-400`→`bg-green-soft border-green/40 text-green`; `text-zinc-300`→`text-muted`.
- Nutrition (lines ~216-221): `text-white`→`text-ink`; `text-zinc-400`→`text-muted`; `text-zinc-200`→`text-ink`.

- [ ] **Step 2: Verify no dark tokens remain**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|emerald-|rose-|bg-white" src/pages/RecipePage.tsx`
Expected: no output. Note: this file had a light `emerald-50`/`emerald-700/800` deals box — confirm those became `green-soft`/`text-green` too (no `emerald-` token of any shade should remain).

- [ ] **Step 3: Typecheck**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/pages/RecipePage.tsx
git commit -m "feat(reskin): RecipePage → Market Paper"
```

---

## Task 7: Onboarding (quiz flow)

**Files:**
- Modify: `src/pages/Onboarding.tsx` (dark tokens at lines 133-380; see grep)

- [ ] **Step 1: Apply the Migration Map across the file**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|emerald-|rose-|bg-white|text-black|bg-black" src/pages/Onboarding.tsx`
Migrate every hit per the Map. Notable cases:
- Intro screen (lines ~133-160): badge `bg-emerald-600/10 border-emerald-500/20`→`bg-green-soft border-green/40`; `text-emerald-400`→`text-green`; `<h1>` add `font-display`, `text-white`→`text-ink`, accent `text-emerald-500`→`text-paprika`; CTA `bg-white text-black`→`bg-green text-white`; `text-zinc-300`→`text-muted`.
- Header + skip (lines ~170-173): `<h1>` `font-display`, `text-white`→`text-ink`, accent→`text-paprika`; skip `text-zinc-300`→`text-muted`.
- Step indicator + progress bar (lines ~187-202): same mapping as CreatePlan Step 1 (active `bg-green text-white`, done `bg-green-soft text-green border-green/40`, todo `bg-kraft text-muted border-line`; bar track `bg-kraft`, fill `from-green to-green-mid`).
- Choice cards — goals/styles/allergies (lines ~213-249): selected `bg-emerald-600/10 border-emerald-600 text-white` / `bg-emerald-600/10 border-emerald-500 text-emerald-400` → `bg-green-soft border-green text-ink` / `bg-green-soft border-green text-green`; unselected `bg-slate-900 border-* text-zinc-300` → `bg-paper border-line text-muted`.
- Household/budget/skill/time controls (lines ~264-325): labels `text-zinc-400`→`text-muted`; pills `bg-slate-900 text-zinc-400` → `bg-paper text-muted`, selected `bg-emerald-600 text-white border-emerald-500`→`bg-green text-white border-green`; budget value `text-emerald-500`→`text-green`; range `bg-slate-600 accent-emerald-600`→`bg-kraft accent-green`.
- Footer nav, desktop + mobile (lines ~339-358): outline `border-slate-600 text-zinc-200 hover:text-white`→`border-line text-ink hover:bg-kraft`; primary `bg-emerald-600 hover:bg-emerald-500 text-white`→`bg-green hover:bg-green-mid text-white`; sticky mobile bar `bg-[#1e293b]/95 border-slate-600`→`bg-paper/95 border-line`.
- Helper sub-components (lines ~370-380): step header `text-white`→`text-ink`, badge `bg-emerald-600`→`bg-green`; row divider `border-slate-600`→`border-line`; label `text-zinc-300`→`text-muted`.

- [ ] **Step 2: Verify no dark tokens remain**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|emerald-|rose-|bg-black" src/pages/Onboarding.tsx`
Expected: no output.

- [ ] **Step 3: Typecheck**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/pages/Onboarding.tsx
git commit -m "feat(reskin): Onboarding quiz → Market Paper"
```

---

## Task 8: Stragglers — BillingSuccess + remaining components

**Files:**
- Modify: `src/pages/BillingSuccess.tsx` (lines 78-150)
- Modify: `src/components/ProtocolUpload.tsx`
- Modify: `src/components/ui/StatusTracker.tsx`
- Modify: `src/components/ui/Skeleton.tsx`
- Modify: `src/components/recipe/PortionStepper.tsx`
- Modify: `src/components/recipe/RecipeIngredients.tsx`

- [ ] **Step 1: BillingSuccess**

Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|emerald-|rose-|bg-white|text-black" src/pages/BillingSuccess.tsx`
Apply the Map. Notable: page `bg-[#1e293b] text-white`→`bg-paper text-ink`; `text-emerald-400`→`text-green` + accent dots→`text-paprika`; primary `bg-white text-black hover:bg-zinc-100`→`bg-green text-white hover:bg-green-mid`; outline `border-white/20 text-white hover:bg-white/5`→`border-line text-ink hover:bg-kraft`; `text-zinc-300/400/500`→`text-muted`; `<h*>` add `font-display`.

- [ ] **Step 2: Remaining components**

For each file below, grep and apply the Map:
Run: `cd /opt/llmDietPlanner/frontend && grep -nE "slate-[0-9]|zinc-[0-9]|1e293b|emerald-|rose-|THEME\." src/components/ProtocolUpload.tsx src/components/ui/StatusTracker.tsx src/components/ui/Skeleton.tsx src/components/recipe/PortionStepper.tsx src/components/recipe/RecipeIngredients.tsx`
- `Skeleton.tsx`: shimmer base `bg-slate-*` → `bg-kraft` (the loading placeholder should read as light).
- `StatusTracker.tsx`, `PortionStepper.tsx`, `RecipeIngredients.tsx`, `ProtocolUpload.tsx`: standard Map application. Any `THEME.*` reference already resolves light from Task 1 — leave it.

- [ ] **Step 3: Verify no dark tokens remain anywhere in the app surface**

Run:
```bash
cd /opt/llmDietPlanner/frontend && grep -rnE "slate-[0-9]|zinc-[0-9]|1e293b|334155|emerald-|bg-black/[0-9]" src/pages/BillingSuccess.tsx src/components/ProtocolUpload.tsx src/components/ui/StatusTracker.tsx src/components/ui/Skeleton.tsx src/components/recipe/PortionStepper.tsx src/components/recipe/RecipeIngredients.tsx
```
Expected: no output.

- [ ] **Step 4: Typecheck**

Run: `cd /opt/llmDietPlanner/frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
cd /opt/llmDietPlanner && git add frontend/src/pages/BillingSuccess.tsx frontend/src/components/ProtocolUpload.tsx frontend/src/components/ui/StatusTracker.tsx frontend/src/components/ui/Skeleton.tsx frontend/src/components/recipe/PortionStepper.tsx frontend/src/components/recipe/RecipeIngredients.tsx
git commit -m "feat(reskin): BillingSuccess + remaining app components → Market Paper"
```

---

## Task 9: Build, CSS-token audit, and full-app Playwright verification

**Files:** none modified (verification only). Requires the user-provided dev test-account credentials (see spec); set `E2E_EMAIL` / `E2E_PASSWORD` env vars from them.

- [ ] **Step 1: Full repo grep for any remaining dark token in app source**

Run:
```bash
cd /opt/llmDietPlanner/frontend && grep -rnE "1e293b|334155|slate-[0-9]|zinc-[0-9]|emerald-[0-9]" src/pages src/components src/lib
```
Expected: no output. (Public pages were already light; if any hit appears in a public page, it predates this work — note but do not change without checking it's an app surface.)

- [ ] **Step 2: Production build**

Run: `cd /opt/llmDietPlanner/frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Confirm the light tokens actually made it into the built CSS**

Tailwind silently drops unknown classes, so a green build can hide a broken theme. Confirm the brand rgb values are present and the old dark slate hex is gone from the app bundle:
Tailwind emits the hex for solid colors (and `rgb(.. / <alpha>)` for opacity variants), so grep the hex case-insensitively:
```bash
cd /opt/llmDietPlanner/frontend
echo "paper  #F7F3EC:"; grep -roiE "#f7f3ec|247 243 236" dist/assets/*.css | wc -l
echo "green  #2E6B43:"; grep -roiE "#2e6b43|46 107 67"   dist/assets/*.css | wc -l
echo "slate  #1e293b:"; grep -roiE "#1e293b|30 41 59"    dist/assets/*.css | wc -l
```
Expected: paper + green counts > 0 (the light tokens compiled in). The slate count reflects any remaining dark usage; investigate if non-zero in an app context.

- [ ] **Step 4: Start the app and log in with Playwright**

Start the dev server (background): `cd /opt/llmDietPlanner/frontend && npm run dev` (note the local URL, typically http://localhost:5173).
Then drive Playwright: navigate to `/login`, fill the test credentials, submit, wait for redirect.

- [ ] **Step 5: Screenshot every authenticated page at desktop + mobile**

Using Playwright (desktop 1440px and mobile 390px viewports), capture and save under `ux-review/`:
- `/` (Dashboard) → `reskin-app-dashboard-desktop.png`, `-mobile.png`
- `/create` (CreatePlan) → `reskin-app-create-*.png`
- a real plan `/plan/:id` (PlanView) → `reskin-app-plan-*.png`
- a recipe `/plan/:id/recipe/:mealId` (RecipePage) → `reskin-app-recipe-*.png`
- `/onboarding` (force-navigate; if it redirects because onboarding is complete, temporarily hit it via a fresh test account or note the limitation) → `reskin-app-onboarding-*.png`

For each screenshot confirm: (a) no dark slate background remains, (b) brand reads consistent with the public site (paper bg, ink text, green/paprika accents, `vařto.` navbar), (c) text is legible / not washed out on paper, (d) keyboard focus ring is the green ring (Tab to a control and screenshot one focus state).

- [ ] **Step 6: Commit verification artifacts (optional, untracked)**

`ux-review/` is a git-untracked review folder; leave it untracked. Summarize findings for the user with the screenshot paths.

---

## Task 10: Open the PR

- [ ] **Step 1: Push and open PR**

```bash
cd /opt/llmDietPlanner && git push -u origin feat/auth-app-reskin
gh pr create --base develop --head feat/auth-app-reskin \
  --title "feat(reskin): auth app → Market Paper (light, brand Vařto)" \
  --body "Carries the light Market Paper identity into the logged-in product (Dashboard, CreatePlan, PlanView, RecipePage, Onboarding, BillingSuccess + shared chrome). Considered recolor per docs/superpowers/specs/2026-06-26-auth-app-reskin-design.md. Verified locally via build + CSS-token audit + Playwright screenshots (ux-review/reskin-app-*.png). Ends the dark/light two-identity split."
```

- [ ] **Step 2: Report PR URL + screenshot summary to the user.**

---

## Notes on verification gaps / risks

- **Onboarding screenshot** needs an account whose onboarding is *not* complete (the route redirects to Dashboard once done). If the provided test account has completed onboarding, request a second fresh account or verify Onboarding by temporarily bypassing the redirect locally (do not commit the bypass).
- **Dense data legibility** is the main visual risk — watch PlanView meal cards and Dashboard plan cards for washed-out text on paper; `card` white surfaces over `paper` should provide enough separation, but flag any low-contrast block in Step 5.
- **Accent dots**: the app's signature `word.` accent dots move to `paprika` to match the `vařto.` wordmark — confirm this reads intentional, not like an error color, in the screenshots.
