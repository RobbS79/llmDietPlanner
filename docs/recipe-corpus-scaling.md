# Scaling the Curated Recipe Corpus (B2): 30 → 500–1000

Best-practice playbook for growing the `CuratedRecipe` corpus from the B0/B1
pilot (30 recipes) to a production-grade 500–1000. This is the **B2** phase of
the recipe-grounding plan (`docs/recipe-grounding-plan.md`). It assumes B0/B1
(pipeline) and B3 (retrieval) are already live.

---

## 1. Why size matters

Retrieval (`select_recipes_for_plan`) only serves a recipe that passes the hard
gate: `status=published` + slot in `meal_types` + `dietary_tags ⊇` the user's
restrictions + **`is_catalog_mapped()`** (every non-optional ingredient resolves
to the catalog). With ~20–30 eligible recipes, a 7-day plan repeats dishes and
can't honor narrower diet/cuisine requests. The target:

- **500–1000 published, catalog-mapped recipes.**
- Enough depth that **every (slot × main dietary tag)** cell has ≥ 15–20 options
  so a week of plans never repeats and restricted diets still get variety.

This is the single most important quality lever for grounded generation. Treat
it as an ongoing data-curation program, not a one-off script run.

---

## 2. The critical path: the source-URL index

Everything downstream is automated. The **only** human-gated input is the
source-URL index — `[{dish_name, source_url, source_name, source_author?}]`
(see `docs/curated-recipe-index.json` for the 30-row pilot and
`docs/curated-recipe-index.example.json` for the schema).

**Build the index against an explicit coverage matrix, not ad-hoc.** Define the
cells you must fill and curate URLs until each is covered:

| Axis | Values | Notes |
|---|---|---|
| Meal slot | breakfast, lunch, dinner, small_meal, snack | Lunch/dinner are easiest; **breakfast & snacks are usually the gap** — over-source them. |
| Dietary tag | (none), vegetarian, vegan, gluten_free, dairy_free, low_carb, high_protein | Each tag needs standalone depth, not just incidental matches. |
| Cuisine | czech, italian, asian, mediterranean, mexican, american, … | Target ~40% CZ-traditional / ~60% international (tune in QA). International EN sites give cleaner JSON-LD. |

Rule of thumb for 1000 recipes: ~5 slots × ~6 diet profiles × variety → plan in
**batches of ~100**, each batch a balanced slice of the matrix, so coverage
grows evenly instead of 400 lunches and 5 breakfasts.

### Sourcing guidance
- **Prefer sites with `schema.org/Recipe` JSON-LD.** The pilot got clean
  extraction (`json-ld`, 0 errors) precisely because the chosen sites are
  structured. Large EN recipe sites (Budget Bytes, Cookie and Kate, Love and
  Lemons, NatashasKitchen, etc.) and the better CZ sites (toprecepty.cz,
  recepty.cz) are reliable. Avoid blog HTML with no structured data — extraction
  degrades to messy page-text.
- **Catalog-buyability is the gate, not dish origin.** A recipe is only useful if
  its ingredients map to the CZ/SK catalog. Bias toward dishes built from
  buyable staples; exotic single-source ingredients will fail `is_catalog_mapped`
  and waste a slot. (See §4.)
- **Attribution is mandatory.** Always store `source_url` + `source_name` (and
  `source_author` when known). We paraphrase into our own novice-clear steps and
  **link back with credit** — this is the legal posture and sends creators
  traffic. Keep a per-source note in `license_note`.
- **De-dupe before curating.** The pipeline skips an entry whose `source_url` is
  already in the corpus, but it won't catch the *same dish from two URLs*. Keep
  the index itself deduped by dish.

---

## 3. The pipeline (per batch)

All commands are **idempotent and resumable** — safe to re-run; a recipe whose
`source_url` already exists is skipped. Run in the **production environment**
(DO App Platform Console for the `llmdietplanner` component), where the prod
`DATABASE_URL`, `GEMINI_API_KEY`, and `ANTHROPIC_API_KEY` live.

```bash
# 1. Keep the canonical-ingredient dictionary ahead of the corpus (see §4).
python manage.py seed_canonical_ingredients

# 2. Curate the batch (fetch → extract JSON-LD → rewrite to Czech → map →
#    attribute → advisory judge). ~10–15 s/recipe; cost-bound with --limit.
python manage.py build_curated_recipes --index docs/curated-recipe-index-batchNN.json --limit 100 --sleep 1

# 3. Re-resolve ingredient→catalog links (no LLM cost). Run after any dict change.
python manage.py remap_curated_recipes

# 4. Vet, then promote (see §5). Only catalog-mapped recipes should go live.
```

Cost/throughput notes:
- ~1 Gemini call (rewrite) + ~1 Claude call (judge) per recipe. Batch of 100 ≈
  20–30 min wall-clock at `--sleep 1`. Use `--no-judge` for a cheaper first pass,
  then judge separately if needed.
- Resumability means a dropped console session just needs a re-run.
- For 500–1000, prefer a **PRE_DEPLOY job or a scheduled one-off job** over an
  interactive console paste, so long runs aren't tied to your terminal.

---

## 4. Co-scale the ingredient dictionary (the mapping gate)

