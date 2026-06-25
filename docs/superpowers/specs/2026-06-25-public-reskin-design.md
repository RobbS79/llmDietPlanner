# Public Re-skin — "Market Paper" — Design Spec

Date: 2026-06-25
Status: approved direction + name; spec for review
Scope owner: Robert (ergonomics bar); visual direction delegated to Claude

## 1. Goal

Replace the AI-default dark-slate + emerald skin on the **public** surface with a
warm, food/grocery-grounded identity that fits the subject (a Czech meal planner
priced from real shops). Improve visual hierarchy and scannability without
regressing the ergonomics/accessibility wins already shipped (P0 mobile nav +
links + skeleton; P1 focus rings + contrast + honest copy).

## 2. Scope

**In scope (public pages only):** Landing (`/`), Recepty index (`/recepty`),
Recipe detail (`/recepty/:id/:slug`), Pricing (`/pricing`), About (`/o-nas`),
Login (`/login`), plus the shared `PublicHeader` and the public footer.

**Out of scope (deferred):**
- The logged-in app (Dashboard, Create plan, Plan view, Recipe page, `Navbar`).
  It keeps the current theme for now; re-skin can follow once this is proven.
- Domain change — stays `eatalnicek.eu`.
- Any backend/data changes. This is presentation only.

## 3. Brand

- **Name (wordmark):** **Vařto** (coined from *vařit*, "to cook"). Lowercase
  wordmark `vařto.` with a paprika-colored period. Replaces "DietPlanner"
  everywhere on public pages; also remove the stray "AI" from `<title>` tags.
- **Tagline / punchline:** „Jezte chytře, plaťte míň." (Eat smart, pay less.)
- **Domain:** unchanged (`eatalnicek.eu`); brand and domain intentionally differ.
- **Voice:** plain, warm, confident Czech. Active verbs, sentence case, no filler.
  (Claude authors/finalizes Czech copy and supplies EN glosses for review.)

## 4. Design tokens

### 4.1 Color (hex + role)
| Token | Hex | Role |
|-------|-----|------|
| `paper` | `#F7F3EC` | page background (warm off-white) |
| `card` | `#FFFFFF` | raised cards / receipt |
| `kraft` | `#EFE7D8` | tinted section bands, secondary surfaces |
| `line` | `#E4DAC8` | borders, dividers |
| `ink` | `#241E1A` | primary text (espresso, not pure black) |
| `muted` | `#6B6258` | secondary text |
| `green` | `#2E6B43` | **primary** — CTAs, brand; white text passes AA |
| `green-mid` | `#3F8557` | hover/secondary green |
| `green-soft` | `#E7F0E8` | green-tinted chips/bands |
| `paprika` | `#DB5026` | **accent** — prices, deal chips, receipt edge, headline accent word |
| `paprika-strong` | `#B23E1C` | paprika when it must carry white text (AA) |
| `paprika-soft` | `#FBE6DC` | deal-chip background |

**Contrast rule (must hold):** every text/background pair ≥ WCAG AA — 4.5:1 normal,
3:1 large (≥24px or ≥18.66px bold). Specifically: white text only on `green` or
`paprika-strong` (never plain `paprika`); `muted` on `paper` must be verified
≥4.5 (darken toward `#5E564C` if it falls short). Verify with a contrast pass at
implementation, same as the P1 audit.

### 4.2 Type
- **Display:** Bricolage Grotesque (700–800), tight tracking. Headlines, wordmark.
- **Body/UI:** Hanken Grotesk (400–700). Paragraphs, labels, buttons.
- **Numerals/prices (signature):** Space Mono (400/700). Prices, quantities,
  receipt figures, day codes.
- All three confirmed to render Czech diacritics (verified in mockup). Self-host
  or load via Google Fonts; pick one and apply consistently.
- Retire the current all-caps + wide letter-spacing tic; use sentence case and
  reserve uppercase for small eyebrow labels only.

### 4.3 Shape / depth
- Radii: cards `16px`, buttons `12px`, chips `6–8px`, pills `999px`.
- Shadows: soft, warm, low — e.g. `0 26px 50px -28px rgba(36,30,26,.35)` for the
  receipt; lighter for cards. No glow/neon shadows.

## 5. Signature — the receipt / price-tag system

