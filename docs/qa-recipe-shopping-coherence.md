# QA Senior Engineer — Recipe ↔ Shopping List Coherence

> **Audience.** A senior QA engineer responsible for the meal-plan output
> seen by paying customers. This document defines who that person is,
> what they own, the specific class of bugs they must hunt, and a
> reusable test runbook they execute on every release and on every
> reported "the recipe says X but the shopping list says Y" complaint.

---

## 1. Why this role exists

On 2026-06-11 a paying user opened plan `108`, recipe
`108:1:dinner:0`, and saw a contradiction in our own output:

- **Recipe text:** "the beef (*klizka*) is already prepared"
- **Shopping list:** "buy 300 g *klizka*"

We charged the user for an ingredient our own recipe said they already
had. The user's words: _"talking rubbish... the paying users would be
pissed off. I am pissed off."_ That is a P0 trust failure, not a cosmetic
bug. We need a senior QA owner because:

1. The LLM produces two coupled artefacts (the meal plan and the
   shopping list) in two separate calls. Each call can be locally
   correct and still produce a globally inconsistent output.
2. Automated unit tests cover code paths, not semantic agreement
   between two LLM outputs in seven languages.
3. The cost of one missed regression is a refund + churned customer +
   negative review. The cost of catching it pre-release is one human
   hour.

## 2. Role definition

**Title:** Senior QA Engineer — LLM Output Coherence.

**Reports to:** Engineering lead, with a dotted line to the founder
(every P0 from this surface goes straight to the founder).

**Owns:**

- The "is this plan self-consistent?" gate before any plan is exposed
  to a paying customer.
- The multilingual phrase catalogue in
  `diet_planner/services/recipe_coherence.py` (`_PRE_PREPARED_PHRASES`).
  Owning means: when a new bug report comes in mentioning a phrase we
  didn't catch, this person adds the phrase, ships a test, and ships
  the fix in the same PR.
- The runbook in §5 below. Reviews and updates it every quarter.
- The "QA evidence" appendix attached to every release PR — a one-page
  PDF / Slack thread showing which scenarios were exercised and the
  pass/fail.

**Does not own:** the LLM prompt itself (that is engineering), the
pricing logic, or the UI templates. They file bugs against those
owners; they do not patch them without a code-owner review.

## 3. Mental model the QA person must internalise

The product has **two LLM artefacts**, generated in two sequential
calls, that **must agree**:

| Artefact | Source | Field on disk |
|---|---|---|
| Meal plan | Phase-1 Gemini call | `DietaryPlan.days[*].{breakfast,lunch,dinner,...}` |
| Shopping list | Phase-2 Gemini call seeded from Phase-1 ingredients | `DietaryPlan.shopping_list` |

The contract between them is **purely textual** — there is no foreign
key, no schema constraint, nothing that forces the two to agree. So
"coherence" is something we have to *check*, not something we can
*declare*.

The canonical incoherence patterns the QA person hunts for:

1. **Pre-prepared ingredient on shopping list.** Recipe says "already
   prepared / leftover / from yesterday / pre-cooked" — shopping list
   charges for it. This is the *klizka* bug.
2. **Ingredient in shopping list never referenced by any recipe.**
   User is paying for something no meal uses.
3. **Recipe ingredient missing from shopping list.** User opens the
   fridge and discovers they don't have what the recipe needs.
4. **Quantity drift.** Recipe says 300 g, shopping list says 100 g.
5. **Unit drift.** Recipe says litres, shopping list says ml.
6. **Language drift.** Recipe in Czech, shopping list item in English
   (`"chicken"` instead of `"kuře"`).
7. **Currency / locale drift.** Czech plan priced in EUR.

This document focuses on (1). The same skeleton applies to the others.

## 4. Automated guardrails this role relies on

The QA person doesn't replace automation — they verify it. The hooks
already in the codebase are:

- **`diet_planner/services/recipe_coherence.py`**
  - `detect_pre_prepared_ingredient_names(meal)` — multilingual phrase
    scanner.
  - `filter_pre_prepared(meal)` — used by `RecipeDetailView` so cached
    and freshly-generated recipes never display a "buy klizka" line
    when the description says it's already prepared.
  - `find_coherence_issues(days, shopping_list)` — used by
    `MealPlanValidator` as a **hard error** (not warning).
- **`diet_planner/services/validation.py:MealPlanValidator.validate()`**
  emits one error per detected conflict and refuses to mark the plan
  `is_valid_for_checkout`.
- **`diet_planner/services/shopping_list.py:_extract_ingredients_from_meal_plan`**
  skips pre-prepared ingredients before the Phase-2 LLM ever sees them.
