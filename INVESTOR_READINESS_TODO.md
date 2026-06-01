# Investor-Readiness TODO

Action items surfaced during the investor benchmark of **eatálníček (eatalnicek.eu / DietPlanner)** vs the incumbent **Guláš (gulas.cz)**. Items are scoped to *before a fundraise or public launch* — not the current dev backlog unless noted.

Last updated: 2026-06-01

---

## 1. Pricing — move from 2 tiers to 3  ⬜ TODO

**Current** (`frontend/src/pages/Pricing.tsx`, `PLANS`):
- **Zdarma** — 0 CZK, 10 plans, no real prices / PDF / store comparison
- **Pro** — 149 CZK/mo (99 CZK/mo billed annually), all features

**Target structure:**
| Tier | Price | Notes |
|---|---|---|
| Free | 0 CZK/mo | **Keep exactly as-is** (10 plans, current feature set) |
| Mid | **99 CZK/mo** | new middle tier |
| Top | **199 CZK/mo** | new top tier |

**Open decisions before implementing (need Robert's input):**
- [ ] **Tier names** (CZ) — e.g. Free / Pro / Premium? Confirm naming.
- [ ] **Feature split between 99 and 199.** What does 199 unlock that 99 doesn't? Candidate levers already in the codebase: unlimited vs capped plans, multi-store price *comparison* (vs single store), priority generation, PDF export, history/saved plans, # of stores compared, family/household profiles. Need a deliberate good/better/best ladder, not a guess.
- [ ] **Annual billing** — current toggle shows an annual discount (149→99). Decide annual prices for the new 99 and 199 tiers, or drop annual for now.
- [ ] **Existing "Pro" users / grandfathering** — N/A in dev phase, but note for launch.

**Implementation touchpoints when ready:**
- `frontend/src/pages/Pricing.tsx` — `PLANS` array + the monthly/annual toggle logic
- Stripe/payment price IDs (wherever subscription tiers map to payment products)
- Any backend entitlement/feature-gating that currently checks free-vs-Pro

---

## 2. De-emphasize "AI" in user-facing copy  ✅ DONE (2026-06-01)

Repositioned messaging around the real differentiator — **real store prices / outcomes** — rather than "AI". "AI"/Gemini remain backend plumbing only. Files changed: `Landing.tsx`, `Pricing.tsx`, `RecipeIndexPage.tsx`, `PublicRecipePage.tsx`, `PlanView.tsx`.

**Intentionally left as-is:** `Terms.tsx` and `Privacy.tsx` still disclose use of "umělá inteligence" and the legal entity name "DietPlanner AI" — AI disclosure in legal/ToS is honest and protective, so it stays. Revisit only if the legal entity name itself changes.

---

## 3. Team page / founder presence  ⬜ DEFERRED (pre-fundraise)

Not a dev-phase task. Belongs on the "before fundraise or public launch" checklist. At seed stage investors underwrite the founder; an anonymous site ("© 2026 DietPlanner", no name) is a yellow flag and also depresses *consumer* trust for a money+health product. Cheapest fix on the list — one name, photo, two-sentence bio, a "why I built this."

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
