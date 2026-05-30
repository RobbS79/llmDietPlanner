# Shopping List Pricing — Observation, Investigation, and Implementation Plan

Date: 2026-05-28
Status: Design (no code yet)
Related plans: `STAPLE_PRICING_PLAN.md`

## 1. Observation — what triggered this

**URL inspected:** `https://squid-app-6avsy.ondigitalocean.app/plan/105/shopping-list`
(Note: plan 105 returned 404 on prod for the inspecting session — analysis was done on a manual paste of the list contents that the user provided.)

**Item-level sum is arithmetically correct** — the displayed line items sum to exactly
**1414.20 CZK**, matching the displayed "Odhadovaná cena celkem". Math is not the bug.

**The methodology is misleading.** The per-item prices are essentially whole-pack prices charged against tiny used quantities:

| Item            | Used qty   | Shown price | Reality                                |
|-----------------|------------|-------------|----------------------------------------|
| Med             | 10 g       | 99.9 CZK    | Whole jar — 10 g ≈ half a teaspoon     |
| Pepř            | 1 špetka   | 24.9 CZK    | Whole spice container                  |
| Sůl             | 1 špetka   | 9.9 CZK     | Whole salt pack                        |
| Olivový olej    | 15 ml      | 129.9 CZK   | Whole bottle                           |
| Vlašské ořechy  | 20 g       | 69.9 CZK    | Whole bag                              |
| Rajčatový protlak | 20 g     | 19.9 CZK    | Whole tube/can                         |
| Paprika mletá   | 5 g        | 24.9 CZK    | Whole jar                              |
| Česnek          | 1 stroužek | 29.9 CZK    | Whole bulb                             |

Effect: the total overstates real cost — it bills a full pack for every ingredient even
when the recipe uses a pinch, and ignores that most users already have salt/pepper/oil
at home.

## 2. Direction — what we're switching to

Replace per-item invented prices with two honest signals:

1. **A range** — "Regular price: X–Y CZK" for the non-pantry items in the basket, where
   X = cheapest single-store basket, Y = priciest single-store basket. This motivates
   the store choice without faking precision.
2. **Targeted leaflet deals** — surface only items that are *actually discounted this
   week*, per store, with validity windows. Pair each with a "save ~N CZK" anchor.

User-confirmed decisions during the design discussion:

- Range basis: regular-price variance across stores (X to Y CZK).
- Savings UX: shown adjacent to each discounted item (not as a single hero number).
- Pantry handling: a single full-list "I have basics" checkbox (split into two levels
  per Section 4 below).
