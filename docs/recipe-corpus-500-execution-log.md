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
| 4 | `curate-batch` DO one-off job in `.do/app.yaml` + runbook | ✅ committed `27ac01a`, hardened `6dfeb93`; **never installed on live DO spec** (web service only) |
| 5 | PM subagent → 470 source URLs + coverage matrix | ✅ committed `d44260f` |
| **—** | **Merge `develop`→`prod`, deploy** | ✅ active deploy on prod = `60b4ccf` (2026-06-19) |
| 6 | Smoke test (20-URL batch01) + draft inspection | ✅ validated locally 2026-06-18. Prod smoke run via web Console (not the PRE_DEPLOY job — that never installed). |
| 6.5 | Dictionary growth on batch01 smoke set (98→99% mapping) | ✅ shipped via `4bb1bd0` |
| 7 | Full 5-batch curation loop + dict growth | 🟡 **Curation done** (484 total / 454 draft confirmed on prod 2026-06-20). **Dict-growth incomplete:** only batches 01–02 mapped. 345 drafts still blocked by ≥1 unmapped ingredient. |
| 8 | Coverage check → promote → close-out | 🟡 **partial.** First live promotion ran 2026-06-20: **promoted=109 → published_total=139**. The 109 fully-mapped drafts are now served. **345 still draft**, blocked by ≥1 unmapped ingredient — needs dictionary growth (Task 7.3) before a second promote. |

Both `develop` and `prod` are at `60b4ccf` as of 2026-06-19.

---

## 2026-06-20 — prod ground truth confirmed (no longer inferred)

