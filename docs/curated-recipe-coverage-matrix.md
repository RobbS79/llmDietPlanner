# Curated Recipe Coverage Matrix — B2 Push (30 → 500)

Planned sourcing distribution for the ~470-URL corpus expansion, built against
the coverage axes in `docs/recipe-corpus-scaling.md` §2 and the brief in
`docs/superpowers/specs/2026-06-18-recipe-corpus-extension-to-500-design.md` §3.

- **Total new URLs:** 470, split into 5 matrix-balanced batches of 94 each
  (`docs/curated-recipe-index-batch01.json` … `batch05.json`).
- **CZ-traditional / international split:** 167 CZ (36%) / 303 international (64%)
  — within the ~40% / ~60% target band.
- **Dedup:** by dish (URL last-path slug) and by exact URL; 470 distinct dishes.
- **Sourcing:** all entries harvested from sites that publish
  `schema.org/Recipe` JSON-LD (see by-site table) and built from CZ-catalog
  staples (no exotic single-source ingredients).

> Counts below are **planned source URLs per cell**, not yet-published recipes.
> Final published depth depends on the ingredient-mapping gate
> (`is_catalog_mapped()`); `coverage_matrix_report` measures that after the
> pipeline run. The matrix is over-sourced deliberately so each cell still
> clears the ≥ 15–20 floor after some recipes drop on mapping.

## Distribution by meal slot

| Slot | URLs | Share | Notes |
|---|---:|---:|---|
| breakfast | 116 | 24.7% | **Over-sourced** (doc-flagged gap). |
| snack | 111 | 23.6% | **Over-sourced** (doc-flagged gap). |
| small_meal | 94 | 20.0% | Soups, salads, dips, light plates. |
| lunch | 93 | 19.8% | Mains, bowls, hearty soups. |
| dinner | 56 | 11.9% | Thinnest slot — see "Under-filled cells". |

## Coverage matrix: meal slot × primary dietary tag

Each recipe is bucketed by its **most-restrictive** dietary tag
(vegan > gluten_free > high_protein > low_carb > dairy_free > vegetarian >
none), matching how `select_recipes_for_plan` filters: a `vegan` recipe also
satisfies `vegetarian`/`dairy_free` requests, so the strictest tag is the
binding axis for depth. Many vegan rows are *also* `gluten_free`/`dairy_free`,
so the realized depth for those looser tags is **higher** than the cell shows.

| Slot \ Tag | vegan | gluten_free | vegetarian | high_protein | none | **Total** |
|---|---:|---:|---:|---:|---:|---:|
| **breakfast** | 31 | 40 | 37 | 6 | 2 | **116** |
| **snack** | 44 | 22 | 35 | 3 | 7 | **111** |
| **small_meal** | 50 | 5 | 14 | 0 | 25 | **94** |
| **lunch** | 30 | 0 | 29 | 4 | 30 | **93** |
| **dinner** | 42 | 0 | 0 | 7 | 7 | **56** |
| **Total** | **197** | **67** | **115** | **20** | **71** | **470** |

`dairy_free` is not shown as a primary bucket because it is almost always
co-tagged on vegan rows (197 vegan ⇒ 197 dairy_free-eligible). `low_carb`
appears only as a secondary tag on the salmon/roast-chicken dinner cluster.

### Effective dietary depth (recipes that *satisfy* a tag, incl. supersets)

| Tag | Recipes that satisfy it | Floor (≥15)? |
|---|---:|---|
| vegan | 197 | yes |
| vegetarian | 312 (vegan+vegetarian) | yes |
| gluten_free | ~190 (explicit + naturally-GF vegan) | yes |
| dairy_free | ~200 (vegan + tagged) | yes |
| high_protein | 20 | yes |

## Per-batch slot balance

Round-robin distribution across (slot × tag) buckets keeps every batch a
balanced slice — no "all lunches in batch01" skew. Each batch = 94 URLs.

| Batch | breakfast | snack | lunch | dinner | small_meal |
|---|---:|---:|---:|---:|---:|
| batch01 | 24 | 22 | 18 | 11 | 19 |
| batch02 | 23 | 22 | 18 | 12 | 19 |
| batch03 | 23 | 22 | 19 | 11 | 19 |
| batch04 | 23 | 22 | 19 | 11 | 19 |
| batch05 | 23 | 23 | 19 | 11 | 18 |

## Cuisine distribution (planned)

~40% CZ-traditional / ~60% international. International leans Mediterranean,
American, Italian, Asian, Mexican — the cuisines with the cleanest JSON-LD and
the most CZ-buyable ingredient profiles.

