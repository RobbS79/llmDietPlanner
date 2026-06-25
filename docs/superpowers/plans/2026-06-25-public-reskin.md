# Public Re-skin ("Market Paper", brand Vařto) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the public pages from the dark-slate/emerald AI default to the warm "Market Paper" identity (brand **Vařto**), with a grocery-receipt signature, while preserving every P0/P1 ergonomics + WCAG AA gain.

**Architecture:** Introduce a centralized semantic token system (Tailwind config + `THEME`) and a scoped font stack, then migrate the public pages from hardcoded `#1e293b`/`emerald-*`/`slate-*` values to those tokens. Build one reusable `Receipt` component as the signature. Auth-app components are untouched (out of scope) — do not change the global `font-sans` or the existing `background`/`surface` tokens they rely on.

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind CSS, react-router, Playwright (MCP) for visual verification. Fonts via Google Fonts (Bricolage Grotesque, Hanken Grotesk, Space Mono).

**Verification model (read this — not literal TDD):** A re-skin has no meaningful unit tests. Each task is verified by: (a) `npx tsc --noEmit` = 0 errors, (b) `npm run build` passes, (c) `npx vitest run` stays green (17 tests), and (d) a Playwright screenshot of the affected page at 1440px + 390px saved to `ux-review/`, plus a scripted contrast/tap-target check where text/bg or interactive sizing changed. Commit after each task.

**Reference spec:** `docs/superpowers/specs/2026-06-25-public-reskin-design.md`

---

## File structure

**Create:**
- `frontend/src/components/ui/Receipt.tsx` — the receipt/price-tag signature (props-driven, reusable).

**Modify (foundation):**
- `frontend/tailwind.config.js` — add semantic colors + `display`/`body`/`price` font families (leave `sans`, `background`, `surface` intact).
- `frontend/src/lib/theme.ts` — point `THEME` at the new tokens.
- `frontend/index.html` — add the Google Fonts `<link>`.
- `frontend/src/index.css` — recolor the global `:focus-visible` ring for the light bg; no new always-on motion.

**Modify (public pages — apply token map + structural changes):**
- `frontend/src/components/layout/PublicHeader.tsx`
- `frontend/src/pages/Landing.tsx`
- `frontend/src/pages/RecipeIndexPage.tsx`
- `frontend/src/pages/RecipePage.tsx` (recipe detail) — public view path only
- `frontend/src/pages/Pricing.tsx`
- `frontend/src/pages/About.tsx`
- `frontend/src/components/recipe/RecipeIngredients.tsx` (already partly touched in P1) and other components rendered only inside the public recipe/landing pages, as encountered.
- `frontend/index.html` / SSR `<title>`/meta strings + `llm_diet_planner_project/views.py` SSR meta — drop "AI", use "Vařto" on public canonical/OG strings.

**Do NOT modify:** `frontend/src/components/layout/Navbar.tsx`, Dashboard/CreatePlan/PlanView and other auth-only components; `background`/`surface` Tailwind tokens; global `font-sans`.

---

## Token map (used by every page task)

Apply these replacements on public pages. This is the mechanical core of each page task; the structural notes per page are layered on top.

| Old (hardcoded) | New (token) | Notes |
|---|---|---|
| `bg-[#1e293b]` (page bg) | `bg-paper` | page background |
| `text-white` / `text-zinc-100/200` (primary) | `text-ink` | primary text |
| `text-zinc-300/400` (secondary) | `text-muted` | secondary text |
| `bg-slate-700/50`, `bg-[#334155]`, `glass-card` | `bg-card border border-line` or `bg-kraft`; for `<Card>` pass `variant="paper"` | surfaces |
| `border-slate-600/700` | `border-line` | dividers/borders |
| `bg-emerald-600`/`bg-emerald-500` + `text-white` (CTA) | `bg-green hover:bg-green-mid text-white` | primary action |
| `text-emerald-500/400` (accent) | `text-green` (brand) or `text-paprika` (prices/deals) | choose by role |
| emerald blur orbs / `shadow-glow-*` / neon | remove or `bg-green-soft` flat | no glow on light |
| `uppercase tracking-widest` on body-meaning text | sentence case, drop tracking | keep uppercase only on tiny eyebrows |
| price/quantity numerals | `font-price` (mono) | signature |
| display headings | `font-display` | Bricolage |

