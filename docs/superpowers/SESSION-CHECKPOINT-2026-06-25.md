# Session Checkpoint — 2026-06-25

A UX/design pass on the **public** site, end to end: audit → fixes → re-skin → rebrand, all shipped to prod (`eatalnicek.eu`) and verified with Playwright.

## Shipped to prod (in order)

1. **P0 ergonomics** (PR #25, `8ee9861`) — mobile hamburger header (shared `PublicHeader`), `/recepty` skeleton load, recipe cards as real `<a href>`, name-first recipe image categorization + `recategorize_recipe_images` backfill (ran in prod console, 7/22 fixed; e.g. Kuřecí parmigiana now chicken).
2. **P1 accessibility & honesty** (PR #26, `51031e1`) — global `:focus-visible` ring, WCAG-AA contrast fixes, dropped the unverifiable "97 %" claim.
3. **Public re-skin → "Market Paper" + brand "Vařto"** (PR #27 `c4078dc` + `77865cd`) — light warm palette (paper/ink/green/paprika), Bricolage/Hanken/Space Mono type, grocery-`Receipt` signature hero, section-band hierarchy. All 10 public pages + SSR fallback + prerendered titles. Brand "DietPlanner/AI" → **Vařto** (`vařto.`, tagline „Jezte chytře, plaťte míň."). Domain unchanged (`eatalnicek.eu`).

Specs/plans: `docs/superpowers/specs/2026-06-25-public-reskin-design.md`, `docs/superpowers/plans/2026-06-25-public-reskin.md`. Visual gallery: `ux-review/prod-*.png`.

## Verified on prod
- All public pages render Market Paper, mobile + desktop; brand consistent.
- WCAG AA across pages; keyboard focus visible; skip-link 6.36:1.
- Auth app provably untouched (still dark; `THEME` dark, components default `variant="app"`).
- All page `<title>`s = "— Vařto" (no DietPlanner/AI).

## Remaining / deferred
- **Brand leftovers (in progress this checkpoint):** password-reset email (`login_app/utils.py`), e2e smoke test wordmark assertion (`e2e/tests/smoke.spec.ts`), Django Site name (migration set "DietPlanner AI").
- **Auth app re-skin** — deliberately out of scope; still dark. Future task.
- Pre-existing pending item from before this session: eggs-rounding frontend fix (portion gate).

## Process lessons (saved to memory)
- Tailwind silently drops unknown classes → a green build can hide a broken theme; grep the built CSS for rgb tokens.
- Local `develop` can desync from `origin/develop` after a squash-merge; `git reset --hard origin/develop` before follow-up work.
- Prod is a rolling deploy; poll canonical URLs until consistent (no `?cache-bust` query — separate stale CDN entry).