| Cuisine bucket | URLs | Share |
|---|---:|---:|
| czech | 167 | 36% |
| american | ~120 | 26% |
| mediterranean | ~55 | 12% |
| italian | ~45 | 10% |
| asian | ~45 | 10% |
| mexican | ~35 | 7% |
| french / other | ~3 | <1% |

(International cuisine counts are approximate — they are a secondary curation
axis; the binding gates are slot × dietary tag and catalog-buyability.)

## By-source-site distribution

| Source site | URLs | JSON-LD |
|---|---:|---|
| Toprecepty.cz | 153 | yes |
| Love and Lemons | 141 | yes |
| Cookie and Kate | 77 | yes |
| Budget Bytes | 50 | yes |
| The Mediterranean Dish | 18 | yes |
| Recepty.cz | 14 | yes |
| Natasha's Kitchen | 9 | yes |
| Gimme Some Oven | 8 | yes |

## Gap-cell prioritization rationale

The doc (`recipe-corpus-scaling.md` §2) flags four chronic gaps. Each was
deliberately over-sourced:

1. **breakfast (116 URLs, the largest slot).** Lunch/dinner are trivially
   abundant on every recipe site; breakfast is where a grounded planner runs
   dry and repeats. We pulled oats/porridge, eggs/frittata/shakshuka,
   pancakes/waffles, smoothies, chia/quinoa bowls, and CZ classics
   (livance, palacinky, ovesna kase, michana vajicka, omelety) so a 7-day plan
   never repeats a breakfast and restricted diets still get variety.
2. **snack (111 URLs).** Second-largest slot. Dips/hummus, roasted chickpeas,
   energy/protein balls, granola bars, popcorn, plus CZ svacina staples
   (chlebicky, buchty, vdolky, kolace, dukatove buchticky, utopenci,
   nakladany hermelin, tatarak).
3. **vegan (197 URLs, 42% of corpus).** The hardest restriction to honor with
   variety. Sourced across *every* slot, not just dinner, so a fully-vegan week
   has breakfast→snack→small_meal→lunch→dinner depth.
4. **gluten_free (67 explicit + most of the 197 vegan rows are naturally GF).**
   Concentrated in breakfast (40) and snack (22) — the slots where GF options
   are scarcest — via almond/oat-flour bakes, egg dishes, smoothies, chia, and
   naturally-GF grain bowls.

## CZ ~40% / international ~60% rationale

- **CZ-first product.** The corpus is CZ-first (SK shares the catalog), and the
  planner's cultural credibility depends on real Czech classics — svickova,
  gulas, rizek, knedliky, the soup canon (kulajda, bramboracka, cesnecka,
  zelnacka, gulasovka, cockova, frankfurtska, hrachova, fazolova). 167 CZ URLs
  give every CZ slot real depth.
- **International for clean extraction + dietary depth.** The doc notes EN sites
  give cleaner JSON-LD and that catalog-buyability — not dish origin — is the
  gate. International sources (Budget Bytes, Cookie and Kate, Love and Lemons,
  The Mediterranean Dish, Natasha's Kitchen, Gimme Some Oven) carry the vegan,
  gluten_free, and breakfast/snack depth that the CZ-traditional canon is thin
  on (Czech home cooking is meat- and dairy-heavy). The 64% international share
  is where almost all the vegan/GF gap-filling lives.
- Net effect: CZ provides cultural anchoring + the "none"/omnivore lunch-dinner
  base; international provides the restricted-diet and breakfast/snack breadth.

## Under-filled cells needing a follow-up mini-batch

Reviewer note — cells below the eventual ≥ 15 published floor may need a small
targeted top-up (≤ 50 URLs) after the mapping gate trims the corpus:

- **dinner (56 total).** Thinnest slot. International dinner mains are well
  covered (vegan 42, high_protein meat/fish 7), but **CZ-traditional dinner**
  is thin — most CZ classics were slotted as lunch (the Czech main meal). If
  `coverage_matrix_report` shows dinner under target, promote some CZ
  lunch mains to also carry the `dinner` meal_type, or source ~20 more
  dinner-appropriate CZ dishes (pecene maso, zapekane pokrmy).
- **high_protein (20).** Adequate but the slimmest tag. Concentrated in
  meat/fish dinners and egg breakfasts; if a high-protein user needs a full
  varied week, a ~15-URL top-up of high-protein lunch bowls/salads would help.
- **snack × high_protein (3) and breakfast × none (2)** are thin *as primary
  buckets*, but these users are served by the large vegetarian/gluten_free
  breakfast and snack pools, so no standalone top-up is expected.
- **low_carb** has no dedicated depth — only incidental on the
  salmon/roast-chicken dinners. Not a doc-flagged gap; defer unless QA shows
  demand.