- **`diet_planner/llm_service.py:generate_meal_plan_only`** — Phase-1
  system prompt now contains an explicit `INGREDIENT CONSISTENCY` rule.
- **`diet_planner/tests/test_recipe_coherence.py`** — 16 unit tests
  including the literal *klizka* case, in cs / sk / pl / hu / ro / bg /
  de / en.

### 4a. The semantic "simulated human" judge (cross-model, advisory)

The phrase-matchers above are precise but blind to anything they have no
pattern for. `diet_planner/services/recipe_human_judge.py` adds the layer a
regex can't: it sends the plan, the individual recipes, and the shopping
list to **Claude** (a *different* model family from Gemini, which writes the
plans — cross-model review catches blind spots a model has in its own
output) and asks it to read everything the way a paying customer would. It
answers three human questions and returns structured findings:

1. **Shoppable** — "If I buy exactly what's on this list (across whatever
   shops it spans), will I then have what every recipe needs? Anything on
   the list no recipe uses? Anything a recipe needs that's missing?"
2. **Cookable** — "Does each recipe actually tell me *how* to make the
   food — real steps, not just an ingredient dump?" This is the
   **"it doesn't tell the user how to prepare the food"** failure mode: a
   recipe that lost its instructions is incoherent even if every ingredient
   and price is correct.
3. **Humanly sane** — no *"eat 1 piece of chocolate bar"* non-meals, no
   absurd quantities, no wrong-language items.

Properties the QA person must know:

- **Advisory, not blocking — today.** `MealPlanValidator` surfaces the
  judge's findings as **warnings** (with a `stats['human_judge']` summary),
  never as `is_valid_for_checkout` errors. This is deliberate: we measure
  the false-positive rate before promoting any of it to a hard gate.
- **Fail-open.** A disabled judge, a missing `ANTHROPIC_API_KEY`, a missing
  `anthropic` SDK, an API error, or a model refusal all return
  `ran == False` and change nothing. Plan generation never breaks because
  of the judge.
- **Off by default.** Enable with `RECIPE_HUMAN_JUDGE_ENABLED=true` and an
  `ANTHROPIC_API_KEY`. Model is `RECIPE_HUMAN_JUDGE_MODEL` (default
  `claude-opus-4-8`). A `JudgeVerdict` with `ran == False` means *unknown*,
  **not** *good* — never read a "coherent" verdict as a pass without
  checking `ran` first.
- **Tested** in `diet_planner/tests/test_recipe_human_judge.py` (Anthropic
  API mocked — serialization, gating, fail-open, verdict parsing). The
  *quality* of Claude's judgement is exercised manually via §5.4, not CI.

