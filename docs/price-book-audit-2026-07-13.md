# Price-Book Audit — 2026-07-13

**Scope:** `diet_planner/data/canonical_prices.yaml` (231 entries), the static book
that feeds per-recipe prices shown to paying customers
(`services/recipe_pricing.py` → `RecipeSerializer.get_price_range`).

**Status:** Proposal only. Nothing committed to the live book. Corrections live in
`diet_planner/data/canonical_prices.proposed.yaml` for human approval, per the
Component-1 gate in the per-recipe-priced-shopping-list design.

**Deliverables**
- `diet_planner/management/commands/audit_price_book.py` — re-runnable audit gate.
- `diet_planner/tests/test_audit_price_book.py` — unit tests for band/ratio/unit logic.
- `diet_planner/data/canonical_prices.proposed.yaml` — corrected copy (`verified` + `source` on every entry).
- this report.

---

## 1. Headline finding

The book was auto-seeded from **catalog medians and never audited**, and the medians
are **systematically inflated** — especially for fresh produce and staples, which
drive ~90% of recipe cost. Of 34 corrected entries, **30 went down**, several by
2–3.5×:

- `bananas` **597.8 → 26.2 Kč/kg** (−96%) — a gross seeding error (per-kg price was ~23× the real shelf price).
- `carrots` −71%, `potatoes` −66%, `pasta` −62%, `pork` −57%, `apples` −56%, `bread` −55%.
- The known `chicken-breast` bug (350 Kč/kg, 3.2× thigh) is corrected to 169.9 Kč/kg (1.55× thigh).

The catalog medians cannot be trusted at face value; cross-checking the book against
the catalog is circular (same polluted source). We re-anchor the staples to official
national data.

---

## 2. Methodology (tiered — not scrape-and-average)

| Tier | Source | Role | `verified` |
|---|---|---|---|
| 1 | **ČSÚ** national average consumer prices, Dec 2025 (VDB `webgraf.CenyCSV`, 33 CPI-basket staples, Kč/unit) | primary anchor for staples | `true` |
| 2 | ČSÚ-derived **ratio / piece-weight** estimates (breast from whole chicken, tenderloin from beef, etc.) | mid-tail the basket doesn't track directly | `false` |
| 3 | Reasoned **wholesale × margin** estimates for clearly-broken entries | rescue absurd values (plant-milk, mango, garlic, leek) | `false` |

Everything the ČSÚ basket doesn't cover and that the audit did **not** flag as
implausible is left at its catalog median, tagged `catalog-median-unchanged`,
`verified: false`. A number is only `verified: true` when it is Tier-1
ČSÚ-anchored.

