# DietPlanner AI -- UI/UX Overhaul Plan

Prioritized action items from senior UI/UX Engineer, Graphic Designer, and Marketing Manager audit.
Sources: full frontend code audit, competitive analysis (Eat This Much, Mealime, Prospre, MealPrepPro, Noom, Yazio, Lifesum, MyFitnessPal, HelloFresh, Rohlik.cz, Kosik.cz), and SaaS conversion research.

---

## P0 -- Critical (do first, <1 hour each)

### P0.1 -- Fix Mixed Language (Czech-first CTAs) -- DONE
- [x] Hero headline: changed to Czech (`"Vite, co budete jist / i kolik to bude stat."`)
- [x] Hero CTA: `"Create Your Plan"` -> `"Vytvorit jidelnicek zdarma"`
- [x] Bottom CTA: `"Get Started Free"` -> `"Vytvorit muj prvni plan"`
- [x] All button/label text: fully localized across Landing, Login, CreatePlan, Dashboard, Navbar, ForgotPassword, ResetPassword
- **Files:** `Landing.tsx`, `Login.tsx`, `CreatePlan.tsx`, `Dashboard.tsx`, `Navbar.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`

### P0.2 -- Add Risk-Reducer Micro-Copy Under Hero CTA -- DONE
- [x] Added `"Bez kreditni karty. Hotovo za mene nez 60 sekund."` below hero description
- **File:** `Landing.tsx`

### P0.3 -- Add `og:image` Meta Tag -- PARTIAL
- [ ] **TODO:** Create 1200x630px Open Graph image and place at `frontend/public/og-image.png`
- [x] Added `<meta property="og:image">` to `index.html`
- [x] Added `<meta name="twitter:image">` to `index.html`
- **File:** `index.html`

### P0.4 -- Placeholder/Label Contrast -- DONE
- [x] Bumped `placeholder:text-zinc-800` -> `placeholder:text-zinc-600` across all forms
- [x] Bumped `text-zinc-700/800` labels -> `text-zinc-500` across all pages
- **Files:** `CreatePlan.tsx`, `Dashboard.tsx`, `Login.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`, `PlanView.tsx`, `Landing.tsx`

### P0.5 -- Fix Loading Screen Copy -- DONE
- [x] Changed `"Booting AI Engine..."` to `"Pripravujeme vas jidelnicek..."`
- **File:** `index.html`

### P0.6 -- Accessibility: Add aria-labels to Icon Buttons -- DONE
- [x] Hamburger menu toggle: `aria-label="Otevrit/Zavrit menu"`
- [x] Password eye toggle: `aria-label="Zobrazit/Skryt heslo"` (Login + ResetPassword)
- [x] Logout button: `aria-label="Odhlasit se"`
- **Files:** `Navbar.tsx`, `Login.tsx`, `ResetPassword.tsx`

### P0.7 -- Improved Testimonials with Specifics -- DONE (pulled from P1.2)
- [x] Katerina: added time-saved metric ("Driv 2 hodiny tydne, ted 60 sekund")
- [x] Tomas: added concrete health outcome ("Zhubl jsem 3 kg za mesic bez hladoveni")
- **File:** `Landing.tsx`

### P0.8 -- Social Proof on Login Page -- DONE (pulled from P1.3)
- [x] Added "Pridejte se k 500+ lidem, kteri uz planuji chytreji." below Google button
- **File:** `Login.tsx`

### P0.9 -- Improved Meta Description -- DONE (pulled from P1.8)
- [x] Updated to: "Zadejte sve cile, AI vytvori jidelnicek s recepty a nakupnim seznamem s cenami z Rohliku ci Kauflandu. 10 planu zdarma, bez karty. Hotovo za 60s."
- **File:** `index.html`

### P0.10 -- Improved Dashboard Empty State -- DONE (pulled from P2.7)
- [x] Added benefit-driven copy: "Vytvorte svuj prvni plan a zjistete, kolik usetrite."
- **File:** `Dashboard.tsx`

---

## P1 -- High Impact (1-3 hours each)

