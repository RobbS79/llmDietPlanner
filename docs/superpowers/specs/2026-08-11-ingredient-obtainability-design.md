# Ingredient Obtainability in Czech Shops — Design

**Date:** 2026-08-11
**Status:** Approach approved, spec pending review
**Author:** Robert Soroka (with Claude)

## Summary

Recipes in the curated corpus routinely call for ingredients a Czech user
cannot buy on a normal shopping trip — tahini, za'atar, dýňové pyré, bok choy,
vanilkový extrakt, javorový sirup. The corpus is roughly half Czech dishes and
half translated Anglo/US recipes that imported their author's pantry along with
the method. The existing 100% catalog-mapping gate does **not** catch this: it
proves an ingredient exists in *Rohlík's* catalog, never that it is on a shelf
in Albert.

This spec introduces an explicit obtainability rating, rolls it up to the
recipe, gates new recipes on it, repairs the existing corpus by substitution,
and teaches plan selection to prefer the one-stop shop.

The availability bar is set at **"any normal supermarket"** — Albert / Billa /
Kaufland / Tesco / Lidl, one stop, no planning.

Six deliverables, in shipping order:

1. **Rate** — `CanonicalIngredient.availability` on all 295 canonicals, seeded
   from a git-tracked YAML.
2. **Roll up + measure** — `CuratedRecipe.shopping_difficulty` +
   `shopping_blockers`, and a read-only report over the 458 published recipes.
3. **Gate the intake** — curation and chat web research reject unobtainable
   ingredients, so the problem stops regenerating.
4. **Substitute** — rewrite recipes whose blockers have a faithful Czech swap.
5. **Unpublish** the residue, where the specialty ingredient *is* the dish.
6. **Rank** — penalise `findable` recipes in `score_recipe`.