---

## Task 1: Design tokens + fonts + focus ring

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/components/ui/Card.tsx`
- Modify: `frontend/index.html`
- Modify: `frontend/src/index.css`
- Leave UNCHANGED: `frontend/src/lib/theme.ts` (the auth app's `MainLayout` and `Card` default depend on it — see Step 2)

- [ ] **Step 1: Add tokens + font families to Tailwind**

In `frontend/tailwind.config.js`, replace the `theme.extend` block with (keep `background`/`surface` for the auth app, add the rest):

```js
extend: {
  colors: {
    background: '#1e293b',   // auth app (unchanged)
    surface: '#334155',      // auth app (unchanged)
    paper: '#F7F3EC',
    card: '#FFFFFF',
    kraft: '#EFE7D8',
    line: '#E4DAC8',
    ink: '#241E1A',
    muted: '#5E564C',        // darkened from spec #6B6258 for AA safety on paper
    green: { DEFAULT: '#2E6B43', mid: '#3F8557', soft: '#E7F0E8' },
    paprika: { DEFAULT: '#DB5026', strong: '#B23E1C', soft: '#FBE6DC' },
  },
  fontFamily: {
    display: ['"Bricolage Grotesque"', 'system-ui', 'sans-serif'],
    body: ['"Hanken Grotesk"', 'system-ui', 'sans-serif'],
    price: ['"Space Mono"', 'ui-monospace', 'monospace'],
  },
  borderRadius: { '3xl': '1.5rem', '4xl': '2rem', '5xl': '2.5rem' },
  animation: { 'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite' },
}
```

Note: `font-sans` is intentionally NOT overridden, so the auth app keeps its current font. Public pages opt in via `font-body`.

- [ ] **Step 2: Give Card a light `variant` (do NOT touch THEME)**

`THEME` (lib/theme.ts) is shared: `MainLayout` (auth) and `Card` (used by Dashboard, PlanView, CreatePlan, Onboarding — all out of scope) depend on its dark values. Leave `theme.ts` exactly as-is. Instead, add an opt-in light variant to `Card` so public pages get the Market Paper surface without changing the auth app. Replace `frontend/src/components/ui/Card.tsx` with:

```tsx
import { ReactNode, HTMLAttributes, KeyboardEvent, MouseEvent } from 'react';
import { Link } from 'react-router-dom';
import { THEME } from '@/lib/theme';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  className?: string;
  /** When set, the card renders as a real navigational link (<a href>). */
  to?: string;
  /** 'app' (default) = dark auth-app surface from THEME; 'paper' = light public surface. */
  variant?: 'app' | 'paper';
}

export const Card = ({ children, className = "", onClick, to, variant = 'app', ...props }: CardProps) => {
  const isInteractive = !!onClick || !!to;
  const surface = variant === 'paper' ? 'bg-card border-line' : `${THEME.surface} ${THEME.border}`;
  const base = `${surface} border rounded-2xl shadow-lg transition-all`;
  const focusRing = isInteractive
    ? 'focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:outline-none'
    : '';

  if (to) {
    return (
      <Link to={to} className={`block ${base} ${focusRing} ${className}`} onClick={onClick as ((e: MouseEvent) => void) | undefined}>
        {children}
      </Link>
    );
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (onClick && (e.key === 'Enter' || e.key === ' ')) {
      e.preventDefault();
      onClick(e as any);
    }
  };

  return (
    <div className={`${base} ${focusRing} ${className}`} onClick={onClick}
      {...(onClick ? { role: 'button', tabIndex: 0, onKeyDown: handleKeyDown } : {})} {...props}>
      {children}
    </div>
  );
};
```

(Public pages will pass `variant="paper"`; auth pages keep the default and stay dark.)

- [ ] **Step 3: Load fonts**

In `frontend/index.html`, inside `<head>` add:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
```

