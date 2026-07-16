# Landing Value Clarity — Goal-Based Hero (Backlog #1) — Design

**Date:** 2026-07-16 · **Ticket:** Phase I pilot backlog #1 · **Status:** Approved (copy + scope), ready to implement.

## Problem
The landing hero leads with the vaguest, hardest-to-substantiate promise — **deals** (we can only say *how many* ingredients are on sale, never a Kč figure; `PRICE_DISPLAY_ENABLED=false`) — and mismatches the goal/macro-seeking **Fitness** ad audience the pilot targets. Fix: one **goal-based** hero promise; deals demoted to honest supporting proof.

## Scope (approved): hero + home meta + light reframe
Landing-page only. NOT touching recipe-page value-prop echoes, Pricing copy, or Django recipe views (they repeat the old deals line but aren't the landing hero — a separate consistency sweep if ever wanted).

### 1. Hero rewrite — `frontend/src/pages/Landing.tsx` (~L65–74)
- Badge → **Jídelníček podle vašeho cíle** (*A meal plan for your goal*)
- H1 → **Zhubnout, nabrat, nebo jen jíst líp?** / **Naplánujeme vám celý týden jídla.** (*Lose weight, build muscle, or just eat better? We'll plan your whole week of meals.*)
- Subhead → **Popíšete svůj cíl vlastními slovy — a dostanete jídelníček na míru s recepty, nutričními hodnotami (kalorie a makra) a nákupním seznamem. U některých surovin navíc rovnou vidíte aktuální slevy z letáků.** (*Describe your goal in your own words — and get a tailored plan with recipes, nutrition (calories & macros), and a shopping list. For some ingredients you also see current leaflet deals.*)
- CTA + "Bez kreditní karty. Hotovo za méně než 60 sekund." — **unchanged**.

### 2. Home meta — goal-first, replacing the deals-forward tagline
- `frontend/prerender.mjs` home route (`path:'/'`, L23–24) title + description.
- `frontend/index.html` L12/13 (title/desc), L17/18 (og), L24/25 (twitter), JSON-LD L39/42 (WebApplication description) — reconcile the currently-divergent descriptions to the one new string.
- New `<title>`: **Vařto — Jídelníček na míru podle vašeho cíle** (*a tailored meal plan for your goal*)
- New description: **Popište svůj cíl a dostanete týdenní jídelníček na míru — recepty, kalorie a makra i nákupní seznam. U některých surovin navíc slevy z letáků. 2 jídelníčky zdarma.**

### 3. Light reframe (demote loudest supporting deal-emphasis) — `Landing.tsx`
- **Stat band** (L107–110): replace the deals stat `{ '<Každý týden>', 'Nové slevy z letáků českých obchodů' }` with a nutrition stat **{ value: 'Kalorie a makra', label: 'U každého jídla' }** (*Calories & macros / For every meal*). Order stays: 500+ plans · nutrition · <60s.
- **Testimonials** (L125–141): reorder so the weight-loss/nutrition quote (**Tomáš K.**) is first, time-saving (Kateřina) second, deals-led (Marek) third. Quotes unchanged — order only.

## Non-goals
No Kč savings figures. No re-enabling `PRICE_DISPLAY_ENABLED`. No per-audience landing variants. No changes outside the landing page + its meta.

## Verification
- `npx tsc --noEmit` + `npm run lint` (no new problems) locally.
- Grep the changed files to confirm the OLD hero strings ("A ukážeme, co je ve slevě", "Jídelníček s přehledem slev", "přehledem slev v obchodech") are fully gone and the description string is identical across prerender.mjs + index.html (title/og/twitter/JSON-LD).
- **Prod verification is authoritative** (dev box OOMs on `vite build`; prerender/meta only observable after deploy): after deploy, `curl` prod `/` and confirm the new `<title>`/description in the served prerendered HTML, and visually confirm the hero on eatalnicek.eu.