Prod is now **directly scriptable from the dev droplet** (see §"Prod access
method" below), so the 2026-06-19 inferences are replaced with measured numbers.

### Confirmed live counts (prod `llmdietplanner` console)

```
CuratedRecipe   total=484   draft=454   published=30
```

→ This is the **"Task 7 done, Task 8 owed"** case. Curation landed (484 ≈ target
500; the ~16 shortfall = pipeline skips/errors across batches). Only the original
30 are served to users.

### Dry-run promotion — the blocker, quantified

```
[dry-run] promoted=109  skipped_unmapped=345  skipped_judge=0  published_total=30
```

Promoting **right now** would take live 30 → ~139. **345 drafts are blocked**
because the gate is strict.

### Promotion gate semantics (`CuratedRecipe.is_catalog_mapped`, `models/curated.py:135`)

> "Every **non-optional** ingredient resolves to a `catalog_id` or `canonical`."

It's **100%, not a threshold** — a single unmapped non-optional ingredient blocks
the whole recipe. This is why the long-tail unmapped ingredients are so costly:
recipes block on *any* miss, so unlock is not proportional to occurrences fixed.

### Why it stuck "in the middle"

Curation (ingest URLs → drafts) finished for all 5 batches, but the paired
**dictionary-growth loop (Task 7.3)** was only completed for batches 01–02
(`4bb1bd0`, `5d441e7`). Batches 03–05 were curated in the web Console and their
unmapped ingredients were never added to `canonical_ingredients.yaml`. Result:
454 drafts, but 345 sit behind the mapping gate.

### Unmapped report — the shape of the work (`unmapped_ingredients_report --top 50 --status draft`)

```
Unmapped: 692 distinct surface forms, 1012 occurrences, 380 recipes with ≥1 unmapped.
```

**It's a long tail.** Top 50 forms ≈ **244 of 1012 occurrences (~24%)**; the
remaining ~640 forms are mostly singletons/doubletons. Head is full of easy wins —
common staples that simply lack a canonical/alias:

- **Plain staples missing canonicals:** `květák` (cauliflower 7), `šalotka`
  (shallot 7), `jablko`/`brambora` (apple/potato, singular forms), `mango`,
  `pórek` (leek), `klobása`/`špekáčky` (sausage), `garam masala`, `kypřicí prášek
  do pečiva` (baking powder 7), `avokádový olej` (avocado oil 8).
- **Sugar family** (high frequency): `moučkový cukr` (powdered 16), `krystalový
  cukr` (granulated 7), `hnědý cukr` (brown 4), `kokosový cukr` (coconut 4).
- **Inflection / duplicate splits** (the normalizer gotcha — see
  `[[ingredient-mapping-normalizer]]`): `žloutek`(7)/`žloutky`(4) egg yolk;
  `dýňová semínka`(5)/`dýňová semínka (pepitas)`(3) pumpkin seeds — should merge.
- **Long-tail / malformed lines that may never map cleanly:** `kokosový nebo
  olivový olej`, `konopná, chia nebo lněná semínka` — multi-ingredient strings;
  better fixed per-recipe or accepted as permanently blocked.

**Implication:** a focused head-pass (top ~60–80 forms + inflection merges) is
high-leverage but **will not** reach all 454 — covering 24% of occurrences leaves
many recipes still blocked on a single rare miss. Getting from 109 → ~454 means
grinding hundreds of singletons, with diminishing returns. Realistic outcome of
one good pass: promotable rises from 109 into the ~200–300 range.

### Decision options (pending operator choice)

1. **Promote 109 now (no-regret floor)** → 30→~139 live today, reversible-ish, no
   code change. Then grind the dictionary to unlock more in later passes.
2. **Dictionary-growth pass first** → `unmapped_ingredients_report` → add
   canonicals/aliases to `canonical_ingredients.yaml` (TDD per
   `[[ingredient-mapping-normalizer]]`) → commit → deploy → `seed_canonical_ingredients`
   → `remap_curated_recipes` → re-check. Repeat. Then promote a bigger batch.
3. **Consider relaxing the gate** (product/code decision): allow promotion at
   e.g. ≥90% mapped instead of 100%. Would unlock far more than dictionary
   grinding for the same effort — but ships recipes with an unpriceable
   ingredient or two. Worth a separate brainstorm before doing.

### Prod access method (new — 2026-06-20)

Prod was previously "web-Console only." It is now scriptable from the **dev
droplet** (`/opt/llmDietPlanner`):

- A **rotated DO API token** lives in `.env` as `DIGITAL_OCEAN_TOKEN` (value not
  recorded here — see `[[security-incident-dbminer]]` re: secret hygiene).
- Installed `doctl` is 1.116.0 (no `console`); a newer **doctl 1.124.0** binary at
  `/tmp/doctl` provides `apps console`.
- `apps console` needs a TTY; drive it non-interactively with the pty harness
  `/tmp/console_drive.py <app-id> llmdietplanner <token> "<cmd; echo MARKER>" MARKER`.
- App id `f1ffa865-7f6d-4aa0-9e74-2b37dac2f0e8` (`squid-app`), component
  `llmdietplanner`. `DATABASE_URL` is a DO-encrypted SECRET — not extractable from
  the spec, so the console is the only path to the prod DB from here.

### Live promotion #1 (2026-06-20)

```
promoted=109  skipped_unmapped=345  skipped_judge=0  published_total=139
```

First real write to prod via the console harness. Published corpus **30 → 139**.
The 109 fully catalog-mapped recipes are now served to users. Remaining **345
drafts** are blocked by the 100% mapping gate and await dictionary growth.

### Next: dictionary-growth loop (in progress)

Working the head of the unmapped report into `canonical_ingredients.yaml`
(canonicals + aliases + inflection merges), TDD per
`[[ingredient-mapping-normalizer]]`, then commit → deploy → `seed_canonical_ingredients`
→ `remap_curated_recipes` → re-run dry-run promote. Goal: lift promotable past
the current 109 toward ~200–300 on the next pass.

---

## 2026-06-19 status check — "are the 500 live?"

**Short answer: no, not live to users yet.** Curation ran but promotion didn't.

**What was confirmed from the prod web Console on 2026-06-19** (operator session,
output pasted into the Slack thread; not captured in any deployment log):

- Re-running `build_curated_recipes --index docs/curated-recipe-index-batch02.json`
  produced `curated=0 skipped=94 errors=0` → **all 94 batch02 URLs are already in
  the prod corpus** (idempotent skip on `source_url`). Batches 01–05 are
  presumed similarly ingested; only batches 01–02 have left a commit trail.
- `unmapped_ingredients_report` reported **380 recipes with ≥1 unmapped
  ingredient** out of the draft set, with 692 distinct unmapped surface forms
  and 1012 occurrences. That floor alone proves the corpus is well past the
  original 30; the actual `CuratedRecipe` total is higher (recipes with 100%
  mapped ingredients aren't counted in the 380).

**What is NOT yet confirmed:**

- Exact `CuratedRecipe.objects.count()` and the `draft` vs `published` split.
  The Sanity check one-liner below settles it in one paste.
- Whether the §8 promotion step has run. No git/log trail for it; default after
  `build_curated_recipes` is `status=draft`, and only `published` rows are
  served. So unless someone ran `promote_curated_recipes` in the Console
  without telling git, the answer is **drafts only**.

**Why the doc above was stale:** batches 03–05 were curated directly in the
web Console without commits for dictionary growth or status notes. The job-based
path in `.do/app.yaml` was never installed on the live DO spec (`jobs: []` per
`GET /v2/apps/$APP`), so there's no DO Jobs log either. Operator runs in the
web Console don't survive a redeploy.

### Sanity check — paste in web Console any time

Settles total / draft / published in one shot:

```bash
python manage.py shell -c "from diet_planner.models import CuratedRecipe as R; \
print('total:', R.objects.count(), \
      '| draft:', R.objects.filter(status='draft').count(), \
      '| published:', R.objects.filter(status='published').count())"
```

Interpret:

- `published ≈ 30, draft ≈ 470` → Task 7 done, **Task 8 still owed** (run §8 below).
- `published ≈ 470+, draft ≈ 0` → **already live**; backfill this doc and close out.
- anything else → investigate before promoting.

### What to do next (to actually make them live)

```bash
# In the web Console (DO dashboard → llmdietplanner → Console):

# 1. Confirm coverage including drafts; every (slot × main tag) cell ≥ 15
python manage.py coverage_matrix_report --include-drafts

# 2. Dry-run promotion (no writes)
python manage.py promote_curated_recipes --dry-run

# 3. Spot-check 5–10 to-be-promoted drafts in /admin (clarity, attribution,
#    real shopping basket). Hold back problem rows with status=vetted.

# 4. Live promotion (catalog-mapped drafts → published)
python manage.py promote_curated_recipes

# 5. Re-run the Sanity check above; expect published ≈ 470+.
```

The §"Operator runbook — remaining prod steps" Task 8 block below is the
canonical version of step 4; this section is just the "do it now" shortcut.

---

## Local smoke validation + dictionary growth (2026-06-18 ~21:30)

Rather than wait on the ambiguous prod log, the batch01 smoke pass was run
**locally** (`docker-compose run --rm --no-deps web build_curated_recipes
--index docs/curated-recipe-index-batch01.json --limit 20 --no-judge`), which
targets the local Postgres — prod untouched. Two outcomes:

**1. Pipeline + sources are healthy.** `curated=20 skipped=0 errors=0` — all 20
batch01 URLs fetched cleanly via json-ld, no 404s, Czech titles/steps generated
(3–8 steps each). Batch01 sources are good to ship.

**2. 🚩 Correction to the RESUME-HERE assumption below.** The live DO app spec
(`doctl apps spec get`) contains **zero jobs** — only the `web` service. The
`curate-batch` PRE_DEPLOY job exists solely in the repo's `.do/app.yaml`; DO
serves a dashboard-managed spec that ignores it. **So the prod smoke pass never
ran — prod still has only the original 30 recipes.** Installing the job needs
`doctl apps update --spec .do/app.yaml` (overwrites live spec — diff first), or
just run the command in the `web` Console per RESUME HERE. (`doctl` 1.116.0 has
no `apps console` subcommand, so the console step is manual / dashboard-only.)

**3. Dictionary growth — the real gate.** Initial mapping was only 35% because
the local canonical dictionary was unseeded; after `seed_canonical_ingredients`
it was **68%** — still below the 80% smoke gate. One growth pass on the 20-recipe
draft set took it to **99% (186/188)**, 20/20 recipes fully mapped:

- **+24 canonicals** in `diet_planner/data/canonical_ingredients.yaml` (almond
  milk/butter/flour, almonds, pecans, hemp/flax seeds, quinoa, greek yogurt,
  buttermilk, hummus, brussels sprouts, radishes, sun-dried tomatoes, hot sauce,
  za'atar, dates, peaches, cherries, generic fruit, dark chocolate, matcha,
  coffee, English muffins).
- **~35 aliases** for non-stripped qualifier/plural forms on existing canonicals
  (`baby špenát`, `máslo nesolené`, `řezaný oves`, `banán`, `plátky šunky`,
  `sýr čedar`/`gouda`, `rajče roma`, `okurka perská`, `šťáva z citronu`, …).
- **Normalizer fix** (`services/canonical_lookup.py`): `_strip_descriptors` now
  drops unicode vulgar fractions (`½ ¼ ¾ ⅓ …`) the same way it drops ASCII
  quantities — a corpus-wide win (covered by a new TDD test in
  `tests/test_pricing_pantry.py`; full module green, 21 tests).

Two long-tail lines remain unmapped (1.1%), both acceptable:
`konopná, chia nebo lněná semínka` (a malformed multi-ingredient line) and
`javorový sirup navíc` (maple syrup lives in the *migration*-seeded canonical
set, not this YAML).

> **Implication for Task 7:** run the per-batch dictionary-growth loop (7.3) for
> batches 02–05 the same way — curate, `unmapped_ingredients_report`, top up the
> YAML, re-seed + remap — but batch01's surface forms are now covered, so later
> batches should start from a much higher baseline.

---

## ▶ RESUME HERE (as of 2026-06-18 ~19:00)

> ⚠️ Superseded in part by the §"~21:30" section above: the PRE_DEPLOY job is
> **not** in the live spec, so the smoke pass did **not** auto-run. Treat the
> manual `web`-Console run below as the *first* prod curation, not a re-confirm.

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
