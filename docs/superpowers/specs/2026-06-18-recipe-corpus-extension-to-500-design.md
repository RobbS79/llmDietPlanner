# Recipe Corpus Extension to 500 (B2 Push)

**Status:** Design approved 2026-06-18.
**Phase:** B2 of `docs/recipe-grounding-plan.md`.
**Companion docs:** `docs/recipe-corpus-scaling.md` (the playbook this spec executes).

## 1. Problem & goal

The curated `CuratedRecipe` corpus is at the B0/B1 pilot size — **30 entries
in `docs/curated-recipe-index.json`**. Retrieval (`select_recipes_for_plan`)
serves only `status=published` + slot-matching + dietary-tag-covering +
`is_catalog_mapped()` recipes, so at 30 the planner repeats dishes within a
7-day plan and can't honor narrower dietary requests.

**Goal:** grow the published, catalog-mapped corpus to **500 recipes** in a
single push, with even depth so every **(meal slot × main dietary tag)** cell
has **≥ 15–20** options.

**Primary optimization:** variety-per-plan (anti-repeat) **and** dietary depth
(fill the doc-flagged gap cells first: breakfast, snacks, vegan, gluten-free).

## 2. Scope & non-goals

**In scope:**
- Source selection for ~470 new dish URLs (PM subagent).
- Building the four §8 follow-up tools from `docs/recipe-corpus-scaling.md`.
- Running the existing pipeline (`build_curated_recipes`,
  `remap_curated_recipes`) end-to-end in prod against the new index.
- Canonical-ingredient dictionary growth between batches.
- Promotion to `status=published` for the catalog-mapped subset.

**Out of scope:**
- Multi-market: corpus stays **CZ-first** (SK shares the catalog, so it
  benefits passively). PL or other markets are future work.
- Tightening the promotion gate beyond `is_catalog_mapped()` (e.g. requiring a
  judge verdict ≥ `minor_issues`) — the gate stays as the doc specifies.
- Changes to the pipeline itself (`build_curated_recipes`,
  `recipe_curation` service, scrapers) — those are stable.
- Public recipe SEO pages — bonus mentioned in the doc but not part of this
  push.

## 3. The PM subagent: source selection

A `general-purpose` subagent is dispatched, framed as a senior product manager
responsible for the corpus's coverage strategy.

**Brief to the subagent:**
- Target output: **5 batched index files** named
  `docs/curated-recipe-index-batch01.json` … `batch05.json`, ~94 entries each,
  matrix-balanced.
- Each entry follows the existing schema:
  `{ "dish_name": "...", "source_url": "...", "source_name": "...",
    "source_author": "..."? }`.
- Hard sourcing rules (from `recipe-corpus-scaling.md` §2):
  - Prefer sites that publish `schema.org/Recipe` JSON-LD (clean extraction).
  - Recipes must be plausibly **CZ-catalog-buyable** — built from buyable
    staples, no exotic single-source ingredients that would fail
    `is_catalog_mapped()`.
  - **Attribution mandatory** — every entry must carry `source_url` +
    `source_name`; `source_author` when known.
  - **Dedupe by dish**, not just URL — the same dish from two URLs is a dupe.
- Coverage matrix to fill (axes from `recipe-corpus-scaling.md` §2):
  - Meal slot: `breakfast`, `lunch`, `dinner`, `small_meal`, `snack`.
    **Over-source breakfast and snack** — these are the doc-flagged gaps.
  - Dietary tag: `(none)`, `vegetarian`, `vegan`, `gluten_free`, `dairy_free`,
    `low_carb`, `high_protein`. **Over-source vegan and gluten_free.**
  - Cuisine: `czech`, `italian`, `asian`, `mediterranean`, `mexican`,
    `american`, etc. **Target ~40% CZ-traditional / ~60% international.**
- Seed source list (free to extend): Budget Bytes, Cookie and Kate, Love and
  Lemons, NatashasKitchen, toprecepty.cz, recepty.cz.
- Deliverable alongside the JSON files: a Markdown coverage matrix table
  (per-batch and aggregate) so the human reviewer can verify balance at a
  glance before any pipeline run.

The PM subagent dispatch runs **in parallel** with the four-command tooling
build below — they're independent, so we save wall-clock. The pipeline runs
in step 5 only begin once both the index files and the tooling commands have
landed.

## 4. Tooling to build (§8 items)

All four built **TDD-first** as small focused Django management commands.
Each command is independently testable and idempotent.

### 4.1 `promote_curated_recipes`
- Promotes `draft` → `published` iff `is_catalog_mapped()`.
- Flags:
  - `--dry-run` — print what would promote, change nothing.
  - `--min-judge-verdict {coherent,minor_issues}` (optional, default off) —
    additional gate on `quality_score.verdict`.
- Output: promoted count, skipped count (with reason: not catalog-mapped /
  judge below threshold), totals.
- Tests: catalog-mapped promotes; unmapped stays draft; dry-run mutates
  nothing; judge gate filters when set.

### 4.2 `unmapped_ingredients_report`
- Wraps the §4 inline shell query as a real command.
- Iterates all `CuratedRecipe.ingredients` and emits a ranked `Counter` of
  ingredient names where neither `canonical` nor `catalog_id` is set.
- Flags: `--top N` (default 50), `--csv` (machine-readable for tracking
  across batches), `--status {all,draft,published}` (default `all`).
- Tests: returns ranked frequencies; respects `--top`; CSV format stable.