### P1.1 -- Sticky Mobile CTA on Landing Page -- DONE
- [x] Fixed bottom CTA bar on mobile, appears after scrolling 600px
- [x] Backdrop blur, full-width indigo button with "Vytvorit jidelnicek zdarma"
- [x] Hidden on `sm:` and above, bottom padding on container to avoid overlap
- **File:** `Landing.tsx`

### P1.2 -- Improve Testimonials with Specifics -- DONE (moved to P0.7)

### P1.3 -- Social Proof on Login/Register Page -- DONE (moved to P0.8)

### P1.4 -- Add `robots.txt` and `sitemap.xml` -- PARTIAL
- [x] Created `frontend/public/robots.txt` with SeznamBot allow + sitemap reference
- [ ] **TODO:** Generate `sitemap.xml` from Django backend
- [ ] **TODO:** Submit to Google Search Console and Seznam Webmaster Tools
- **Files:** `frontend/public/robots.txt`

### P1.5 -- Landing Page: Add "Who Is This For?" Section -- DONE
- [x] 4 cards after testimonials: "Chteji jist zdraveji", "Sleduji makra", "Chteji setrit za jidlo", "Vari doma"
- [x] Czech copy with Heart, Target, Wallet, Lightbulb icons
- **File:** `Landing.tsx`

### P1.6 -- Landing Page: Add "How AI Creates Your Plan" Transparency Section -- DONE
- [x] 4-step explainer: Analyzuje cile > Vytvori jidla > Overuje ceny > Vy mate kontrolu
- [x] Contained in subtle card with indigo-tinted icons
- **File:** `Landing.tsx`

### P1.7 -- Footer: Add Real Links -- DONE
- [x] Privacy Policy page created at `/privacy` with full Czech GDPR content
- [x] Terms of Service page created at `/terms` with full Czech legal content
- [x] Routes added to `App.tsx`
- [x] Footer links already localized to Czech
- **Files:** `Privacy.tsx`, `Terms.tsx`, `App.tsx`, `Landing.tsx`

### P1.8 -- Improve Meta Description -- DONE (moved to P0.9)

---

## P2 -- Medium Effort (half-day each)

### P2.1 -- Progressive Onboarding (Wizard) for CreatePlan
- [ ] Split 3-section form into stepped wizard with progress bar
  - Step 1: Dietary goals (textarea -- most engaging, lowest friction)
  - Step 2: Meal config (meals, snacks, duration)
  - Step 3: Location + store
- [ ] Add progress indicator ("Step 2 of 3")
- [ ] Sticky submit button on mobile
- **Why:** 3-field forms convert at 10.1% vs 3.6% for 9-field forms. Leverages commitment/consistency psychology.
- **File:** `CreatePlan.tsx`

### P2.2 -- Design System Normalization
- [ ] Unify font sizes: standardize to `text-[10px]`, `text-xs`, `text-sm`, `text-base`, `text-lg` (remove arbitrary `text-[11px]` etc.)
- [ ] Unify border radius: `rounded-xl` (buttons/inputs), `rounded-2xl` (cards), `rounded-3xl` (hero sections)
- [ ] Unify spacing scale: `p-6` (compact cards), `p-8` (standard cards), `p-10` (hero sections)
- [ ] Unify shadow scale: `shadow-lg` (cards), `shadow-2xl` (CTAs), remove arbitrary shadows
- [ ] Unify secondary text: `text-zinc-400` (readable labels), `text-zinc-500` (secondary), `text-zinc-600` (tertiary)
- **Why:** Currently 4+ border-radius variants, 5+ shadow styles, 3+ secondary text colors with no clear hierarchy. Inconsistency signals low polish.
- **Files:** All pages and components

### P2.3 -- Recipe Schema Markup (JSON-LD)
- [ ] Add `@type: Recipe` structured data to `RecipePage.tsx`
- [ ] Include: name, ingredients, instructions, nutrition, totalTime, servings
- [ ] Add `@type: WebApplication` to `index.html`
- **Why:** Enables rich recipe cards in Google/Seznam search results -- the most prominent food-related rich snippet.
- **Files:** `RecipePage.tsx`, `index.html`

### P2.4 -- Loading Skeleton States
- [ ] Add skeleton placeholders for Dashboard cards while loading
- [ ] Add skeleton for PlanView meal cards
- [ ] Add skeleton for shopping list items
- **Why:** Perceived performance improvement. Currently shows nothing during API calls.
- **Files:** `Dashboard.tsx`, `PlanView.tsx`, `ShoppingListPage.tsx`