- [ ] **Step 4: Recolor the global focus ring for the light bg**

In `frontend/src/index.css`, change the `:focus-visible` rule added in P1 from emerald-400 to paprika (visible on both the new cream pages and the dark auth app):

```css
:focus-visible {
  outline: 2px solid #DB5026; /* paprika — visible on light and dark */
  outline-offset: 2px;
  border-radius: 4px;
}
```

- [ ] **Step 5: Verify build + types + tests**

Run: `cd frontend && npx tsc --noEmit && npm run build && npx vitest run`
Expected: tsc 0 errors; build succeeds; 17 tests pass. (No visual change yet — pages still use old hardcoded classes; this only adds tokens.)

- [ ] **Step 6: Sanity-check the auth app didn't shift**

`THEME` is unchanged and `Card`'s default variant stays `'app'`, so Dashboard/PlanView/CreatePlan/Onboarding and `MainLayout` render exactly as before. Confirm `npm run build` is clean; no visual change anywhere yet (public pages still use old classes until later tasks add `variant="paper"` + token classes).

- [ ] **Step 7: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/lib/theme.ts frontend/index.html frontend/src/index.css
git commit -m "feat(reskin): add Market Paper design tokens, fonts, focus ring"
```

---

## Task 2: Receipt signature component

**Files:**
- Create: `frontend/src/components/ui/Receipt.tsx`

- [ ] **Step 1: Implement the component**

Create `frontend/src/components/ui/Receipt.tsx`:

```tsx
interface ReceiptItem {
  day?: string;        // e.g. "PO"
  name: string;
  price: string;       // formatted, e.g. "72"
  deal?: boolean;      // shows "ve slevě" chip
}
interface ReceiptProps {
  title: string;        // e.g. "Váš týden"
  subtitle?: string;    // e.g. "3 jídla denně · 7 dní"
  source?: string;      // e.g. "Rohlík.cz"
  items: ReceiptItem[];
  totalLabel: string;   // e.g. "Týdenní nákup"
  total: string;        // e.g. "1 247"
  currency?: string;    // default "Kč"
}

export const Receipt = ({ title, subtitle, source, items, totalLabel, total, currency = 'Kč' }: ReceiptProps) => (
  <div className="relative bg-card border border-line rounded-2xl p-7 shadow-[0_26px_50px_-28px_rgba(36,30,26,0.35)]">
    <div className="absolute left-0 right-0 -top-px h-2 rounded-t-2xl"
         style={{ background: 'repeating-linear-gradient(90deg,#DB5026 0 14px,transparent 14px 22px)' }} />
    <div className="flex items-end justify-between border-b-2 border-dashed border-line pb-3.5 mb-1.5">
      <div>
        <div className="font-display font-bold text-lg text-ink">{title}</div>
        {subtitle && <div className="text-[11px] uppercase tracking-[0.12em] text-muted mt-0.5">{subtitle}</div>}
      </div>
      {source && <div className="text-xs font-bold text-green">{source}</div>}
    </div>
    {items.map((it, i) => (
      <div key={i} className="flex items-baseline gap-2 py-2.5 text-[15px]">
        {it.day && <span className="font-price text-[11px] text-muted w-8">{it.day}</span>}
        <span className="font-semibold text-ink">{it.name}</span>
        {it.deal && <span className="bg-paprika-soft text-paprika-strong font-bold text-[11px] px-1.5 py-0.5 rounded-md">ve slevě</span>}
        <span className="flex-1 border-b border-dotted border-[#cdbfa6] translate-y-[-4px]" />
        <span className="font-price font-bold text-[15px] text-ink">{it.price}&nbsp;{currency}</span>
      </div>
    ))}
    <div className="flex items-center justify-between border-t-2 border-dashed border-line mt-2 pt-4">
      <span className="font-bold text-sm uppercase tracking-[0.1em] text-muted">{totalLabel}</span>
      <span className="font-price font-bold text-3xl text-ink">{total}<small className="text-[15px] text-muted">&nbsp;{currency}</small></span>
    </div>
  </div>
);
```

- [ ] **Step 2: Verify it typechecks/builds**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: 0 errors, build succeeds. (Not yet rendered anywhere; used in Task 4.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ui/Receipt.tsx
git commit -m "feat(reskin): add Receipt signature component"
```

