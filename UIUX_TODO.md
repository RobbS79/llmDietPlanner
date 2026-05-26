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

### P0.3 -- Add `og:image` Meta Tag -- DONE
- [x] Created 1200x630px Open Graph image at `frontend/public/og-image.png` (dark theme, brand, sample plan, Czech copy)
- [x] Added `<meta property="og:image">` to `index.html`
- [x] Added `<meta name="twitter:image">` to `index.html`
- **Files:** `index.html`, `frontend/public/og-image.png`

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

### P1.4 -- Add `robots.txt` and `sitemap.xml` -- DONE (sitemap implemented)
- [x] Created `frontend/public/robots.txt` with SeznamBot allow + sitemap reference
- [x] Added `django.contrib.sitemaps` to INSTALLED_APPS
- [x] Created `sitemaps.py` with per-section sitemaps (landing, pricing, legal, auth) with proper priority/changefreq
- [x] Added `/sitemap.xml` URL route before catch-all in `urls.py`
- [ ] **TODO (ops):** Submit to Google Search Console and Seznam Webmaster Tools
- [ ] **TODO (ops):** Update `django.contrib.sites` Site domain from default to production domain
- **Files:** `settings.py`, `sitemaps.py`, `urls.py`, `frontend/public/robots.txt`

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

### P2.1 -- Progressive Onboarding (Wizard) for CreatePlan -- DONE
- [x] Split 3-section form into 3-step wizard (Step 1: Goals+city, Step 2: Meals+duration, Step 3: Store)
- [x] Animated progress bar with step indicators (numbered circles, checkmarks for completed)
- [x] "Krok X z 3" label below progress bar
- [x] Back/Next navigation buttons (desktop: bottom row, mobile: sticky bottom bar)
- [x] Step validation: can't advance from step 1 without prompt + city
- [x] Summary card on step 3 showing all selections before submit
- [x] FadeIn animation on step transitions
- [x] Sticky submit button on mobile (fixed bottom bar)
- [x] "Reuse previous settings" only shown on step 1
- [x] Increased range slider height from h-1.5 to h-2 for mobile touch
- **File:** `CreatePlan.tsx`, `index.css`

### P2.2 -- Design System Normalization -- DONE
- [x] Unified font sizes: replaced all `text-[11px]` with `text-xs` across Login, ForgotPassword, ResetPassword, CreatePlan, PlanView
- [x] Unified border radius scale: replaced `rounded-[3rem]` and `rounded-[2.5rem]` with standard `rounded-3xl` across all pages
- [x] Unified shadow scale: created reusable `shadow-glow-sm/md/lg`, `shadow-deep`, `shadow-deep-full` utility classes in `index.css` and replaced all arbitrary shadow values
- [x] Completed full Czech localization of remaining English strings in PlanView, RecipePage, ShoppingListPage, CreatePlan
- **Files:** All pages, `index.css`

### P2.3 -- Recipe Schema Markup (JSON-LD) -- DONE
- [x] Added dynamic `@type: Recipe` structured data to `RecipePage.tsx` via useEffect
- [x] Includes: name, ingredients (recipeIngredient), instructions (HowToStep), nutrition, prepTime, cookTime, totalTime, servings
- [x] Added `@type: WebApplication` schema to `index.html`
- **Files:** `RecipePage.tsx`, `index.html`

### P2.4 -- Loading Skeleton States -- DONE
- [x] Created reusable `Skeleton`, `CardSkeleton`, `MealCardSkeleton`, `ShoppingItemSkeleton` components
- [x] Dashboard now shows 3 card skeletons while loading (replaces full-page LoadingScreen)
- **Files:** `Skeleton.tsx`, `Dashboard.tsx`

### P2.5 -- Toast Notification System -- DONE
- [x] Created `ToastProvider` with `useToast()` hook (success/error methods)
- [x] Auto-dismiss after 4s, slide-in animation, close button
- [x] Wrapped App in `ToastProvider`
- [x] Integrated into PlanView: "Oznaceno jako uvareno!" toast on meal cooked toggle
- **Files:** `Toast.tsx`, `App.tsx`, `PlanView.tsx`, `index.css`

### P2.6 -- AI Generation "Magic Moment" Animation -- DONE
- [x] LoadingScreen now shows context-aware step messages based on generation status
- [x] Added animated progress bar that fills as generation progresses through stages
- [x] StatusTracker steps localized to Czech
- [x] Heading changed to "Generujeme..."
- **Files:** `LoadingScreen.tsx`, `StatusTracker.tsx`