The pilot's hardest lesson: a recipe is only eligible if its ingredients map.
The pilot lifted mapping 25% → ~95–99% by growing `CanonicalIngredient`
62 → 164 and adding a normalizing resolver. **As the corpus grows, the
dictionary must grow with it** or new recipes silently fail the gate.

Workflow each batch:
1. After `build_curated_recipes`, **measure unmapped ingredients** (ranked by
   frequency) — the same query used in the pilot:
   ```bash
   python manage.py shell -c "import collections; from diet_planner.models import CuratedRecipe; c=collections.Counter(i['name'] for r in CuratedRecipe.objects.all() for i in (r.ingredients or []) if not (i.get('canonical') or i.get('catalog_id'))); print(c.most_common(50))"
   ```
2. For each frequent miss, decide: **new `CanonicalIngredient`** (a real new
   ingredient) or **alias on an existing one** (synonym / plural / variant).
   Add to `diet_planner/data/canonical_ingredients.yaml`.
3. Re-run `seed_canonical_ingredients` + `remap_curated_recipes`, re-measure.
4. Target **≥ 95% ingredient mapping** and a healthy count of
   fully-`is_catalog_mapped` recipes per batch before promoting.

Resolver behavior to rely on (`diet_planner/services/canonical_lookup.py`):
- exact match → alias match → **normalized fallback** (strips
  parenthetical/post-comma/prepositional descriptors; order-independent
  sorted-token key). So you usually only need **one alias per genuinely distinct
  surface form**, not every grammatical variant.
- The normalized index is cached; `clear_cache()` runs automatically in
  `remap_curated_recipes`.

> When `StoreProduct` rows are populated per store, tighten the gate from
> canonical-level to actual store-catalog resolution. Until then,
> `is_catalog_mapped()` (canonical/`catalog_id`) is the pragmatic gate.

---

## 5. Vetting & promotion

Lifecycle: `draft` → `vetted` → `published`. Only **`published`** is served.

- The **coherence/clarity judge is advisory** — it annotates `quality_score`
  (verdict + issue list) but does **not** block. In the pilot most recipes came
  back `minor_issues`; that's expected and fine to publish.
- **Gate promotion on `is_catalog_mapped()`**, not on the judge verdict. A recipe
  that isn't catalog-mapped should stay `draft` (it can never be served anyway).
- **Human spot-check** a sample per batch in admin (Curated Recipes): check step
  clarity, cultural fit, and that `ingredients[]` is the real shopping basket
  (no "leftover from yesterday" items — the klizka coherence rule).
- Promote only the catalog-mapped subset. Cleanest as a short script
  (`promote.py`, run with `python manage.py shell < promote.py`):
  ```python
  from diet_planner.models import CuratedRecipe
  promoted = 0
  for r in CuratedRecipe.objects.filter(status='draft'):
      if r.is_catalog_mapped():
          r.status = 'published'
          r.save(update_fields=['status', 'updated_at'])
          promoted += 1
  print('promoted:', promoted, '| published total:',
        CuratedRecipe.objects.filter(status='published').count())
  ```
  > Prefer a small dedicated `promote_curated_recipes` management command for
  > this (TODO, see §8) so promotion is a clean, reviewable operation rather
  > than an ad-hoc script.

---

## 6. Quality gates per batch (definition of done)

Before a batch counts as "shipped":

- [ ] `build_curated_recipes`: `errors` ≈ 0 (investigate any fetch/extract fails).
- [ ] Ingredient mapping ≥ 95%; unmapped tail is genuine non-ingredients
      (brines, "fresh fruit") or rare exotics.
- [ ] Coverage matrix: the batch advances the under-filled cells (breakfast,
      snacks, vegan/gluten_free depth), not just more lunches.
- [ ] Human spot-check passed on a sample (clarity, cultural fit, shopping
      coherence, attribution present).
- [ ] No duplicate dishes vs. the existing corpus.
- [ ] Promoted set = catalog-mapped only.

Track over time: **eligible-recipe count per (slot × dietary tag)**, overall
mapping rate, and per-plan repeat rate (should fall toward zero as the corpus
grows).

---

## 7. Operational guidance

- **Idempotent + resumable** everywhere — re-running never duplicates.
- **Run in prod env** (Console or a one-off job) so writes land in prod Supabase.
- **Batch (~100)** to bound cost, keep the coverage matrix balanced, and make
  vetting tractable.
- Keep each batch's index file in `docs/` (`curated-recipe-index-batchNN.json`)
  for reproducibility and audit.
- **Multi-market:** corpus is CZ-first; SK shares the catalog. PL/other markets
  get translated or separate corpora later (the rewrite step already localizes).
- **Bonus:** published `CuratedRecipe`s can also power the public recipe SEO
  pages — real, attributed, indexable content.

---

## 8. Suggested follow-up tooling (not yet built)

- `promote_curated_recipes` command (gate on `is_catalog_mapped`, optional judge
  threshold).
- An "unmapped ingredients report" command (wraps the §4 query) to drive
  dictionary growth each batch.
- A coverage-matrix report (eligible count per slot × dietary tag) to target
  sourcing.
- A one-off DO App Platform **job** spec for large batch runs, so curation isn't
  tied to an interactive console.