The one memorable, subject-true element. Reused across pages:
- **Receipt card:** perforated paprika top edge (repeating-linear-gradient),
  dashed dividers, monospace prices with dotted leader lines, a bold mono total.
- **Hero uses it as the lead visual** (a sample week priced like a receipt) —
  replaces the templated stat row as the hero's thesis.
- **Deal chip:** paprika-soft pill, paprika-strong text, „ve slevě" — reuses the
  existing active-deals headline data.
- **Recipe cost** and **plan totals** render in the same mono/price-tag language.

## 6. Layout principles

- **Section rhythm:** alternate `paper` and `kraft`/`green-soft` bands so the page
  has visible structure and a clear primary action per screen (fixes the
  "everything same weight" flatness). No more monotone single-value scroll.
- **Hero = thesis:** the most characteristic thing (food + real price) shown, not
  claimed. Keep the strong headline „Víte, co budete jíst i kolik to stojí."
- Keep all responsive/ergonomic behavior from P0/P1 (hamburger, real links,
  skeletons, focus rings). Mobile: hero stacks (receipt below copy).

## 7. Per-page application

- **Landing:** new header (vařto. + green CTA); hero with receipt signature;
  honest stat band on `kraft`; existing sections re-skinned to the light palette
  with alternating bands; footer on `ink` or deep-green for contrast anchor.
- **Recepty index:** light grid; recipe cards become warm `card` tiles (photo +
  title + deal chip + meta); keep real-link + skeleton behavior; skeleton recolored.
- **Recipe detail:** light layout; photo hero; ingredients/postup in two columns
  on `paper`/`card`; nutrition + cost in the mono price-tag language; deals chip.
- **Pricing:** three tiers as light cards, recommended tier accented green; price
  figures in mono; FAQ accordion; keep the honest FAQ copy from P1.
- **About:** light layout, same header/footer, founder block re-skinned.
- **Login:** light auth card, green primary, brand wordmark, keep show-password +
  Google + tab affordances.

## 8. Implementation approach (token architecture)

Today `THEME` (lib/theme.ts) centralizes a few tokens but most components
hardcode `bg-[#1e293b]` / `bg-emerald-600` etc. The re-skin must fix that so it's
maintainable:
1. Define semantic tokens in `tailwind.config.js` (`paper`, `ink`, `green`,
   `paprika`, …) and update `THEME` to reference them.
2. Migrate hardcoded `#1e293b` / `slate-*` / `emerald-*` on public pages to the
   new tokens. Auth-app components keep their current values (out of scope) — do
   not break them.
3. Add the font stack (config + `index.css`), retire the uppercase/tracking tic.
4. Build the receipt as a small reusable component used by hero (and later
   recipe/plan cost).
Keep diffs page-scoped and verifiable; this is a sequence of bounded edits, not a
big-bang rewrite.

## 9. Accessibility (non-negotiable)

- Preserve P0/P1 gains: hamburger, real links, skeletons, global `:focus-visible`
  ring (recolor to a token that contrasts on the light bg), AA contrast, honest copy.
- Run a contrast pass on the final palette before shipping (same method as P1).
- Tap targets ≥44px; reduced-motion still respected (no new always-on motion).

## 10. Risks & rollout

- **Risk:** light palette + new fonts is a large visual change; SSR-prerendered
  pages (`/`, `/pricing`, `/login`) must rebuild (`build:prod` runs prerender).
- **Risk:** font loading cost — preconnect + `display=swap`, subset to Czech.
- **Rollout:** one PR for tokens+header+Landing (the proof), then per-page PRs, or
  one cohesive PR if review prefers. Verify each page on **prod** (Playwright,
  desktop+mobile) per standing rule, and save a PNG gallery to `ux-review/`.
- **Reversible:** presentation-only; revert is a branch revert.

## 11. Success criteria

1. Public pages read as a warm food/grocery brand, not a dark dashboard.
2. Clear per-page hierarchy and a single obvious primary action.
3. Receipt signature present on landing (and reused where cost appears).
4. Brand = `vařto.` + tagline, consistent; no "DietPlanner"/"AI" left on public pages.
5. All P0/P1 ergonomics + WCAG AA intact (verified on prod).
6. Token system centralized; no new hardcoded public-page colors.

## Non-goals
Logged-in app re-skin, domain change, backend/data changes, new features.