- Deals placement: a **separate section** above/below the main shopping list.
- Multi-store: show deals across multiple stores honestly (don't force one store).
- Mobile-first: yes — this view is used in-store on a phone.

## 3. Investigation — what already exists in the codebase

### 3.1 Pantry staples (ready)

- `CanonicalIngredient.is_pantry_staple` boolean, indexed
  (`diet_planner/models/catalog.py:55–131`).
- `CanonicalIngredient.estimated_price_czk` / `estimated_price_eur` for prorated
  fallback pricing.
- `DietaryPlan.pantry_price` field for the prorated pantry share
  (`diet_planner/models/core.py:513–520`).
- ~70 staples already seeded in
  `diet_planner/migrations/0022_seed_canonical_staples.py` — oils, vinegars, salt,
  spices, baking dry goods, condiments. Multi-lingual aliases (EN/CS/SK) included.

### 3.2 Leaflet / discount data (ready)

- `LeafletOffer` model (`diet_planner/models/core.py:588–714`):
  - `shop`, `country`, `ingredient_name`, `display_name`
  - `price`, `original_price`, `discount_percentage`, `currency`
  - `price_type` (DISCOUNTED | REGULAR | LLM_ESTIMATED)
  - `expires_at` (indexed), `scraped_at`, `freshness_state`
  - `store_product` FK into normalized catalog
- Newer append-only history layer (`diet_planner/models/pricing.py:73–167`):
  - `PriceRecord`: `source_type` (LEAFLET_DISCOUNT | STORE_REGULAR | STORE_API |
    HISTORICAL_AVERAGE | LLM_ESTIMATED | USER_REPORTED), `price`,
    `original_price`, `discount_percentage`, `confidence`, `valid_from`,
    `valid_until`, `scraped_at`, `scrape_run` FK
  - Custom manager: `.best_price()`, `.for_ingredient()`, `.current()`
- `PriceFreshnessPolicy` (`pricing.py:169–194`): per-source TTL + auto-expiry config

### 3.3 Store coverage (10 stores)

**Czech (7):** LIDL_CZ, ROHLIK, KOSIK_CZ, ALBERT_CZ, KAUFLAND_CZ, PENNY_CZ, TESCO_CZ
**Slovak (3):** LIDL_SK, KAUFLAND_SK, LUNYS

- All 10 have leaflet data (via kupi.cz / kupino.sk aggregators or direct scrape).
- Rohlík, Košík, Lunys have *catalog* prices (online-only, `is_online_only=True`,
  24h TTL). The other seven are leaflet-only.
- Billa is intentionally absent.
- Confirms memory note: Rohlík and Košík are the strongest catalog targets.

### 3.4 What does NOT exist yet

- A "regular-price range across stores" computation/endpoint.
- A "this-plan's deals this week" query that filters `PriceRecord` by
  `source_type=LEAFLET_DISCOUNT`, `valid_until > now()`, joined to the plan's
  shopping-list ingredients.
- A two-level pantry toggle in the frontend (we have the flag; the UI doesn't expose
  it).
- A "deals" section in the shopping-list React view.

## 4. Pantry staples — proposed two-level toggle

The user asked to broaden staples beyond what's seeded. The ~70 already-seeded items
cover dry goods well. The gap is **perishable basics** people commonly stock but that
rotate (milk, butter, eggs).

| Group              | Default | Examples                                          |
|--------------------|---------|---------------------------------------------------|
| Basics (dry)       | ON      | salt, pepper, oils, vinegar, sugar, flour, spices, soy sauce, mustard, bouillon, baking powder, honey |
| Fridge basics      | OFF     | milk, butter, eggs                                |
| Pantry produce     | (TBD)   | garlic, onion                                     |
| Dry staples        | (TBD)   | rice, pasta                                       |

Two-level toggle reasoning: defaulting milk/butter/eggs ON would advertise savings
the user may not actually have (they go bad and get rebought weekly). Defaulting dry
basics OFF would make the price range look misleadingly higher than reality.

## 5. Proposed UI structure (mobile-first)

```
┌─────────────────────────────────────────────────┐
│ Regular price: 850–1180 CZK                     │  ← range across stores
│ ─────────────────────────────                   │
│ ☑ Mám doma základy (olej, sůl, koření)          │  ← default ON
│ ☐ Mám doma mléko, máslo, vejce                  │  ← default OFF
│ ─────────────────────────────                   │
│ 💰 Tento týden ušetříte až ~210 CZK             │  ← anchor link to deals
└─────────────────────────────────────────────────┘

═══ AKCE TENTO TÝDEN ═══════════════════════════════
 ┌─ Lidl ▪ 10.4.–17.4. ──────────────────────────┐
 │ Mléko polotučné 1L      24.9 → 18.9   −6 Kč  │
 │ Kuřecí prsa 600g       159.0 →119.0  −40 Kč  │
 │ Celkem u Lidlu:                ušetříte 46 Kč│
 └──────────────────────────────────────────────┘
 ┌─ Albert ▪ 12.4.–17.4. ────────────────────────┐
 │ Filet z lososa 200g    139.0 → 99.0  −40 Kč  │
 └──────────────────────────────────────────────┘

═══ NÁKUPNÍ SEZNAM ═════════════════════════════════
[ ] Ovesné vločky        50 g
[ ] Mléko polotučné     300 ml      ★ akce u Lidlu
[ ] Banán                2 ks
 ...

═══ ZÁKLADY (předpokládáme, že máte) ═══════════════
[grey] Sůl, pepř, olivový olej, česnek...
```

Key UI properties:

- The headline number is the **range**, not a single faked total.
- Per-item prices disappear from the main list (no more whole-jar-for-a-pinch).
- The deals section is a separate, scannable block grouped by store, with each
  store's validity window in the header.
- Sale items in the main list carry a `★ akce u <store>` chip linking to the deal.
- Pantry items collapse to a single quiet line.

## 6. Decisions — RESOLVED (2026-05-29)

All six original open questions are now decided, plus a seventh that surfaced
during the discussion (upcoming leaflets):

1. **Range formula.** ✅ **Cheapest–priciest single-store basket.**
   `X = sum(cheapest basket at one store)`, `Y = sum(priciest basket at one
   store)` — both are real single-store totals, computed over the non-pantry
   items (pantry items excluded when their toggle is ON).
2. **Default toggle state.** ✅ **Basics ON, fridge OFF.** Dry basics
   (salt/oil/spices) assumed at home; milk/butter/eggs not assumed.
3. **Deal filtering.** ✅ **Cheapest-source-only.** A leaflet discount qualifies
   as a "deal" *only if* the discounted price is the cheapest source for that
   item across all 10 stores. Avoids advertising a Tesco "sale" that's still
   pricier than Rohlík's regular price.
4. **Per-item price visibility in main list.** ✅ **Drop entirely.** Main list is
   checkbox + name + qty (+ optional `★ akce` chip). Fully removes the
   whole-pack-for-a-pinch problem that triggered this work.
5. **Empty deals state.** ✅ **Show a friendly message** (do NOT hide the
   section). Warm, apologetic tone rather than a terse "Žádné akce".
   **Final Czech copy (LLM-authored, confirmed natural):**
   *"Snažili jsme se, ale pro vaše jídla jsme tento týden žádné slevy nenašli :("*
   (EN reference: "We did our best to find discounts, unfortunately we didn't
   spot anything for your meals :(".)
6. **Stale leaflets.** ✅ **Drop expired silently** (`valid_until < now()`).
7. **Upcoming leaflets.** ✅ **NEW — show them.** kupi.cz lists not-yet-active
   leaflets (e.g. starts in 3 days, runs 7). These are valuable. Decisions:
   - **Build in this iteration** (not a follow-up) — includes the scraper work
     described in Section 7.
   - **One unified "Akce" list** with dated chips: current deals render plain,
     upcoming deals carry an `[od DD.MM.]` chip. No separate "Brzy v akci" block.
   - **Still plan-filtered:** an upcoming deal only appears if its item is
     actually in this plan's shopping list (same join as current deals).

### Three-bucket deal model (derived from #6/#7)

For every plan ingredient, a matched `PriceRecord` with
`source_type=LEAFLET_DISCOUNT` falls into exactly one bucket by its window:

| Bucket    | Condition                              | UI                          |
|-----------|----------------------------------------|-----------------------------|
| expired   | `valid_until < now()`                  | dropped silently            |
| current   | `valid_from <= now() <= valid_until`   | shown, plain                |
| upcoming  | `valid_from > now()`                   | shown, `[od DD.MM.]` chip   |

## 7. Implementation plan

### Scraper (prerequisite for upcoming deals — decision #7) — ✅ DONE 2026-05-29

Implemented. Files touched:
- `scrapers/utils.py`: new `parse_validity_window(text, now)` — parses Czech
  `DD. M.` date tokens (nbsp-tolerant), infers the year (handles Dec→Jan), and
  returns `(valid_from@00:00, valid_until@23:59:59)` tz-aware, handling both the
  full "od <from> – <until>" range and the single "platí do <until>" form.
- `scrapers/kupi_cz.py`: crawls **all** leaflet links (capped at
  `MAX_LEAFLETS_PER_STORE=5`), parses each leaflet's window from its detail-page
  `<h1>` (fallback: listing link text), and stamps `valid_from`/`valid_until`
  onto every offer.
- `models/pricing.py`: `.current()` now also requires `valid_from <= now` (so
  future-dated rows don't leak into live matching — safe, excludes nothing
  existing); new `.upcoming()` returns future-dated, not-yet-expired rows.
- `tasks.py` `scrape_store_task`: uses each offer's parsed window when present,
  else the store's generic TTL.
- Tests: `tests/test_leaflet_validity.py` — parser (SimpleTestCase, 5 cases incl.
  Dec→Jan boundary, all green) + current/upcoming bucketing (needs postgres DB).

Verified live against kupi.cz/lidl: 4 leaflets crawled, 69 offers all stamped
with real windows (two distinct: 28.5–31.5 and 25.5–31.5).

**Deferred / caveats:**
- **SK scrapers (kupino.sk, lunys.sk) NOT date-aware.** Verified their structure
  differs from kupi.cz — no per-leaflet detail page with a date H1, no
  `platí do` text. They stay on the generic-TTL fallback (still correct: rows
  bucket as `current`, never `upcoming`). Upcoming SK deals are a follow-up.
- **Path B (`scrape_and_store`, LLM extraction) still first-leaflet-only.** The
  deals feature reads PriceRecords written by Path A (`scrape_store_task`), which
  is now date-aware, so this is fine; Path B can be aligned later if needed.
- **Non-food leaflets:** crawling all leaflets now also ingests e.g. Lidl's
  "Nabídka spotřebního zboží" (consumer goods). These are harmless (name-based
  ingredient matching ignores them) but do add unused rows.

---

Original problem (for reference): `kupi_cz.py` discarded everything we needed:

- It scrapes only `leaflet_links[0]` (`kupi_cz.py:88`) — the current leaflet —
  and never visits the upcoming ones listed on the same page.
- It parses **no validity dates**; `valid_from`/`valid_until` are set generically
  by the service, not read from the leaflet.
- Its `skip_words` (`kupi_cz.py:24-44`) actively drop titles containing
  `"od pondělí"`, `"od čtvrtka"`, `"platí"`, `"končí"` — the exact validity
  strings we now want to keep and parse.

Work required:

1. Crawl **all** leaflet links on the listing page, not just `[0]`.
2. Add a validity-window parser for `platí od DD.MM. do DD.MM.` (and the
   weekday forms like "od pondělí") → `(valid_from, valid_until)` datetimes.
   Year inference needed (windows can cross year boundary).
3. Stop treating those date strings as skip-words for the *leaflet header*
   (still skip them as product titles); attach the parsed window to each offer
   dict instead.
4. Thread `valid_from`/`valid_until` from the offer through
   `upsert_price_record` — it **already accepts both as params**
   (`price_recording.py:68-69,139-140`), so no signature change there; the
   caller in `scraper_service` must pass the per-leaflet window instead of a
   generic TTL-derived one.
5. Mirror the same date parsing into `kupino_sk.py` / `lunys_sk.py` if they share
   the kupino aggregator structure (verify before assuming).

### Backend

1. Add a helper on the shopping-list service to compute a per-store basket total
   for each of the 10 stores (using `PriceRecord.best_price()` and pantry-aware
   filtering). Returns `{store: {total, currency}, ...}`.
2. Derive `regular_price_range = (min(totals), max(totals))` excluding pantry
   items when the user's pantry toggles are ON.
3. Add a deals query: for each ingredient in the plan, find `PriceRecord` rows
   where `source_type=LEAFLET_DISCOUNT`, drop expired (`valid_until < now()`),
   and bucket the rest into **current** (`valid_from <= now()`) and **upcoming**
   (`valid_from > now()`) — see Section 6 three-bucket table. Apply the
   Decision-3 filter: keep a deal only if its discounted price is the cheapest
   source for that item across all stores. Group by store.
4. Extend the `/api/goals/<id>/` (or shopping-list endpoint) response with:
   - `price_range: {low, high, currency, store_low, store_high}`
   - `pantry_toggles: {basics_on, fridge_on}` (user-settable, persisted)
   - `deals: [{store, valid_from, valid_until, status: "current"|"upcoming",
     items: [{ingredient, original, sale, savings}], store_total_savings}]`
     — only items present in this plan's shopping list.
5. Wire `pantry_toggles` to the existing `is_pantry_staple` filter and to
   `DietaryPlan.pantry_price` recompute.

### Frontend

1. Replace the current per-item-price card layout with the structure in Section 5.
2. Top card: range + 2 toggles + savings anchor link.
3. New unified "Akce" section, grouped by store, with validity dates. Current
   deals render plain; upcoming deals carry an `[od DD.MM.]` chip (decision #7).
   When no plan item matches any deal, render the friendly empty message from
   decision #5 — do not hide the section.
4. Main list: checkbox + name + qty + optional `★ akce u <store>` chip; no price.
5. Collapsed "Základy" section at the bottom.
6. Mobile-first layout; sticky top card with range + toggles.

### Validation

- Manual QA on a plan whose ingredients deliberately span (a) pantry-only items,
  (b) items with current deals, (c) items with no leaflet match. Confirm range,
  deals, and toggles all behave.
- Playwright across the affected plan/shopping-list pages on prod, per the project
  QA workflow (memory: `feedback-qa-prod.md`).

## 8. Out of scope (for this iteration)

- Suggesting an optimal multi-store *route* (e.g. "Lidl + Rohlík delivery"). The
  data supports it; the UI complexity does not.
- Predicting next week's leaflets before they're scraped.
- User-reported price corrections (`PriceRecord.source_type=USER_REPORTED`
  already exists in the schema; no UI yet).