**Substitute and Unpublish are gated on the measurement output** (see
[Decision gate](#decision-gate)). Deliverables are referred to by name
throughout; the numbered subsections under [Design](#design) are a separate
sequence describing *what to build*, not *what ships when*.

## Problem / Motivation

The owner's own stated blocker is "I would not pay for it"
(`[[product-appeal-blocker]]`). Asked to name what was wrong, the answer was
obtainability: *"some recipes with ingredient which are not quite trivial in
shops in cz, or they are but are fancy, or only in specified shops, or simply
not easy to get."*

### Evidence

Measured against prod on 2026-08-11.

**Corpus-wide.** 458 published `CuratedRecipe` rows draw on 273 distinct
non-optional canonicals (of 295 `CanonicalIngredient` rows total, 106 flagged
`is_pantry_staple`). The imported-pantry tail is broad and shallow:

| Ingredient | Recipes |
|---|---|
| vanilkový extrakt | 47 |
| chilli prášek | 29 |
| česnekový prášek | 27 |
| javorový sirup | 26 |
| mandlové mléko | 21 |
| kokosový olej | 20 |
| cibulový prášek | 15 |
| tahini | 13 |

Below that sits a true specialty tail appearing in 1–3 recipes each: za'atar,
sumak, aleppské chilli vločky, harissa, garam masala, zelená kari pasta, nori,
bok choy, tempeh, panko, melasa, tapiokový škrob, kokosový cukr, lahůdkové
droždí, edamame, radicchio.

**Against real traffic** (last 60 days: 38 served meals, 26 distinct recipes) —
**6 clearly broken, 5 borderline**, i.e. roughly one meal in three fails the
one-stop promise:

- `restovane-bok-choy-s-nudlemi` — tamari, soba, shiitake, baby bok choy,
  edamame, rýžový ocet
- `pikantni-stredomorsky-cizrnovy-salat` — aleppské chilli vločky, sumak
- `menemen` — aleppské chilli vločky
- `italsky-sekany-salat` — radicchio, provolone, pepperoncini
- `salat-z-peceneho-kvetaku-s-tahini-dresinkem`, `recka-cizrnova-polevka-revithosoupa` — tahini
- `dynove-muffiny-bez-lepku` — dýňové pyré (effectively nonexistent on Czech
  shelves), mandlová mouka, vanilkový extrakt

Borderline: garam masala, extra pevné tofu, rýžový ocet, sezamový olej,
kadeřavá kapusta.

**Honesty note on this number.** An earlier hand-count put the failure rate at
~50%; that was wrong — it wrongly classed sójová omáčka, dijonská hořčice,
řecký jogurt and avokádo as specialty when all four are in every Czech
supermarket. The corrected figure is ~25% clearly problematic, up to ~40%
counting borderline. The sample is small (26 distinct recipes), and the corpus
is **not** uniformly bad: kulajda, bramborové halušky s brynzou, gulášová
polévka and špenát s knedlíkem are all perfectly shoppable.

### Why one bad ingredient is fatal

A recipe needing one un-buyable item ruins the shopping trip as thoroughly as
one needing five: the user either abandons the meal or makes an extra trip. So
the recipe-level rating takes the **worst** ingredient, not an average.

### Why this can't be derived from data we already hold

`StoreProduct` cannot answer the question. Active product counts on prod:

| Store | Active products |
|---|---|
| ROHLIK | 2384 |
| TESCO_CZ | 61 |
| PENNY_CZ | 59 |
| ALBERT_CZ | 47 |
| KAUFLAND_CZ | 28 |
| LIDL_CZ | 25 |
| KOSIK_CZ, LIDL_SK, KAUFLAND_SK, LUNYS | 0 |

The mainstream chains have leaflet crumbs, not assortments. `LeafletOffer` is
worse for this purpose: it records only *discounted* items, so absence from it
proves nothing at all.

The rating must therefore be **authored**, not computed.

## Scope

**In scope:**
- `CanonicalIngredient.availability` + `availability_note`; git-tracked seed
  YAML; idempotent apply command.
- `CuratedRecipe.shopping_difficulty`, `shopping_blockers`, `adaptation_note`,
  `original_ingredients`; rollup command.
- Read-only distribution report, sliced by meal_type × dietary_tag.
- `IngredientSubstitute.purpose` + `substitute_unit`; CZ availability-swap
  seed data.
- Intake gate in `curate_from_source` and `recipe_research`.
- Substitution rewrite command (`--dry-run` first), judge-verified.
- Unpublish command for the unsaveable residue.
- Ranking term in `score_recipe` + `specialty` exclusion in
  `eligible_recipes_for_slot`, behind a flag.
- Unit tests for the pure rollup/rating logic; one curation test for the gate;
  one retrieval test for the ranking term.

**Out of scope (explicit):**
- **Dish familiarity / appetite** — the `zapadoafricka-arasidova-polevka`
  problem, where every ingredient is buyable but no Czech user wants the dish.
  Deferred to the next project by explicit decision.
- **Any user-visible surface.** No "vše v běžném supermarketu" badge, no
  shopping-difficulty display. The promise gets fixed, not advertised.
- **Curating replacement recipes.** If the report says the corpus is too thin
  after repair, that becomes its own project — it is not smuggled in here.
- **Slovak stores.** All four SK stores hold 0 products; the bar is defined on
  the CZ chains only.
- **Per-store availability.** One rating per ingredient, not a matrix.
- Re-enabling price display (`[[recipe-pricing-rollback-2026-07-13]]`).

## Decisions

Settled with the owner before this spec was written:

1. **Bar = "any normal supermarket"** (Albert / Billa / Kaufland / Tesco /
   Lidl). The strictest of the options offered.
2. **Treatment = "substitute, then drop the rest."** Rewrite where a faithful
   Czech swap exists; unpublish where the ingredient is the dish.
3. **Scope = "shopping first, ship it."** Obtainability now; appetite later.
4. **Rating authored by Claude, arbitrated by the owner** on the flagged subset
   only (~60 of 295). The owner shops in these stores; Claude does not.
5. **Three tiers, not binary** — a middle `findable` tier keeps borderline
   ingredients usable-but-penalised instead of amputating already-thin pools
   (GF lunch was 18 of 372 in `[[grounding-selection-quality-gap]]`).
6. **Rewriting an attributed recipe is disclosed**, via `adaptation_note`, with
   the original ingredients preserved.

## Design

### 1. Data model

#### `CanonicalIngredient.availability`

```python
class Availability(models.TextChoices):
    COMMON    = 'common',    'Common — any supermarket (Albert/Billa/Kaufland/Tesco/Lidl)'
    FINDABLE  = 'findable',  'Findable — large store or Rohlík only'
    SPECIALTY = 'specialty', 'Specialty — asian/bio shop or online only'
    UNRATED   = 'unrated',   'Unrated'
```

Defined at **module level in `catalog.py`**, not nested in the model class, so
`curated.py` can import it for `shopping_difficulty` without a circular import.

`default=UNRATED`, `db_index=True`. Plus:

```python
availability_note = models.CharField(max_length=200, blank=True)
```

— short free text ("Albert ano, Lidl ne") capturing the arbitration reasoning
so a later reviewer isn't re-deriving it.

**`unrated` is deliberately asymmetric:**

| Context | `unrated` behaves as |
|---|---|
| Ranking / eligibility | `findable` — mild penalty, still servable |
| Intake gate (new recipes) | Blocked, same as `specialty` |

Rationale: treating `unrated` as `specialty` everywhere would collapse the
corpus the moment the migration lands; treating it as `common` everywhere would
leak forever. The asymmetry means existing recipes keep working while any
*newly encountered* unknown ingredient forces a human decision. Approved by the
owner as such.

#### `CuratedRecipe`

```python
shopping_difficulty = models.CharField(
    max_length=10, choices=Availability.choices,
    default=Availability.UNRATED, db_index=True,
    help_text="Worst non-optional ingredient's availability. Denormalised; see recompute_shopping_difficulty.",
)
shopping_blockers = models.JSONField(
    default=list, blank=True,
    help_text="Canonical slugs at findable/specialty/unrated that set shopping_difficulty",
)
adaptation_note = models.CharField(max_length=300, blank=True)
original_ingredients = models.JSONField(null=True, blank=True)
```

**Invariant:** the rollup never *writes* `unrated` to `shopping_difficulty` (it
maps an unrated ingredient to `findable`, per the asymmetry table). So
`shopping_difficulty == unrated` means exactly one thing — **the rollup has not
run for this recipe yet** — and reports can rely on that to distinguish "not
computed" from "computed, has unknowns".

`shopping_blockers` exists so that (a) the report can name *which* ingredient
sank a recipe, and (b) ranking can grade by count rather than treating one
blocker the same as four.

`original_ingredients` is the pre-rewrite snapshot: it makes a bad substitution
revertible and preserves what the credited source actually wrote.

#### `IngredientSubstitute`

The model already carries `quality_score` and `conversion_factor`. Two additions:

```python
class Purpose(models.TextChoices):
    PREFERENCE   = 'preference',   'General preference'
    DIETARY      = 'dietary',      'Dietary restriction'
    AVAILABILITY = 'availability', 'Czech shop availability'

purpose = models.CharField(max_length=12, choices=Purpose.choices,
                           default=Purpose.PREFERENCE, db_index=True)
substitute_unit = models.CharField(max_length=20, blank=True,
                                   help_text="Unit after substitution; blank keeps the original")
```

`substitute_unit` is required because `conversion_factor` is a scalar, and *1
lžička vanilkového extraktu → 1 sáček vanilkového cukru* is a unit change, not
a multiplication.

`default=PREFERENCE` keeps every existing row behaving exactly as today.

### 2. Ratings live in git

`diet_planner/data/ingredient_availability.yaml`:

```yaml
- slug: tahini
  availability: specialty
  note: "asijské/bio obchody, v běžném supermarketu ne"
  confidence: high
- slug: kadeřavá-kapusta
  availability: findable
  note: "velké Albert/Kaufland sezónně; malé prodejny ne"
  confidence: low
```

`confidence: low` marks the rows for owner arbitration. A management command
`rate_ingredient_availability` applies the YAML idempotently:

- `--dry-run` — print the diff against current DB state, write nothing.
- `--report-uncertain` — print only `confidence: low` rows, formatted for
  review (~60 lines, not 295).

**Why YAML and not the DB alone:** the owner's review surface becomes a PR
diff rather than a database chore, the ratings are versioned alongside the code
that consumes them, and the same file seeds dev and prod without a data dump.

Every one of the 295 canonicals must appear in the YAML. The command **fails
loudly** on any canonical missing from the file, so growing the dictionary
cannot silently reintroduce `unrated` rows.

### 3. Rollup

`recompute_shopping_difficulty` walks `CuratedRecipe` rows (all statuses) and,
for each:

1. For every **non-optional** ingredient, resolve its canonical — preferring
   the stored `canonical` slug, falling back to
   `canonical_lookup.resolve_canonical(name)`.
2. Unresolvable name → treated as `unrated` (it is, by definition, unknown).
3. `shopping_difficulty` = worst tier seen, ordered
   `common < findable < specialty`, with `unrated` ranked at `findable` for
   this purpose (see the asymmetry table) but recorded in `shopping_blockers`.
4. `shopping_blockers` = sorted slugs of every non-`common` contributor.

Optional ingredients are excluded, matching the existing `is_catalog_mapped()`
semantics — a recipe is not unshoppable because of a garnish.

The worst-wins rule is the direct encoding of "one un-buyable ingredient ruins
the trip".

The rollup runs from the batch command and at the end of `curate_from_source`,
so a freshly curated recipe is never left `unrated`. No signals — recomputation
is always explicit.

### 4. Measurement, and the decision gate

`report_shopping_difficulty` (read-only, zero writes) prints:

- Distribution of `shopping_difficulty` across the 458 published recipes.
- The same distribution **sliced by meal_type × dietary_tag** — the number that
  actually matters is not "how many are clean" but "does GF-lunch still have a
  pool".
- The `specialty`/`unrated` set split into **saveable** (every blocker has an
  `availability`-purpose substitute) vs **unsaveable**.
- Blocker frequency ranking — which ingredients cost the most recipes, so
  substitution effort goes where it pays.

<a name="decision-gate"></a>
#### Decision gate

**Substitute and Unpublish — the two steps that mutate the corpus — do not
start until the owner has seen this report.** If it shows, say, 180 of 458
recipes non-`common`, then "substitute, then drop the rest" leaves a corpus too
thin to personalise from, and the correct next move is curating Czech-shoppable
recipes *before* dropping anything. That is a scope decision for the owner, not
a judgment call to make mid-implementation.

The gate gives the owner a **go / stop / re-scope** call on corpus mutation
only. Rate, Roll up, Measure and the intake gate are unaffected by it — they
mutate nothing and are worth shipping regardless of the answer.

### 5. Intake gate

Mirrors the existing `enforce_plausibility` pattern in `curate_from_source`
(`recipe_curation.py:285`) — a new `enforce_availability: bool = True` kwarg,
checked after `build_recipe_fields` and before persist, soft-rejecting via
`result.error`. Honours the "never raises" contract.

Reject when any non-optional ingredient is `specialty` or `unrated`.
`findable` passes the gate (it is servable, merely penalised).

The gate reads **ingredient-level `availability` tiers directly**, not the
recipe's `shopping_difficulty` rollup — the rollup deliberately softens
`unrated` to `findable`, which is right for ranking and wrong for intake.

Global kill switch: `AVAILABILITY_GATE_ENABLED`, shipped `False` and flipped to
`True` once the ratings are loaded.

**Chat web research** (`recipe_research.py:252`) gets one extra move: on gate
failure, attempt availability substitution first, and reject only if the recipe
is unsaveable. Otherwise "najdi mi něco s tofu" starts failing for no good
reason. Same substitution table, both callers.

A rejected research job needs an honest reason: add fail_reason code
`unshoppable` (the field is `max_length=60`; existing codes are `no_sources` /
`all_sources_failed` / `gates_failed` / `error`), with a Czech reply explaining
that the dish needs ingredients Czech shops don't carry.

**This step ships before the repair steps deliberately.** Without it, web
research imports a maple-syrup recipe tomorrow and the repair work is a
treadmill.

### 6. Substitution

Seed data: `diet_planner/data/ingredient_substitutions_cz.yaml`, loaded into
`IngredientSubstitute` with `purpose='availability'` by a
`load_availability_substitutions` command.

The split that matters — **costume change vs. the dish itself**:

| Saveable (faithful swap) | Not saveable (ingredient *is* the dish) |
|---|---|
| vanilkový extrakt → vanilkové aroma | nori in a sushi miska |
| javorový sirup → med | tahini in a tahini dressing |
| tamari → sójová omáčka | zelená kari pasta in thajské kari |
| avokádový olej → řepkový olej | bok choy in restované bok choy |
| mandlové máslo → arašídové máslo | dýňové pyré in dýňové muffiny |
| ovesná mouka → umleté ovesné vločky | |

**Owner-arbitrated, 2026-08-11:** *vanilkový extrakt is not sold in Czech
shops; vanilkové aroma is an acceptable swap.* This is the corpus's single
largest blocker (37 recipes) and it is now settled as `specialty` → substitute.
Note the swap target currently resolves to the `vanilla` canonical (name_cs
"vanilka"), so it needs its own `vanilla-aroma` canonical before the rewrite
runs, or the ingredient line will read "vanilka" instead of "vanilkové aroma".

`apply_availability_substitutions`, per recipe whose blockers are **fully**
covered by the table:

1. Rewrite the ingredient row — `name` → substitute's `name_cs`, `canonical` →
   substitute slug, `quantity` × `conversion_factor`, `unit` →
   `substitute_unit` when set, and **drop any stale `catalog_id`** (it points
   at a `StoreProduct` for the old ingredient).
2. LLM pass rewrites **only the instruction steps whose text names the old
   ingredient**, returning the same `{text, time_min, tip}` schema. Bounded
   edit: untouched steps are passed through verbatim, not regenerated.
3. Run the existing coherence judge (`judge_curated_recipe`). **Discard the
   whole rewrite if it fails** — no half-adapted recipes.
4. Snapshot `original_ingredients`, stamp `adaptation_note`
   ("Upraveno pro dostupnost v českých obchodech: tamari → sójová omáčka"),
   recompute `shopping_difficulty`.

`--dry-run` prints the full diff per recipe and writes nothing. Runs in
reviewable batches (`--limit`).

**Attribution.** We credit and link a named source, then change their recipe.
`adaptation_note` discloses the change on the recipe itself and
`original_ingredients` preserves what they actually wrote. The LLM never
rewrites silently — that is the entire reason for the judge check and the
snapshot. (Approved by the owner.)

### 7. Unpublish the residue

`status` → `draft` for recipes still `specialty` after substitution. **Never
deleted** — `shopping_blockers` records why, and a future corpus with better
substitutions or a wider bar can restore them. The command prints what it
demoted.

### 8. Ranking

In `eligible_recipes_for_slot` (`recipe_retrieval.py:393`): exclude
`shopping_difficulty == specialty`, alongside the existing `enforce_mapping`
gate. (Once Unpublish has run this is belt-and-braces for published rows, but it also
covers the `enforce_mapping=False` chat-draft path.)

In `score_recipe` (`recipe_retrieval.py:~500`):

```python
_SHOPPING_BLOCKER_PENALTY = 1.0
_SHOPPING_PENALTY_CAP = 3.0
...
if settings.AVAILABILITY_RANKING_ENABLED and recipe.shopping_difficulty != COMMON:
    score -= min(len(recipe.shopping_blockers or []) * _SHOPPING_BLOCKER_PENALTY,
                 _SHOPPING_PENALTY_CAP)
```

**Calibration**, against the existing constants:

| Constant | Value |
|---|---|
| `_WANTED_HIT_WEIGHT` | 20.0 |
| `_RECENT_SERVE_PENALTY` | 8.0 |
| `_SAMPLING_WINDOW` | 1.0 |
| EASY difficulty bonus | 2.0 |

At 1.0 per blocker, a single blocker is exactly enough to push a `findable`
recipe out of the top-1.0 sampling window when an equally-scoring `common`
recipe exists — it loses ties, which is the intent. Against
`_WANTED_HIT_WEIGHT` 20.0 it is negligible, so it can never override what the
user actually asked for. The cap at 3.0 keeps it below the EASY bonus + a
single facet emphasis.

Behind `AVAILABILITY_RANKING_ENABLED`, default `False`; enabled after the
report and the repair land.

## Rollout

| # | Deliverable | Mutates corpus? | Flag |
|---|---|---|---|
| 1 | Migrations + rating YAML + apply command | no | — |
| 2 | Rollup + report | no | — |
| 3 | Intake gate | no (blocks new only) | `AVAILABILITY_GATE_ENABLED` `False` → `True` |
| — | **Owner reads report → go / stop / re-scope** | — | **gate** |
| 4 | Substitution table + rewrite (`--dry-run` reviewed first) | **yes** | — |
| 5 | Unpublish residue | **yes** | — |
| 6 | Ranking term | no | `AVAILABILITY_RANKING_ENABLED` `False` → `True` |

The intake gate is placed *before* the decision gate on purpose: it stops the
bleeding regardless of what the owner decides about existing recipes, and
without it the repair work is a treadmill.

Both flags ship `False`. Nothing about plan generation changes until the
ratings exist and the owner has read the numbers.

Prod data commands run through the DO console harness
(`[[prod-console-exec-harness]]`); prod deploys from the `prod` branch, and the
repo's `.do/app.yaml` is never pushed (`[[recipe-curation-trigger]]`).

## Testing

- **Rollup logic** (pure): worst-wins ordering; optional ingredients ignored;
  unresolvable name → `unrated`; `shopping_blockers` content and sort.
- **Rating command**: idempotent re-apply; fails on a canonical missing from
  the YAML; `--dry-run` writes nothing.
- **Intake gate**: a recipe with a `specialty` ingredient is not persisted and
  `result.error` names it; `enforce_availability=False` bypasses it.
- **Chat research**: a saveable recipe is substituted and accepted; an
  unsaveable one fails with `unshoppable`.
- **Substitution**: quantity × factor and unit swap; stale `catalog_id`
  dropped; judge failure discards the entire rewrite; `original_ingredients`
  snapshot matches pre-state.
- **Ranking**: with the flag on, a `common` recipe beats an otherwise-identical
  `findable` one; with a facet hit the `findable` one still wins.

CI runs the backend `diet_planner` suite on PRs to `develop`
(`[[ci-test-gate]]`).

## Risks

- **The corpus may be too thin after repair.** Mitigated by the decision gate:
  measure before cutting.
- **Claude's ratings will contain errors in both directions.** Mitigated by
  `confidence: low` flagging + owner arbitration, and by the ratings being a
  reviewable PR diff rather than opaque DB state. Nothing here is irreversible:
  a corrected YAML row plus a rollup re-run fixes a bad call.
- **A substitution can produce an incoherent recipe** (swap the ingredient,
  leave the method nonsensical). Mitigated by the bounded instruction rewrite,
  the judge check, and `--dry-run` review.
- **Attribution drift** — addressed by `adaptation_note` +
  `original_ingredients`, accepted by the owner.
- **The bar may be wrong.** "Any normal supermarket" is strict; if pools
  collapse, relaxing to `findable`-allowed is a one-line flag change, not a
  data migration.

## Open questions

None blocking. The owner arbitrates the `confidence: low` ratings during
implementation, and reads the measurement report before Substitute and
Unpublish proceed.
