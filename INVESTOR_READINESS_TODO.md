# Investor-Readiness TODO

Action items surfaced during the investor benchmark of **eatálníček (eatalnicek.eu / DietPlanner)** vs the incumbent **Guláš (gulas.cz)**. Items are scoped to *before a fundraise or public launch* — not the current dev backlog unless noted.

Last updated: 2026-06-01

---

## 1. Pricing — move from 2 tiers to 3  ✅ DONE (2026-06-01, marketing page only)

Implemented in `frontend/src/pages/Pricing.tsx`. Decisions Robert made:

| Tier | Price | Jídelníčky | Úpravy | Akční ceny |
|---|---|---|---|---|
| **Zdarma** | 0 CZK/mo | 2 | 3 / jídelníček | none |
| **Standard** | 99 CZK/mo *(highlighted)* | 7 | 10 | 1 store |
| **Premium** | 199 CZK/mo | 30 | 5 / jídelníček | all stores |

- **Names:** Zdarma / Standard / Premium.
- **Differentiator ladder:** the lever is *akční (sale/leaflet) ceny* — Free none, Standard one store, Premium all stores — plus plan count and edit count.
- **Billing:** monthly only (annual toggle removed). Revisit annual once payments are wired.
- **Free credit:** backend `free_generations_remaining` default 10→2 (migration `login_app/0005`); all "X plánů zdarma" hooks across the site now say "2 jídelníčky" (Landing, Pricing, Onboarding, RecipeIndex, PublicRecipe, Terms, prerender meta).

**⚠️ Still NOT built — payments & enforcement:** there is no payment integration and no tier entitlement gating in the backend. The page is marketing-only; CTAs route to `/login`. The 2/7/30 plan caps and per-tier edit limits are **displayed but not enforced**.

**Payment path — integrate via Shopify** (intended approach, TBD): reuse the existing `shopifyin` app rather than adding Stripe. Open questions to resolve when building:
- Does Shopify support the recurring 99/199 CZK **subscription** model we need (Shopify Subscriptions / selling-plans), or is it only set up for one-off meal-prep-box orders today? Confirm before committing to it.
- Map Standard/Premium → Shopify products/selling-plans; on purchase/webhook, set a subscription/tier field on the user.
- Build gating that enforces plan counts, edit counts, and akční-ceny store scope per tier.
- Webhook handling already exists in `shopifyin/webhooks.py` — extend it for subscription create/cancel/renew events.

---

## 2. De-emphasize "AI" in user-facing copy  ✅ DONE (2026-06-01)

Repositioned messaging around the real differentiator — **real store prices / outcomes** — rather than "AI". "AI"/Gemini remain backend plumbing only. Files changed: `Landing.tsx`, `Pricing.tsx`, `RecipeIndexPage.tsx`, `PublicRecipePage.tsx`, `PlanView.tsx`.

**Intentionally left as-is:** `Terms.tsx` and `Privacy.tsx` still disclose use of "umělá inteligence" and the legal entity name "DietPlanner AI" — AI disclosure in legal/ToS is honest and protective, so it stays. Revisit only if the legal entity name itself changes.

---

## 3. Team page / founder presence  ✅ DONE (2026-06-01)

Built `/o-nas` (`frontend/src/pages/About.tsx`): founder name (Robert Soroka), initials-avatar placeholder, short blurb + full first-person bio (CZ), CTA to pricing. Routed in `App.tsx`, added to the public footer (Landing), prerendered (`prerender.mjs`), and added to the sitemap (`sitemaps.py` → `AboutSitemap`). Used the drafted CZ bio with the neutral mental-health phrasing.

**Open (Robert):** drop a real photo at `frontend/public/founder.jpg` and swap out the "RS" initials placeholder; decide whether to strengthen the mental-health line; optional EN version.

**Founder bio — full version (informal but professional, first-person):**

> **EN**
> Hi, I'm **Robert Soroka**, and I built DietPlanner solo. I work full-time, live an active, sporty life, and care about mental health as much as the physical kind — which is exactly where my problem started: I never had time to plan meals that were both genuinely healthy and actually worth eating. Browsing grocery sites and deciding what to cook, week after week, ate up hours I didn't have. So I built the tool I kept wishing existed — one that plans real, nutritious meals and shows exactly what they'll cost at the stores near me. I was my own first user, and after months of relying on it myself, I'm now sharing it with everyone.

> **CZ**
> Ahoj, jsem **Robert Soroka** a DietPlanner jsem vytvořil sám. Pracuju na plný úvazek, žiju aktivně a sportovně a o duševní zdraví dbám stejně jako o to fyzické — a právě tam můj problém začínal: nikdy mi nezbýval čas naplánovat jídla, která by byla zároveň opravdu zdravá a stála za to je jíst. Procházet e-shopy a rozhodovat se, co týden co týden vařit, mi ukrajovalo hodiny, které jsem neměl. Tak jsem si postavil nástroj, který mi pořád chyběl — takový, co naplánuje opravdová výživná jídla a ukáže přesně, kolik budou stát v obchodech kolem mě. Byl jsem svým prvním uživatelem, a po měsících, kdy jsem se na něj sám spoléhal, ho teď otevírám všem.

**Founder blurb — short version (hero / footer / "About" one-liner):**

> **EN**
> I work full-time and train hard, but never had the time to plan healthy meals or price the shopping. So I built DietPlanner to do both in seconds — and now I'm sharing it with everyone.

> **CZ**
> Pracuju na plný úvazek a sportuju, ale nikdy mi nezbýval čas plánovat zdravá jídla ani počítat nákup. Tak jsem vytvořil DietPlanner, který zvládne obojí za pár vteřin — a teď ho sdílím s vámi.

- [ ] **Confirm the mental-health line.** I rendered the `______` blank as a neutral, low-disclosure phrasing — EN "I care about mental health" / CZ "záleží mi na duševním zdraví". Swap to a stronger word (advocate / "zastánce péče o duševní zdraví") only if you want to lead with it.
- [ ] Decide how public to make this (full name + photo vs first name only).
- [ ] Place on a team/"About" page when ready (CZ primary, EN optional).

---

## 4. Other deferred opportunities (roadmap, not now)

- [ ] **Close the commercial loop** — no Rohlík/Košík cart/affiliate integration today (the Shopify code is a separate meal-prep-box storefront, not grocery checkout). This is where Guláš makes its money; it's the affiliate revenue currently left on the table.
- [ ] **Mobile (native or PWA)** — web-only today; meal planning + in-store shopping are phone behaviors, so this is a structural CAC disadvantage vs Guláš's native apps.
- [ ] **Surface the moat on the marketing site** — the live site shows ~1 store (Rohlík) while the backend supports **10**. Under-selling the single best asset. Show the multi-store price layer + confirmed-vs-estimated price labelling on the landing page.