Failure mode the QA person watches for: **the validator detects an
issue but the meal plan ships anyway**. `MealPlanValidator` is now wired
into the production Celery task path (`tasks.py`, right before
`DietaryPlan.objects.create`) — it runs the deterministic checks *and* the
semantic judge on every generated plan. **But it runs in advisory mode:**
errors and warnings are logged (grep the task logs for "Coherence
validation" and "Human-judge verdict"), and the plan still ships. So the
plan *can* still reach the customer with a logged conflict — the QA person
watches the logs and still runs §5.3 on flagged plans until the validator
is promoted to a hard checkout block (§7).

## 5. Runbook

### 5.1 On every PR that touches Phase-1, Phase-2, the validator, or any prompt

1. Pull the branch, run:
   ```
   python manage.py test diet_planner.tests.test_recipe_coherence
   ```
   Must be green.
2. Generate three plans against staging, one per language family we
   most often see bug reports in (cs, pl, de):
   - 7-day plan, breakfast + lunch + dinner, omnivore.
   - 5-day plan with "use leftovers where possible" in the user
     prompt (this is the prompt shape that triggers the *klizka* bug).
   - 3-day plan with a professional protocol attached.
3. For each generated plan, run §5.3 below.

### 5.2 On every customer complaint mentioning "the recipe doesn't match"

1. Reproduce on the user's actual plan ID (read-only DB access). Take
   a screenshot of the recipe and the shopping list side by side.
2. Run §5.3.
3. If the conflict is a new phrase not in `_PRE_PREPARED_PHRASES`,
   file a one-line PR adding it + a test case quoting the exact user
   sentence. SLA: 24 h.
4. Refund the user before merging the fix. The fix proves we listened;
   the refund proves we are accountable.

### 5.3 The 10-minute coherence sweep for a single plan

Run this from a Django shell pointed at the relevant database.

```python
from diet_planner.models import DietaryPlan
from diet_planner.services.recipe_coherence import find_coherence_issues
from diet_planner.services.validation import MealPlanValidator

plan = DietaryPlan.objects.get(id=<PLAN_ID>)
issues = find_coherence_issues(plan.days, plan.shopping_list)
print("conflicts:", len(issues))
for i in issues:
    print(i)

result = MealPlanValidator().validate(
    {"days": plan.days},
    plan.shopping_list,
    {"num_days": plan.dietary_goal.num_days},
)
print("passed:", result.passed)
for e in result.errors: print("ERROR:", e)
for w in result.warnings: print("warn:", w)
```

Then for each recipe ID returned, hit the production URL
`https://<host>/plan/<plan_id>/recipe/<plan_id>:<day>:<meal_type>:<idx>`
in a real browser, **with a logged-in user account in the same
language as the plan**, and visually confirm:

- The ingredient list does not contain any item the description /
  instructions describe as already prepared / leftover.
- Every ingredient shown in the recipe is on the shopping list (modulo
  pre-prepared items, which are intentionally excluded).
- The quantities are within 20 % of each other.

### 5.4 Red-team prompts

These prompts are designed to *try* to trigger the bug. The QA person
runs them periodically (monthly) and on every Gemini model bump.

| # | User prompt (in target language) | What we expect to see |
|---|---|---|
| 1 | "Plán na 5 dní. Pondělí udělej hovězí na cibulce. Úterý použij zbytek hovězího z pondělí ve studeném salátu." | Tuesday salad must NOT have klizka / hovězí on its shopping line. |
| 2 | "Plan zdrowy 7 dni. We wtorek wykorzystaj resztki kurczaka z poniedziałku." | Tuesday meal description mentions leftover chicken; shopping list has no extra chicken for Tuesday. |
| 3 | "7-Tage-Plan. Am Mittwoch verwende Rindfleisch vom Vortag." | Wednesday recipe description: pre-prepared beef; shopping list has no Wednesday beef. |
| 4 | English: "Generate a 4-day plan and reuse leftovers from yesterday wherever possible." | At least one description contains "leftover" / "from yesterday"; no overlap in shopping list. |

If any of these fails: file P0, add the phrase to
`_PRE_PREPARED_PHRASES`, ship the regression test, hold the release.

### 5.5 Evidence the QA person attaches to every release

A markdown table pasted in the release PR:

```
| Plan ID | Language | find_coherence_issues | Validator | Manual UI check | Notes |
|---------|----------|-----------------------|-----------|-----------------|-------|
|  ...    | cs       | 0                     | passed    | OK              |       |
```

If any cell is not "OK / passed / 0", the release is blocked until the
owning engineer responds in writing.

## 6. KPIs for this role

- **Mean time to add a missed phrase pattern:** < 24 h from the user
  report.
- **Releases blocked by §5.5:** track over time. Goal: trend downward
  as the LLM prompt improves.
- **Customer complaints in the "recipe / shopping list mismatch"
  bucket per 1000 plans:** track weekly. Goal: < 0.5 / 1000.

## 7. Open follow-ups (for engineering, not QA)

1. ~~Wire `MealPlanValidator` into the production Celery task so a plan
   that fails the coherence check is caught.~~ **Done** — the validator now
   runs in `tasks.py` on every generated plan, in *advisory* mode (logs
   only). The remaining step is to make it **blocking**: on a failed
   deterministic check (or a high-severity judge verdict), hold the plan
   for review / refund instead of marking the goal `COMPLETED`. See item 5.
2. Backfill cached `Recipe` rows generated before this fix shipped —
   either re-run them through `filter_pre_prepared` and re-save, or
   simply invalidate them so they are regenerated on next view.
3. Add a `Recipe.pre_prepared_ingredients` JSONField and a migration
   so the UI can render "uses leftover beef from yesterday" as a
   first-class section instead of inferring it from a key on the API
   response.
4. Extend the same coherence module to the other six incoherence
   patterns listed in §3. (Partly addressed by the semantic judge in §4a,
   which already covers cookability, non-meals, and orphan/missing items —
   but only in *advisory* mode.)
5. Promote the semantic judge (§4a) from advisory to a hard gate once its
   false-positive rate is measured and acceptable: feed a high-severity
   verdict into `is_valid_for_checkout` so an incoherent plan never reaches
   a paying customer. Track precision/recall against §5.4 red-team runs
   before flipping it on as a blocker.

---

_Last reviewed: 2026-06-11. Next review due: 2026-09-11._