### P2.5 -- Toast Notification System
- [ ] Add toast/snackbar component for success/error feedback
- [ ] Replace inline error alerts with toast notifications where appropriate
- [ ] Add success toast for: plan created, recipe marked cooked, password changed
- **Why:** No global feedback system exists. Users only see errors inline, and success states are often silent.
- **Files:** New component + integration across pages

### P2.6 -- AI Generation "Magic Moment" Animation
- [ ] Replace generic spinner with multi-step progress:
  - "Analyzujeme vase preference..." (Analyzing your preferences)
  - "Hledame nejlepsi ceny..." (Finding best prices)
  - "Optimalizujeme jidelnicek..." (Optimizing your menu)
  - "Vas plan je pripraven!" (Your plan is ready!)
- [ ] Add subtle progress bar between steps
- **Why:** Creates perceived value, reinforces AI + real pricing differentiator. Competitors (Noom) show +10-20% conversion from loading animations.
- **Files:** `LoadingScreen.tsx`, `StatusTracker.tsx`

### P2.7 -- Improve Dashboard Empty State
- [ ] Replace generic Box icon with illustrated empty-state graphic
- [ ] Add benefit-driven copy: `"Vytvorte svuj prvni plan a zjistete, kolik usetrite"` (Create your first plan and see how much you'll save)
- [ ] Larger, more prominent CTA button
- **Why:** Empty states are a critical conversion moment. Current one is too minimal.
- **File:** `Dashboard.tsx`

### P2.8 -- Color Palette Refresh (Consider)
- [ ] Current: dark theme with indigo (#4F46E5) accent
- [ ] Competitor analysis suggests: green primary (Ocean Green #37B97D range) aligns with food/health category norms + Czech grocery brand expectations (Rohlik's green)
- [ ] Alternative: keep dark theme, swap indigo accent to green/emerald for food association
- [ ] Add warm amber/orange accent for CTAs (differentiation from all-green competitors)
- **Decision needed:** Full rebrand or accent-only swap?
- **Why:** Every major food/health competitor uses green. Indigo reads as "tech/SaaS", not "food/health."
- **Files:** `tailwind.config.js`, all components

---

## P3 -- Strategic (1+ days each)

### P3.1 -- Pricing Page
- [ ] Create `/pricing` route
- [ ] Free tier: 10 AI meal plans, basic recipes, shopping list
- [ ] Pro tier: unlimited plans, priority generation, PDF export, advanced macros, multi-store comparison
- [ ] Monthly/annual toggle with "Save X%" badge
- [ ] FAQ section below cards (with FAQ schema markup)
- [ ] Frame cost against savings: `"Stoji mene nez jedno kafe tydne"` (Costs less than one coffee per week)
- **Why:** No pricing page exists. Transparent pricing pages convert at 7-10%.
- **Files:** New `Pricing.tsx` page, `App.tsx` route

### P3.2 -- Server-Side Rendering / Prerendering for SEO
- [ ] Current SPA is invisible to Seznam.cz and suboptimal for Google
- [ ] Option A (quick): Vite SSG plugin or prerender.io for public pages (landing, pricing, public recipes)
- [ ] Option B (full): Migrate landing to Astro/Next.js for hybrid SSR/SSG
- **Why:** Single highest-impact SEO change. Seznam does not fully render JavaScript SPAs.
- **Files:** Build config, deployment

### P3.3 -- SEO Content Layer (Public Recipe Pages)
- [ ] Make generated recipes publicly accessible (no auth required)
- [ ] Each recipe: full page with ingredients, instructions, nutrition, schema markup
- [ ] Internal links to related recipes
- [ ] CTA on each: `"Want a full week of meals like this? Create your free plan."`
- [ ] Content clusters: "keto recepty", "vysoko proteinove jidla", "levne zdrave recepty"
- **Why:** Creates organic traffic engine. Recipe pages are the most SEO-friendly food content format.
- **Files:** Django views/URLs, new frontend pages, sitemap update

### P3.4 -- Onboarding Quiz (Noom-style)
- [ ] 6-8 step quiz before first plan creation:
  1. Primary goal (lose weight / eat healthier / save money / save time)
  2. Household size
  3. Dietary restrictions (vegetarian, vegan, gluten-free, etc.)
  4. Weekly budget in CZK
  5. Preferred store (Rohlik/Kosik/Kaufland/Tesco)
  6. Cooking skill + available time
  7. Allergies
  8. Taste preferences
- [ ] Show personalized plan preview with real prices from chosen store
- **Why:** Quiz-based onboarding: +8.5% trial starts, +17% paying conversions, +22% ARPU (industry benchmarks). Builds commitment before paywall.
- **Files:** New `Onboarding.tsx` wizard, backend to store preferences

### P3.5 -- Weekly Cost Dashboard Widget
- [ ] Add prominent "Weekly Cost" card at top of Dashboard/PlanView
- [ ] Show: `"Tento tyden: 1,247 Kc na Rohliku"` (This week: 1,247 CZK at Rohlik)
- [ ] Running counter: `"Usetfili jste 2,340 Kc tento mesic"` (You saved 2,340 CZK this month)
- **Why:** This is the #1 unique differentiator vs all competitors. No other meal planner shows real grocery prices. Make it impossible to miss.
- **Files:** `Dashboard.tsx`, `PlanView.tsx`, possibly new API endpoint for savings tracking

### P3.6 -- Seznam.cz Optimization
- [ ] Register in Seznam Webmaster Tools (search.seznam.cz/prirucka)
- [ ] Submit sitemap
- [ ] Consider `.cz` domain (dietplanner.cz) -- `.cz` TLDs get priority on Seznam
- [ ] Include keyword variants with and without diacritics
- [ ] Ensure SeznamBot can crawl (requires SSR/prerendering from P3.2)
- **Why:** Seznam has ~25% Czech search market share. Currently invisible to it.

### P3.7 -- CZ Domain + Custom Branding
- [ ] Register `dietplanner.cz` (or `jidelnicek.ai` if available)
- [ ] Move off `squid-app-6avsy.ondigitalocean.app`
- [ ] Custom domain improves trust, SEO, and brand perception
- **Why:** Generic DO subdomain signals "side project." Custom `.cz` domain signals "real Czech business."

---

## Accessibility Backlog

- [ ] Add `prefers-reduced-motion` media query (disable animations for vestibular disorders)
- [ ] Add `skip-to-content` link
- [ ] Add `fieldset`/`legend` to form sections
- [ ] Status badges: add text/icon alongside color (colorblind support)
- [ ] Card `onClick` handlers: use `<button>` or `<a>` instead of `<div>` for keyboard nav
- [ ] Add `aria-live` regions for dynamic content (loading states, form errors)
- [ ] Test with screen reader (NVDA/VoiceOver)

---

## Design Inspiration Sources

| Competitor | Key Takeaway |
|---|---|
| **Eat This Much** | "Try before signup" -- interactive configurator in hero |
| **Mealime** | Speed-to-value -- 3-step Plan > Shop > Cook framework |
| **Noom** | 113-screen onboarding quiz that converts via sunk cost |
| **Rohlik.cz** | 100% satisfaction guarantee, NPS 70+, 4.9/5 rating |
| **HelloFresh** | Segments visitors into 3 personas, different landing per segment |
| **Prospre** | "Free forever" messaging + Instacart integration |
| **Yazio** | Mascot + gamification in onboarding |

---

## Current Uncommitted Changes (to commit)

Files modified (not yet committed on `prod` branch):
- `frontend/index.html` -- favicon, SEO meta, lang=cs
- `frontend/src/pages/Landing.tsx` -- testimonials, metrics, footer links, contrast fixes
- `frontend/src/pages/CreatePlan.tsx` -- placeholder contrast
- `frontend/src/pages/Dashboard.tsx` -- label contrast
- `frontend/src/pages/Login.tsx` -- placeholder contrast, divider contrast
- `frontend/src/pages/ForgotPassword.tsx` -- placeholder contrast
- `frontend/src/pages/PlanView.tsx` -- error text, label contrast
- `frontend/src/pages/ResetPassword.tsx` -- placeholder contrast
- `frontend/public/favicon.svg` -- new custom favicon (untracked)
