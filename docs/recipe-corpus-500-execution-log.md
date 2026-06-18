# Recipe Corpus 30 → 500 — Execution Log & Operator Runbook

Live status and operator handoff for the B2 push that grows the published
`CuratedRecipe` corpus from 30 to ~500.

- **Plan:** `docs/superpowers/plans/2026-06-18-recipe-corpus-extension-to-500.md`
- **Spec:** `docs/superpowers/specs/2026-06-18-recipe-corpus-extension-to-500-design.md`
- **Playbook:** `docs/recipe-corpus-scaling.md`
- **Coverage matrix:** `docs/curated-recipe-coverage-matrix.md`

---

## Status

| Task | What | State |
|------|------|-------|
| 1 | `promote_curated_recipes` command (TDD) | ✅ committed `428c18e` |
| 2 | `unmapped_ingredients_report` command (TDD) | ✅ committed `37f7bbb` + fix `b543577` |
| 3 | `coverage_matrix_report` command (TDD) | ✅ committed `2bd55d3` |
| 4 | `curate-batch` DO one-off job in `.do/app.yaml` + runbook | ✅ committed `27ac01a`, hardened `6dfeb93` |
| 5 | PM subagent → 470 source URLs + coverage matrix | ✅ committed `d44260f` |
| **—** | **Merge `develop`→`prod`, deploy (auto-runs smoke test)** | ✅ pushed `6dfeb93` → DO deploying |
| 6 | Smoke test (20-URL batch01) + draft inspection | 🔄 deploy done; PRE_DEPLOY smoke job likely ran but **unconfirmed** — see RESUME HERE |
| 7 | Full 5-batch curation loop + dict growth | ⬜ prod, not started |
| 8 | Coverage check → promote → close-out | ⬜ prod, not started |

Both `develop` and `prod` are at `6dfeb93` (docs commit `003c5dd` is on
`develop` only; folds into prod on next merge).

---

## ▶ RESUME HERE (as of 2026-06-18 ~19:00)

The merge-to-prod deploy completed and the `web` service came up
(`celery@... ready` in the runtime log). Because DO only starts the service
containers **after** the PRE_DEPLOY job succeeds, the `curate-batch` 20-URL
smoke job has **most likely already run** — but its output was **not
confirmed**. The deploy log view appeared **stale / not updating**, and the
stream being watched was the idle `web` runtime log (the `Done.` line lives in
the separate `curate-batch` component log).

**Do this next — run the smoke test manually in the `web` Console for a
definitive, live result** (sidesteps the stale-log ambiguity):

```bash
python manage.py build_curated_recipes \
  --index docs/curated-recipe-index-batch01.json \
  --limit 20 --no-judge --sleep 1
```

DO dashboard → `llm-diet-planner` → **`web`** component → **Console** tab → paste.

Interpret the final line (idempotent, so safe to re-run):
- `skipped=20 curated=0` → the PRE_DEPLOY job already did it; **gate passes**, go to Task 7.
- `curated=20 errors=0` → fresh run, clean; **gate passes**, go to Task 7.
- A whole **source domain** failing (repeated 404/fetch errors) → swap that
  source (send PM subagent back), re-run.
- Hangs with no output ~2 min → real problem (hung fetch / crashed job), debug
  directly, do not guess from logs.

Then **inspect 5 drafts** in prod admin (Curated Recipes, filter `status=draft`,
sort `created_at` desc): clear Czech steps, real shopping-basket ingredients,
`source_url`/`source_name` present, ≥80% ingredients have `canonical`.

Once the gate passes, proceed to **Task 7** below (set `CURATE_ARGS=""` for full
batches).

> Note: the `google.generativeai` FutureWarning seen in the logs is harmless
> deprecation noise (works fine; future migration to `google.genai` is separate
> low-priority tech debt — not part of this push).

---

## Task 5 deliverable summary (committed `d44260f`)

- **470 URLs**, 5 batch files of 94 each (`docs/curated-recipe-index-batch01.json` … `batch05.json`).
- **0 duplicate URLs.** 5 cross-site same-dish slug collisions (~1%, e.g. `egg-bites`,
  `avocado-toast`) — distinct sources, pipeline dedupes by `source_url`, accepted.
- **CZ / international:** 167 (36%) / 303 (64%) — within the 40/60 band.
- **By slot:** breakfast 116, snack 111, small_meal 94, lunch 93, dinner 56.
- **By strictest dietary tag:** vegan 197, vegetarian 115, none 71, gluten_free 67, high_protein 20.
- **By site:** Toprecepty.cz 153, Love and Lemons 141, Cookie and Kate 77,
  Budget Bytes 50, The Mediterranean Dish 18, Recepty.cz 14, Natasha's Kitchen 9,
  Gimme Some Oven 8.

### Flags carried into the prod push
- **dinner (56)** is the thinnest slot — CZ classics were filed as `lunch` (the Czech
  main meal). Remedy after measuring real coverage: give some CZ lunch mains a
  `dinner` meal_type, or source ~20 more CZ dinner dishes.