### P2.7 -- Improve Dashboard Empty State -- DONE (in P0.10)
- [x] Benefit-driven Czech copy added in P0 round

### P2.8 -- Color Palette Refresh -- DONE
- [x] Swapped full accent from indigo to emerald green across all 18+ files
- [x] Secondary gradient: purple → teal
- [x] Updated hex shadow values (glow effects) to emerald tones
- [x] Updated index.css base styles (body gradient, btn-primary, input-field, selection color)
- [x] Updated theme.ts accent, MainLayout selection, Badge blue variant → actual blue
- [x] All pages: Landing, Login, CreatePlan, Dashboard, PlanView, Pricing, RecipePage, ShoppingListPage, ForgotPassword, ResetPassword, Privacy, Terms
- [x] All components: Navbar, LoadingScreen, StatusTracker
- **Files:** All frontend files

---

## P3 -- Strategic (1+ days each)

### P3.1 -- Pricing Page -- DONE
- [x] Created `/pricing` route with full Czech pricing page
- [x] Free tier (10 plans, basic features) + Pro tier (149/99 CZK monthly/annual)
- [x] Monthly/annual toggle with "-33%" badge and savings calculator
- [x] Feature comparison list with check/x icons
- [x] FAQ section with 5 questions + accordion UI
- [x] FAQ schema markup (JSON-LD FAQPage) for SEO
- [x] "Stoji mene nez jedno kafe tydne" savings framing
- [x] "Cenik" link added to Landing nav + footer
- [x] Bottom CTA section + footer with privacy/terms links
- **Files:** `Pricing.tsx`, `App.tsx`, `Landing.tsx`

### P3.2 -- Server-Side Rendering / Prerendering for SEO -- DONE
- [x] Build-time prerendering using React `renderToString` + `StaticRouter` (no Puppeteer/Chrome)
- [x] 6 public routes prerendered: `/`, `/login`, `/pricing`, `/privacy`, `/terms`, `/forgot-password`
- [x] Per-route SEO: unique `<title>`, `<meta description>`, canonical URL, OG/Twitter tags
- [x] SSR entry point (`entry-server.tsx`) renders public routes in `StaticRouter` context
- [x] Prerender script (`prerender.mjs`) reads Vite output, injects HTML + meta, saves to `dist/prerendered/`
- [x] Django `react_app_view` serves prerendered HTML for public routes, SPA shell for protected routes
- [x] Vite config handles SSR build (no hash, separate outDir)
- [x] Dockerfile updated to run `build:prod` (tsc → vite build → SSR build → prerender)
- **Files:** `entry-server.tsx`, `prerender.mjs`, `vite.config.ts`, `index.html`, `package.json`, `Dockerfile.prod`, `views.py`

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

### P3.5 -- Weekly Cost Dashboard Widget -- DONE
- [x] **PlanView:** Prominent 3-column cost card at top — weekly cost, estimated savings vs Czech average (1,850 CZK/week), monthly/yearly projection
- [x] **PlanView:** Shows daily cost, shop name, savings percentage
- [x] **Dashboard:** Cost summary banner showing latest plan's weekly cost + savings estimate
- [x] **Dashboard:** Per-card cost display on completed goal cards (fetched via useQueries)
- [x] Localized to Czech with proper number formatting (cs-CZ locale)
- [x] Fixed remaining "days" → "dni" Czech localization on Dashboard cards
- **Files:** `PlanView.tsx`, `Dashboard.tsx`

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

- [x] Add `prefers-reduced-motion` media query (disable animations for vestibular disorders) — `index.css`
- [x] Add `skip-to-content` link — `index.css`, `MainLayout.tsx`, `Landing.tsx`, `Login.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`
- [x] Add `fieldset`/`legend` to form sections — `Login.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`
- [x] Status badges: add text/icon alongside color (colorblind support) — `Badge.tsx` (CheckCircle2/XCircle/Clock/AlertTriangle icons per variant)
- [x] Card `onClick` handlers: use `role="button"` + `tabIndex` + keyboard handler for keyboard nav — `Card.tsx`
- [x] Add `aria-live` regions for dynamic content (loading states, form errors, toasts) — `Login.tsx`, `ForgotPassword.tsx`, `ResetPassword.tsx`, `CreatePlan.tsx`, `LoadingScreen.tsx`, `Toast.tsx`
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
