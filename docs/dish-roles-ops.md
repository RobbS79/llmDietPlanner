# Dish roles, příloha and dish families — prod runbook

Spec: `docs/superpowers/specs/2026-09-06-dish-roles-priloha-design.md`.

## What the tag pass writes
`dish_role` (main/supper/breakfast/soup/side/dessert), `meal_types`,
`side_options` (chleb/brambory/ryze/knedlik/testoviny), `dish_family`.
`light` is legacy and must reach zero.

## Order of operations
1. Deploy the code (migration 0038). Untagged and `light` rows behave as before.
2. Dry run on prod:
   `python manage.py retag_dish_roles --force --dry-run > /tmp/retag-report.txt`
   (~460 recipes / 25 per batch ≈ 19 Gemini calls, 2–3 minutes.)
3. Read the report: the "Changes" block (Czech first), the role histogram, and
   the lunch-pool block. Any lunch pool under 15 prints WARNING.
4. Disagree with a line? Add it to `diet_planner/data/dish_role_overrides.yaml`
   (`by_slug` for one recipe, `by_family` for a whole family), commit, deploy,
   repeat step 2 until the report reads right.
5. Write: `python manage.py retag_dish_roles --force`.
6. Probe (read-only): count of `dish_role='light'` must be 0; `domaci-leco`
   must be `side`; every `leco` family row must be `supper` + `[dinner]` +
   `[chleb]`.
7. Generate a QA plan asking for Czech classics; check lečo only at dinner
   with bread, never twice a day; svíčková with knedlík; the shopping list and
   deals headline include the side. Then `/qa-prod`.

## Gotchas
- `prod_run.py`'s idle drain (12 s) is shorter than a Gemini batch; use
  drain(timeout=90, total=600) or run in the DO console.
- New recipes are classified at curation; the command is only a backfill.
- The judge/Anthropic balance does not matter here — classification is Gemini.
