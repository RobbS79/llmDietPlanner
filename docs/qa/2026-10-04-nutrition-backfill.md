# Nutrition backfill on prod — 2026-10-04

Branch/PRs: #106 (table + engine, 579f06c), #107 (column width, fdaed40), #108 (dry-run fixes, a3aa814). Deployment d81b3427 ACTIVE 09:35 UTC.

## Runbook as executed

1. Boot seed: 335/335 canonicals with nutrition, 0 unrated (read-only probe).
2. `remap_curated_recipes`: 676 recipes, 73 mappings changed (yolk/white/whipping-cream/celery-stalk/cherry-tomatoes/corn/whole-chicken); `recompute_shopping_difficulty`: 0 further changes after the first pass (23 in the first pass before #108).
3. Recipe-line fixes: #105 "12 ks mini mozzarella kuličky" → 250 g; #201 "2 ks kapusta" → 100 g kale.
4. `recompute_nutrition --status published` dry run: 535 recipes, 527 complete, 8 incomplete.
5. `recompute_nutrition --status published --apply --skip-incomplete`: applied=527.
6. `refresh_stale_recipe_cache --apply`: checked 31, stale 25, repaired 25.

## Incomplete (kept legacy nutrition, blockers recorded)

| id | recipe | old kcal | new kcal | reason |
|---|---|---|---|---|
| 56 | Sekaná pečeně | 3876 | 3672 | implausible |
| 117 | Hummus | 161 | None | no_piece_weight |
| 192 | Salát z kadeřávku s mrkvovo-zázvor | 1600 | None | no_unit_weight |
| 426 | Superpotravinová smoothie miska s | 126 | None | no_piece_weight |
| 530 | Pečené vepřové kotlety | 1180 | None | no_piece_weight |
| 532 | Steak na pánvi s česnekovým máslem | 771 | None | no_piece_weight |
| 633 | Vietnamská polévka Pho Bo | 1850 | 5069 | implausible |
| 685 | Pečená kachna | 2900 | 8089 | implausible |

Ceiling cases (Sekaná pečeně 1 kg mince / 2 portions, Pečená kachna as-bought, Pho Bo 1.3 kg beef / 3) are real recipe-scale issues; the five `no_piece_weight`/`no_unit_weight` rows need line fixes ("1 ks pork", "1 ks beef", "2 ks water", "dávka chickpeas", kale "dávka").

## Delta distribution (527 complete)

median +12 %, within ±25 %: 312, above +50 %: 124 (legacy per-portion values replaced by whole-recipe totals; the frontend divides by `servings` via `basis: total`), below −50 %: 5.

## REVERSAL

Full old `base_nutrition` for 513 recipes is in `nutrition_reversal_2026-10-04.json` (committed next to this file). The console chunking lost 14 entries; for those only the old kcal is known (from the dry run):

| id | recipe | old kcal |
|---|---|---|
| 1 | Svíčková na smetaně | 3806 |
| 2 | Kuřecí guláš | 1040 |
| 3 | Bramboračka | 434 |
| 4 | Bramboráky | 2230 |
| 5 | Jemné tvarohové palačinky | 1110 |
| 6 | Vepřo knedlo zelo | 1713 |
| 7 | Kuřecí řízek | 769 |
| 8 | Bramborový salát | 5185 |
| 9 | Čočka na kyselo | 5149 |
| 10 | Kulajda | 1520 |
| 11 | Rajská omáčka s hovězím masem | 1268 |
| 12 | Zapečené těstoviny se šunkou | 3042 |
| 13 | Špagety Aglio e Olio | 2800 |
| 14 | Řecký salát | 1752 |

To revert a recipe: set `base_nutrition` back to the stored dict and clear `source`; then `refresh_stale_recipe_cache --apply`.

## Follow-ups
- Frying oil is counted in full (Smažený sýr 1240 kcal/portion); an absorption factor is a spec non-goal for now.
- Per-portion kcal floor is advisory since #108; the ceiling (1500) and zero kcal still block.
- `beans` = canned/drained; dry-bean lines are undercounted ~3× until a `beans-dry` canonical exists.
- Known residue: 17 published lines with no canonical (e.g. "cajunské koření", "gremolata") — optional or to-taste in most cases.
- QA 2026-10-04 (GO) follow-ups: cooked rice/pasta lines ("uvařená rýže") score at dry values (recipe 43: 727 kcal/bowl, ~376 realistic) → add `rice-cooked`/`pasta-cooked` canonicals or a cooked-state rule; SSR JSON-LD `recipeIngredient` emits "None špetka sůl" for to-taste lines (`llm_diet_planner_project/views.py` ~136, pre-existing); showcase recipe 90 cache row lacks `basis`/`nutrition_source` (not refreshed — check `refresh_stale_recipe_cache` coverage of showcase rows); QA account `qa_bot_17b32e` is at 0 free generations (re-grant before the next authed run).

## 2026-10-07 follow-up (PR #109, b4220d4)
Cooked-state canonicals (rice-cooked, brown-rice-cooked, pasta-cooked, quinoa-cooked; cooked chickpeas → chickpeas-canned), cooked-sibling resolver rule, deep-frying oil counted at 25 % when ≥ 60 g and the line says "na smažení". Runbook re-run: seed 339/339; remap changed 23 mappings; `recompute_nutrition --apply --skip-incomplete` applied=527 (same 8 incomplete); 19 published recipes changed (fried dishes down, cooked legumes/grains down), e.g. Domácí hranolky 4784 → 1778, Smažená rýže s vejcem 2909 → 1499, Chana Masala 2275 → 1128; `refresh_stale_recipe_cache --apply` repaired 4. Pre-change values for the 19 are in `nutrition_reversal_2026-10-07.json`.