- **high_protein (20)** is the slimmest tag — a ~15-URL top-up would round it out.
- A handful of URLs (some CZ soups, the Natasha's Kitchen / Gimme Some Oven set)
  came from domain-scoped WebSearch rather than direct fetch — best candidates to
  eyeball during the smoke test for 404s.

---

## Safety fix: PRE_DEPLOY job auto-runs (commit `6dfeb93`)

DO App Platform `PRE_DEPLOY` jobs run **automatically before every deploy** — there
is no manual-only job kind. The `curate-batch` `run_command` was therefore made
safe-by-default: it reads pipeline flags from `CURATE_ARGS`, which **defaults to
`--limit 20 --no-judge`** (a cheap smoke pass). A merge-to-prod deploy can no longer
auto-burn cost on a full unvetted batch.

```yaml
run_command: >-
  python manage.py build_curated_recipes
  --index ${BATCH_FILE:-docs/curated-recipe-index-batch01.json}
  ${CURATE_ARGS:---limit 20 --no-judge}
  --sleep 1
```

For the full per-batch push (Task 7), override `CURATE_ARGS` to `""` (or `--limit 100`)
and `BATCH_FILE` per batch via the DO Console **Run Job** form.

If a `PRE_DEPLOY` job **fails**, DO **rolls back the deploy** — a smoke failure blocks
promotion of that deploy but does not take the live site down.

---

## Operator runbook — remaining prod steps

All steps run in the **DO App Platform** dashboard for `llm-diet-planner`
(`web` service Console, or the `curate-batch` job). Curation is idempotent and
resumable — existing `source_url`s are skipped, so re-runs are safe.

### Task 6 — smoke test (in progress)

The merge-to-prod deploy auto-ran the smoke pass via the PRE_DEPLOY job.

1. **Watch the job log.** Deployments/Activity tab → running deploy → `curate-batch`
   logs. Expect `Done. curated=20 skipped=0 errors=0` (errors at/near 0). A whole
   source family failing = swap that source; scattered errors are fine.
2. **Inspect 5 drafts.** Prod admin → Curated Recipes → filter `status=draft`, sort
   `created_at` desc. Check: clear novice-friendly Czech steps; ingredients look like
   a real shopping basket; `source_url`/`source_name` populated; ≥80% of ingredients
   have `canonical` set.
3. **Decision gate (6.4):**
   - Clean → proceed to Task 7.
   - Source family failing / poor rewrites → send PM subagent back to swap it, re-run.
   - Mapping < 80% → run the dictionary-growth loop (7.3) on the 20-recipe smoke set first.

### Task 7 — full curation loop (per batch, NN = 01..05)

```bash
# 0. (once, before batch01) refresh the canonical dictionary in the web console
python manage.py seed_canonical_ingredients

# 1. Run the batch via the curate-batch job (DO Console → Run Job):
#    set BATCH_FILE=docs/curated-recipe-index-batchNN.json
#    set CURATE_ARGS=""        # full run, no --limit, with judge
#    Stream logs. ~20–30 min/batch; expect curated≈94 errors≈0.

# 2. Verify the batch landed (web console):
python manage.py shell -c "from diet_planner.models import CuratedRecipe; \
print('drafts:', CuratedRecipe.objects.filter(status='draft').count(), \
      'published:', CuratedRecipe.objects.filter(status='published').count())"

# 3. Dictionary growth pass — find frequent unmapped ingredients:
python manage.py unmapped_ingredients_report --top 50 --status draft
#    For each frequent miss: add a new CanonicalIngredient or an alias in
#    diet_planner/data/canonical_ingredients.yaml (locally), commit, push
#    develop→prod to redeploy, then:
python manage.py seed_canonical_ingredients
python manage.py remap_curated_recipes
python manage.py unmapped_ingredients_report --top 20 --status draft
#    Target: ≥95% mapping on the draft set before the next batch.

# 4. Repeat 1–3 for batches 02..05.

# 5. Confirm corpus size after all 5 batches:
python manage.py shell -c "from diet_planner.models import CuratedRecipe; \
print('total:', CuratedRecipe.objects.count(), \
      'drafts:', CuratedRecipe.objects.filter(status='draft').count(), \
      'published:', CuratedRecipe.objects.filter(status='published').count())"
#    Expect total ≈ 500, drafts ≈ 470, published still ≈ 30 (not promoted yet).
```

### Task 8 — promotion + coverage verification + close-out

```bash
# 1. Pre-promotion coverage (including drafts); every (slot × main tag) cell ≥ 15
python manage.py coverage_matrix_report --include-drafts

# 2. Dry-run promotion
python manage.py promote_curated_recipes --dry-run

# 3. Spot-check 10 to-be-promoted drafts in admin (step clarity, attribution,
#    real shopping basket). Hold back problem rows with status=vetted.

# 4. Live promotion (catalog-mapped drafts → published)
python manage.py promote_curated_recipes
#    Expect promoted≈440 skipped_unmapped≈30 published_total≈470.

# 5. Final coverage snapshot
python manage.py coverage_matrix_report
python manage.py coverage_matrix_report --csv > /tmp/coverage_final.csv
```

### Close-out success criteria (spec §8)

- [ ] Published `CuratedRecipe` count ≥ **500**.
- [ ] Every (meal slot × main dietary tag) cell ≥ **15** (target 20).
- [ ] Per-batch pipeline `errors` ≈ 0 across all five batches.
- [ ] Final ingredient mapping rate ≥ **95%** across published recipes.
- [ ] All four §8 tooling commands shipped with tests (done) and §8 marked complete.
- [ ] `curate-batch` job demonstrably ran a batch.
- [ ] Follow-up mini-batch scheduled for thin cells (dinner, high_protein) if real
      post-mapping coverage shows them below the ≥15 floor.