### 4.3 `coverage_matrix_report`
- Prints eligible-published recipe counts per **(slot × dietary tag)**.
- Eligibility = `status='published'` + slot in `meal_types` +
  `dietary_tags ⊇ {tag}` + `is_catalog_mapped()`.
- Flags: `--csv`, `--include-drafts` (debug aid).
- Output is the table we use to verify the ≥ 15–20 target per cell.
- Tests: counts agree with `select_recipes_for_plan`'s eligibility logic on
  fixture data.

### 4.4 DigitalOcean App Platform one-off job spec
- Spec snippet for `app.yaml` (or equivalent) defining a `jobs:` entry that
  runs `build_curated_recipes` against a single batch file argument,
  inheriting the prod env (`DATABASE_URL`, `GEMINI_API_KEY`,
  `ANTHROPIC_API_KEY`).
- Doc snippet on how to invoke the job per batch (`doctl apps create-job ...`
  or console click-path).
- Why: a ~94-URL batch is ~20–30 min wall-clock, and the full push is
  ~95 min total. Console pastes are fragile at this length.

## 5. Execution sequence

End-to-end order — every step is idempotent and resumable:

1. **In parallel** (independent work streams):
   - **PM subagent dispatch** → 5 batch index files committed to `docs/`,
     coverage table reviewed.
   - **Build §8 tooling** (the four commands above) — TDD, merged to main.
2. **Prod prep:** `python manage.py seed_canonical_ingredients` (keep the
   canonical dictionary ahead of the corpus).
3. **Smoke test:** run batch01 with `--limit 20 --no-judge --sleep 1` first,
   inspect the 20 drafts in admin to validate that PM-picked sources extract
   cleanly. If healthy, continue; if not, the PM subagent revises the
   source list before we commit to the full push.
4. **Full batch01 run** via the DO one-off job:
   `build_curated_recipes --index docs/curated-recipe-index-batch01.json
   --sleep 1`.
5. **Dictionary growth loop (after every batch):**
   - `unmapped_ingredients_report --top 50` — review the head of the tail.
   - Add aliases/canonicals to `diet_planner/data/canonical_ingredients.yaml`
     where each entry is either a genuine new ingredient or a synonym of
     an existing one (per `recipe-corpus-scaling.md` §4).
   - Commit the dictionary diff.
   - `python manage.py seed_canonical_ingredients` then
     `python manage.py remap_curated_recipes`.
   - Re-run `unmapped_ingredients_report` to confirm mapping rose.
6. **Repeat steps 4–5** for batches 02, 03, 04, 05.
7. **Coverage check:** `coverage_matrix_report --csv` → verify gap cells are
   advancing toward ≥ 15–20.
8. **Promotion:**
   - `promote_curated_recipes --dry-run` → review the candidate list and
     spot-check ~10 recipes in admin for clarity, cultural fit, shopping
     coherence, attribution.
   - `promote_curated_recipes` (live).
9. **Final report:** `coverage_matrix_report` to confirm distribution; if a
    cell is still under target, schedule a focused mini-batch in a follow-up.

## 6. Quality gates per batch (definition of done)

Per `recipe-corpus-scaling.md` §6:

- `build_curated_recipes` errors ≈ 0 (investigate any fetch/extract fail).
- Ingredient mapping ≥ 95%; unmapped tail is genuine non-ingredients (brines,
  "fresh fruit") or rare exotics.
- Coverage matrix: this batch advances the under-filled cells.
- Human spot-check passed (clarity, cultural fit, shopping coherence,
  attribution).
- No duplicate dishes vs. existing corpus.
- Promoted set = catalog-mapped subset only.

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| **Dictionary lag mid-run** — late batches' unmapped tail explodes; mapping drops below 95%. | Run `unmapped_ingredients_report` between *every* batch, not just at the end. Add canonicals/aliases before the next batch starts. |
| **Same dish from two URLs** — pipeline only dedupes by `source_url`. | PM subagent dedupes its index by dish-name slug before output. Reviewer eyeballs the coverage table for obvious dupes. |
| **Source rot / mass 404s** — a bad source could bleed many fails. | Smoke test (step 4) with `--limit 20` per source family. Pipeline reports `errors` per batch; halt and revise if a source is failing systematically. |
| **Cost overrun** — ~470 × (1 Gemini rewrite + 1 Claude judge). | Smoke run with `--no-judge` first to estimate. If full-push cost is too high, run with `--no-judge` and judge as a separate cheaper follow-up pass. |
| **Coverage skew survives the push** — final report shows a cell still below 15. | Spec accepts a small follow-up mini-batch (≤ 50 URLs) targeted at the under-filled cell; not a failure of this push. |

## 8. Success criteria

- Total `status=published` `CuratedRecipe` count ≥ **500**.
- Every (meal slot × main dietary tag) cell in `coverage_matrix_report` has
  **≥ 15** published catalog-mapped recipes (target 20; 15 is the floor).
- Per-batch pipeline `errors` ≈ 0 across all five batches.
- Final ingredient mapping rate ≥ **95%** across all published recipes.
- All four §8 tooling commands shipped with tests and documented in
  `docs/recipe-corpus-scaling.md` §8 (struck through as completed).
- DO one-off job spec committed and demonstrated to run a batch successfully.

## 9. Out-of-band follow-ups (parked, not in this spec)

- Promote `is_catalog_mapped()` gate from canonical-level to actual
  `StoreProduct`-level once per-store catalogs are populated
  (`recipe-corpus-scaling.md` §4 note).
- Wire published `CuratedRecipe`s into public recipe SEO pages.
- Multi-market corpora (PL etc.) via translated rewrites.