---

## Task 3: PublicHeader re-skin (brand Vařto)

**Files:**
- Modify: `frontend/src/components/layout/PublicHeader.tsx`

- [ ] **Step 1: Re-skin the header**

Apply the token map and the new wordmark. Specifically:
- Wordmark: replace the `Zap` icon + "DietPlanner." with a text wordmark: `<span className="font-display font-extrabold text-2xl tracking-tight text-ink lowercase">vařto<span className="text-paprika">.</span></span>`. Remove the `Zap` import if now unused.
- Desktop + mobile nav links: `text-ink/80 hover:text-ink font-body font-semibold` (drop `uppercase tracking-widest`, use sentence case "Recepty", "Ceník", "Přihlásit se").
- Primary CTA "Vytvořit jídelníček": `bg-green hover:bg-green-mid text-white rounded-xl px-5 py-3 font-body font-bold` (white-on-green passes AA). Keep the `to="/login"` targets.
- Mobile drawer container: `bg-card border-y border-line` (was `bg-slate-900`); drawer links `text-ink`; full-width CTA `bg-green text-white`.
- Keep the hamburger (44px tap target from P1) and `aria-label`/`aria-expanded`.

- [ ] **Step 2: Verify build + visual (mobile is the risk)**

Run: `cd frontend && npx tsc --noEmit && npm run build`. Then via the dev server, Playwright at 390px: confirm the header shows `vařto.` + hamburger, drawer opens with all links + green CTA, nothing clipped. Save `ux-review/reskin-header-mobile.png`.
Expected: clean light header, drawer works.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/layout/PublicHeader.tsx
git commit -m "feat(reskin): PublicHeader to Market Paper + Vařto wordmark"
```

---

## Task 4: Landing re-skin (hero + receipt + bands)

**Files:**
- Modify: `frontend/src/pages/Landing.tsx`

- [ ] **Step 1: Apply token map across the page**

Replace the root `bg-[#1e293b] text-white` with `bg-paper text-ink font-body`. Apply the token map to every section (cards → `bg-card border-line`, emerald CTAs → green, secondary text → `text-muted`). Remove the emerald blur orbs (`bg-emerald-600/[0.06] blur-...`) — on light they read as smudges; delete those decorative divs.

- [ ] **Step 2: Rebuild the hero with the Receipt signature**

Make the hero a two-column grid (`grid lg:grid-cols-2 gap-14 items-center`, stacks on mobile). Left: eyebrow pill (`bg-green-soft text-green`), `font-display` headline „Víte, co budete jíst i **kolik to stojí.**" (accent span `text-paprika`), `text-muted` lead, primary green CTA + ghost button, fine print. Right: render `<Receipt .../>` with the existing `SAMPLE_PLAN` data mapped to `ReceiptItem[]` (use day codes PO/ÚT…, mark 1–2 items `deal`). Remove the old standalone stat row from the hero.

- [ ] **Step 3: Honest stat band**

Keep the three honest stats from P1 (`500+ / Reálné / <60s`) but move them into a `bg-kraft border-y border-line` band below the hero; values `font-display`, labels `text-muted`. (No "97 %".)

- [ ] **Step 4: Section rhythm + tagline**

Alternate section backgrounds `bg-paper` / `bg-kraft` (or `bg-green-soft`) so the page has visible structure. Add the tagline „Jezte chytře, plaťte míň." near the wordmark/footer. Footer: `bg-ink text-paper` (or deep green) as the page's contrast anchor; footer links `text-paper/80`.

- [ ] **Step 5: Verify build + visual + contrast**

Run: `cd frontend && npx tsc --noEmit && npm run build && npx vitest run`. Playwright at 1440px + 390px → `ux-review/reskin-landing-{desktop,mobile}.png`. Run a contrast check (scripted via `browser_evaluate`) on: lead/muted text on paper, white on green CTA, paprika accents — all ≥ AA. Confirm mobile stacks the receipt below the copy.
Expected: warm landing, receipt hero, AA holds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Landing.tsx
git commit -m "feat(reskin): Landing to Market Paper with receipt hero"
```

---

## Task 5: Recepty index re-skin

**Files:**
- Modify: `frontend/src/pages/RecipeIndexPage.tsx`

- [ ] **Step 1: Apply token map + recolor cards and skeleton**

Root → `bg-paper text-ink font-body`. Heading `font-display text-ink` with accent span `text-paprika` (drop italic/uppercase tic). Recipe cards (the `Card to=...` links from P1): `bg-card border-line hover:border-green/40`; title `font-display text-ink`; description `text-muted`; meta in `font-price`/`text-muted`; the deals chip → `bg-paprika-soft text-paprika-strong`. Recolor the skeleton placeholders from `bg-slate-*` to `bg-line/`-tinted on `bg-card`. Keep real-link + skeleton behavior and pagination.

- [ ] **Step 2: Verify build + visual**

Run: `cd frontend && npx tsc --noEmit && npm run build`. Playwright on `/recepty` (dev) 1440px + 390px → `ux-review/reskin-recepty-{desktop,mobile}.png`. Confirm cards are still real `<a href>` and skeleton renders light.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/RecipeIndexPage.tsx
git commit -m "feat(reskin): Recepty index to Market Paper"
```

---

## Task 6: Recipe detail re-skin

**Files:**
- Modify: `frontend/src/pages/PublicRecipePage.tsx` (THIS is the public `/recepty/:id/:slug` route — NOT `RecipePage.tsx`, which is the auth-app recipe view and is out of scope)
- Modify: `frontend/src/components/recipe/RecipeIngredients.tsx` and sibling recipe components as encountered

- [ ] **Step 1: Identify public-only recipe components**

`PublicRecipePage.tsx` is the public route; `RecipePage.tsx` is the auth-app view (leave it dark). Recipe sub-components may be shared between them. Before editing shared recipe sub-components, grep their imports: if a component is used ONLY by public recipe/landing pages, re-skin it; if it's shared with the auth app, gate the palette by the page wrapper (wrap public usage in `bg-paper text-ink font-body`) rather than hardcoding light colors into the shared component. Document which components you changed in the commit body.

- [ ] **Step 2: Apply token map**

Root/public wrapper → `bg-paper text-ink font-body`. Photo hero kept. Title `font-display`; ingredients/postup in two columns on `bg-card`/`bg-paper`; nutrition values + any cost in `font-price`; deals chip `bg-paprika-soft text-paprika-strong`. Keep the `(volitelné)` text at `text-muted` (P1) — re-verify it reads on the new bg.

- [ ] **Step 3: Verify build + visual**

Run: `cd frontend && npx tsc --noEmit && npm run build`. Playwright on a real recipe (e.g. `/recepty/39/kureci-parmigiana/`) 1440px + 390px → `ux-review/reskin-recipe-{desktop,mobile}.png`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/RecipePage.tsx frontend/src/components/recipe/
git commit -m "feat(reskin): recipe detail to Market Paper"
```

---

## Task 7: Pricing re-skin

**Files:**
- Modify: `frontend/src/pages/Pricing.tsx`

- [ ] **Step 1: Apply token map**

Root → `bg-paper text-ink font-body`. Three tier cards → `bg-card border-line`; recommended tier accented with `border-green` + `bg-green-soft` header and the „Doporučeno" chip `bg-green text-white` (or `bg-paprika-strong text-white`). Price numbers `font-price text-ink`. FAQ accordion on `bg-card`/`bg-kraft`. Keep the honest FAQ copy from P1. CTA buttons → green.

- [ ] **Step 2: Verify build + visual**

Run: `cd frontend && npx tsc --noEmit && npm run build`. Playwright `/pricing` 1440px + 390px → `ux-review/reskin-pricing-{desktop,mobile}.png`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Pricing.tsx
git commit -m "feat(reskin): Pricing to Market Paper"
```

---

## Task 8: About re-skin

**Files:**
- Modify: `frontend/src/pages/About.tsx`

- [ ] **Step 1: Apply token map**

Root → `bg-paper text-ink font-body`. Headline `font-display`; founder block re-skinned (`bg-card`/`bg-green-soft` avatar block); back-link `text-muted hover:text-green`. Uses the shared `PublicHeader` (already done).

- [ ] **Step 2: Verify build + visual**

Run: `cd frontend && npx tsc --noEmit && npm run build`. Playwright `/o-nas` 1440px + 390px → `ux-review/reskin-about-{desktop,mobile}.png`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/About.tsx
git commit -m "feat(reskin): About to Market Paper"
```

---

## Task 9: Login re-skin

**Files:**
- Modify: the login page component (find via `frontend/src/pages` route `/login`; likely `Login.tsx`)

- [ ] **Step 1: Confirm the file**

Run: `cd frontend && grep -rl "Přihlášení\|Registrace\|forgot-password" src/pages`
Expected: the login page file path.

- [ ] **Step 2: Apply token map**

Root → `bg-paper text-ink font-body`. Auth card → `bg-card border-line`; `vařto.` wordmark; tabs Přihlášení/Registrace with active = `bg-green text-white`; inputs keep affordances (icons, show-password) but recolor to light (`bg-paper`/`border-line`, focus ring via global rule); primary button green; Google button on `bg-card border-line`; "Přidejte se k 500+…" in `text-muted`.

- [ ] **Step 3: Verify build + visual**

Run: `cd frontend && npx tsc --noEmit && npm run build`. Playwright `/login` 1440px + 390px → `ux-review/reskin-login-{desktop,mobile}.png`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat(reskin): Login to Market Paper"
```

---

## Task 10: Brand strings (drop "AI", use Vařto on public meta)

**Files:**
- Modify: `frontend/index.html` (`<title>`/meta defaults)
- Modify: `llm_diet_planner_project/views.py` (SSR title/description/canonical strings for public routes)

- [ ] **Step 1: Update public-facing titles/meta**

Grep for the brand string: `grep -rn "DietPlanner AI\|DietPlanner" frontend/index.html llm_diet_planner_project/views.py`. Replace public-facing titles with the `Vařto` brand and the tagline, e.g. `Vařto — Jídelníček s reálnými cenami z obchodu`. Remove "AI". Leave the `eatalnicek.eu` domain/canonical URLs unchanged (only the brand text changes).

- [ ] **Step 2: Verify build + SSR**

Run: `cd frontend && npm run build && npm run build:ssr`. Confirm builds pass. Spot-check the prerendered `dist/index.html` `<title>`.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html llm_diet_planner_project/views.py
git commit -m "feat(reskin): brand strings to Vařto, drop AI on public meta"
```

---

## Task 11: Final accessibility + prod verification pass

**Files:** none (verification only); fixes go back into the relevant page file.

- [ ] **Step 1: Full contrast + tap-target + focus sweep**

After deploy (or on a local prod build preview), run the same scripted audit used in P1 across all public pages: every text/bg pair ≥ AA, interactive boxes ≥44px at 390px, `:focus-visible` ring visible on the light bg, reduced-motion still respected, images have alt. Fix any regressions in the offending page file and re-commit.

- [ ] **Step 2: Prod Playwright gallery**

Per the standing rule, verify on **prod** after deploy: capture all public pages desktop+mobile to `ux-review/` and confirm against the spec's success criteria (warm brand, hierarchy, receipt present, Vařto consistent, P0/P1 intact).

- [ ] **Step 3: Final commit (if fixes were needed)**

```bash
git add -A
git commit -m "fix(reskin): a11y/contrast corrections from final sweep"
```

---

## Rollout

Open PRs against `develop` (one cohesive PR, or token+header+Landing first as the proof then per-page — reviewer's choice). Promote `develop` → `prod` to deploy (push-to-prod). The prerendered routes (`/`, `/pricing`, `/login`) rebuild via `build:prod`. Verify on prod, then run the Task 11 sweep. Reversible via branch revert (presentation-only).