**ČSÚ source:** [Vývoj průměrných cen vybraných potravin](https://csu.gov.cz/vyvoj-prumernych-cen-vybranych-potravin-2024)
→ CSV `https://vdb.czso.cz/pll/eweb/webgraf.CenyCSV` (latest data point 2025-12; the
monthly field survey was discontinued end of 2025, so Dec 2025 is the last full basket).

### The audit gate (Component 1a/b/c)

`python manage.py audit_price_book` flags an entry three ways:

- **(a) Category band** — the per-kg / per-l / per-piece price falls outside a
  plausible shelf-price band for its *inferred category*. Bands are category-aware
  (a spice legitimately costs thousands of Kč/kg; a vegetable does not). Count-priced
  (`ks`) items are converted to Kč/kg via `typical_unit_weights.yaml` so they hit the
  same band as their weight-sold shelf form.
- **(b) Ratio sanity** — encoded intra-family expectations:
  - `chicken-breast / chicken-thigh` ∈ [1.2, 2.0] (breast is normally ~1.3–1.8× thigh)
  - `beef-tenderloin / beef` ∈ [1.4, 3.2] (premium cut vs generic)
  - `white-sugar / sugar` ∈ [0.6, 1.5]
  - `whole-milk / semi-skimmed-milk` ∈ [0.85, 1.3]
  - `rice-basmati / brown-rice` ∈ [0.4, 2.5]
- **(c) Thin sample** — median rests on ≤ 2 catalog samples.

Result: current book flags **13** entries; the proposed book flags **0 staples**
(the 11 remaining are borderline-premium or thin-sample non-staples left for human
review — see §5).

---

## 3. ČSÚ → book unit conversions (show the arithmetic)

Engine convention: `price_per_unit` = **CZK per ONE base unit** (`g`, `ml`, or `ks`).
So a ČSÚ price in Kč/kg or Kč/l must be **÷ 1000**; Kč/ks stays as-is; and a Kč/kg
price for a count-unit slug is multiplied by the typical piece weight (kg).

**Mass (Kč/kg ÷ 1000 → Kč/g):**

| ČSÚ item | Kč/kg | ÷1000 → price_per_unit | back-check |
|---|---|---|---|
| Hovězí zadní bez kosti | 337.32 | **0.3373** `beef` | ×1000 = 337.3 Kč/kg ✓ |
| Vepřová pečeně 120.78 + kýta 111.13 (avg) | 115.96 | **0.1160** `pork` | 116.0 Kč/kg ✓ |
| Šunka vepřová | 255.67 | **0.2557** `ham` | 255.7 ✓ |
| Vepřové sádlo | 98.35 | **0.0984** `lard` | 98.4 ✓ |
| Máslo | 186.13 | **0.1861** `butter` | 186.1 ✓ |
| Eidamská cihla | 205.15 | **0.2052** `cheese` | 205.2 ✓ |
| Jablka | 32.46 | **0.0325** `apples` | 32.5 ✓ |
| Banány | 26.24 | **0.0262** `bananas` | 26.2 ✓ |
| Brambory | 13.49 | **0.0135** `potatoes` | 13.5 ✓ |
| Mrkev | 19.32 | **0.0193** `carrots` | 19.3 ✓ |
| Rajská jablka | 66.49 | **0.0665** `tomatoes` | 66.5 ✓ |
| Zelí hlávkové | 18.50 | **0.0185** `cabbage` | 18.5 ✓ |
| Chléb kmínový | 45.14 | **0.0451** `bread-loaf` | 45.1 ✓ |
| Mouka hladká | 14.17 | **0.0142** `plain-flour` | 14.2 ✓ |
| Těstoviny vaječné | 60.73 | **0.0607** `pasta` | 60.7 ✓ |
| Cukr krystalový | 15.97 | **0.0160** `sugar`, `white-sugar` | 16.0 ✓ |
| Med | 159.63 | **0.1596** `honey` | 159.6 ✓ |

**Volume (Kč/l ÷ 1000 → Kč/ml):**

| ČSÚ item | Kč/l | → price_per_unit |
|---|---|---|
| Mléko polotučné pasterované | 24.60 | **0.0246** `semi-skimmed-milk` (×1000 = 24.6 ✓) |

**Count (`ks`) slugs — Kč/kg × piece-weight(kg):**

| slug | ČSÚ Kč/kg | piece g | price_per_unit (Kč/ks) |
|---|---|---|---|
| `lemons` (citrony) | 65.02 | 100 | 65.02 × 0.100 = **6.5020** |
| `onion` (cibule) | 14.71 | 110 | 14.71 × 0.110 = **1.6181** |
| `cucumber` (okurka) | 88.04 | 300 | 88.04 × 0.300 = **26.4120** |
| `bell-pepper` (paprika) | 95.60 | 150 | 95.60 × 0.150 = **14.3400** |

**Per-10-pieces:** Vejce 52.98 Kč/10 ks → **5.2980** Kč/ks (`eggs`).

**Piece → weight (book stores `květák` in grams):** Květák 42.58 Kč/kus ÷ ~750 g head
= **0.0568** Kč/g (`cauliflower`, Tier-2 — depends on head-weight assumption).

**Tier-2/3 estimates (not directly in the basket):**

| slug | basis | new |
|---|---|---|
| `chicken-breast` | whole chicken 71.29 Kč/kg × ~2.4 (breast retail premium; matches Rohlík basic 150–180) | 169.9 Kč/kg |
| `beef-tenderloin` | ~2× `beef` (337) | 649.9 Kč/kg |
| `ground-meat` | pork/beef mince mix ~150 Kč/kg | 150 Kč/kg |
| `whole-milk` | `semi-skimmed` + fat premium | 27.9 Kč/l |
| `plant-milk` | oat/soy basic ~40 Kč/l (was 159.8 — a ~4× error) | 39.9 Kč/l |
| `mango` | ~45–55 Kč/piece (was 121.2) | 49.0 Kč/ks |
| `garlic` | clove, ~240 Kč/kg × 5 g (was ~520 Kč/kg) | 1.20 Kč/ks |
| `leek` | ~50 Kč/kg × 150 g (was 159.6 Kč/kg) | 7.50 Kč/ks |
| `rum` | ČSÚ Tuzemák 264.67 Kč/l (Czech baking "rum"; was 771.3) | 264.7 Kč/l |

---

## 4. Before/after diff (all 34 changed entries)

`old`/`new` are shelf-facing (Kč per **kg** for mass, per **l** for volume, per **ks**
for count), for human readability. Sorted by % change.

| slug | name_cs | old | new | % chg | source | verified |
|---|---|---|---|---|---|---|
| bananas | banány | 597.8 | 26.2 | -96% | csu-vdb-2025-12 | true |
| plant-milk | rostlinné mléko | 159.8 | 39.9 | -75% | estimate-margin | false |
| carrots | mrkev | 67.6 | 19.3 | -71% | csu-vdb-2025-12 | true |
| leek | pórek | 23.9 | 7.5 | -69% | estimate-margin | false |
| bell-pepper | paprika | 44.1 | 14.3 | -67% | csu-vdb-2025-12 | true |
| potatoes | brambory | 39.9 | 13.5 | -66% | csu-vdb-2025-12 | true |
| rum | rum | 771.3 | 264.7 | -66% | csu-tuzemak-2025-12 | false |
| pasta | těstoviny | 159.8 | 60.7 | -62% | csu-vdb-2025-12 | true |
| mango | mango | 121.2 | 49.0 | -60% | estimate-margin | false |
| pork | vepřové maso | 271.6 | 116.0 | -57% | csu-vdb-2025-12 | true |
| beef-tenderloin | hovězí svíčková | 1499.9 | 649.9 | -57% | estimate-csu-ratio | false |
| apples | jablka | 73.9 | 32.5 | -56% | csu-vdb-2025-12 | true |
| bread-loaf | chléb | 100.2 | 45.1 | -55% | csu-vdb-2025-12 | true |
| garlic | česnek | 2.6 | 1.2 | -54% | estimate-margin | false |
| chicken-breast | kuřecí prsa | 349.9 | 169.9 | -51% | estimate-csu-ratio | false |
| cabbage | zelí | 35.2 | 18.5 | -47% | csu-vdb-2025-12 | true |
| tomatoes | rajčata | 119.6 | 66.5 | -44% | csu-vdb-2025-12 | true |
| ground-meat | mleté maso | 249.9 | 150.0 | -40% | estimate-csu-ratio | false |
| eggs | vejce | 8.3 | 5.3 | -36% | csu-vdb-2025-12 | true |
| beef | hovězí maso | 529.9 | 337.3 | -36% | csu-vdb-2025-12 | true |
| cauliflower | květák | 85.4 | 56.8 | -33% | csu-derived-pieceweight | false |
| onion | cibule | 2.2 | 1.6 | -26% | csu-vdb-2025-12 | true |
| ham | šunka | 339.4 | 255.7 | -25% | csu-vdb-2025-12 | true |
| cucumber | okurka | 33.4 | 26.4 | -21% | csu-vdb-2025-12 | true |
| lemons | citrony | 8.0 | 6.5 | -19% | csu-vdb-2025-12 | true |
| butter | máslo | 199.6 | 186.1 | -7% | csu-vdb-2025-12 | true |
| sugar | cukr | 16.9 | 16.0 | -5% | csu-vdb-2025-12 | true |
| semi-skimmed-milk | mléko polotučné | 25.9 | 24.6 | -5% | csu-vdb-2025-12 | true |
| honey | med | 166.6 | 159.6 | -4% | csu-vdb-2025-12 | true |
| lard | sádlo | 95.6 | 98.4 | +3% | csu-vdb-2025-12 | true |
| white-sugar | Cukr krystal | 14.9 | 16.0 | +7% | csu-vdb-2025-12 | true |
| whole-milk | mléko plnotučné | 22.9 | 27.9 | +22% | estimate-csu-ratio | false |
| plain-flour | mouka hladká | 9.9 | 14.2 | +43% | csu-vdb-2025-12 | true |
| cheese | sýr | 134.5 | 205.2 | +53% | csu-vdb-2025-12 | true |

Biggest swings: `bananas` −96% (seeding error), then produce/staples −55…−75%.
Two entries were too *low* and rose: `plain-flour` +43% and `cheese` +53% (the generic
`sýr` median undershot the eidam reference).

---

## 5. Coverage & entries we could NOT confidently price

**Coverage:** 24 of 231 entries (10%) are now `verified: true` (Tier-1 ČSÚ). 10 more
are corrected Tier-2/3 estimates (`verified: false`, sourced). The remaining ~197 keep
their catalog median, tagged `catalog-median-unchanged`, `verified: false`.

> Per the design's honesty gate (`COVERAGE_MIN` in `recipe_pricing.py`), the frontend
> should surface a headline total only when verified coverage clears the threshold, and
> **must never render a price for an unverified canonical**. 10% verified means the
> priced-list should currently show per-line `~X Kč` for verified staples and
> "bez ceny" elsewhere, not a whole-recipe headline — unless coverage is grown (next).

**Flagged but left unchanged (need a Rohlík/Košík basic-SKU check or human input):**

- Borderline-above-band specialty items (plausible, but unverified):
  `almond-flour` (419.8 Kč/kg), `oat-flour` (247.6), `cornstarch` (239.6),
  `panko-breadcrumbs` (284.5), `tortilla-chips` (527.2), `sesame-oil` (1195.7 Kč/l),
  `arugula` (455.1 Kč/kg). These may be correct for a premium SKU; a Tier-2 scrape
  would confirm.
- Thin-sample (≤2 catalog samples): `mustard` (n=1), `protein-powder` (n=1),
  `coffee` (n=2), `pineapple` (n=2). Fragile regardless of plausibility — re-source.

**Known lower-confidence estimates in the proposal (review before trusting):**
`chicken-breast`, `cauliflower` (head-weight assumption), `whole-milk`, `plant-milk`,
`mango`, `garlic`, `leek`, `beef-tenderloin`, `ground-meat`, `rum`.

**Caveat on `butter`:** anchored to Dec 2025 (186.1 Kč/kg). The June 2026 ČSÚ inflation
release notes butter fell to ~142 Kč/kg (lowest since Aug 2021) — a volatile trough.
186 is the defensible last-full-basket value; revisit if butter-heavy recipes look high.

---

## 6. How to re-run

```bash
# audit the live book
python manage.py audit_price_book

# audit the proposal (expect 0 staple flags)
python manage.py audit_price_book --book diet_planner/data/canonical_prices.proposed.yaml

# dump per-entry flags to CSV
python manage.py audit_price_book --csv /tmp/price_audit.csv

# unit tests for the band/ratio/unit-conversion logic
python manage.py test diet_planner.tests.test_audit_price_book
```

**Next step (human):** review this diff + `canonical_prices.proposed.yaml`, then decide
whether to promote to `canonical_prices.yaml`. Growing verified coverage past
`COVERAGE_MIN` (0.6) for the headline total needs a Tier-2 Rohlík/Košík basic-SKU pass
on the mid-tail — out of scope for this audit.
