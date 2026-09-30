"""Re-derive cached Recipe rows stranded by a corpus revision.

`Recipe` rows are a write-once cache built from the meal dict on the first
recipe-detail GET. Nothing invalidates them when curation later corrects the
`CuratedRecipe` they came from, so rows accumulate whose stored nutrition
matches neither the whole-recipe total nor the per-portion value implied by the
current corpus (5 of 30 curated multi-portion rows on prod, 2026-08-07).

Staleness is a broken invariant, not a timestamp: a healthy row satisfies

    nutritional_info.calories  ==  per-portion calories x servings

which is exactly what the per-portion display relies on. Rows violating it were
cached against different `base_servings`/`base_nutrition` than the corpus now
holds, and no amount of dividing at display time can recover the right number.

Repair re-renders the meal through `render_curated_meal` (the serving path:
side dish, basis/servings keys and all) against the slot's DEFAULT calorie
target, not the plan's own stored calories — those are the stale data being
repaired.

Dry-run by default; prints a table and changes nothing:

    python manage.py refresh_stale_recipe_cache

With --apply, each stale row is rewritten in place from the current corpus,
along with its plan position (pool or legacy day grid) so the two cannot disagree:

    python manage.py refresh_stale_recipe_cache --apply [--goal-id N]
"""
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import DietaryPlan, Recipe
from diet_planner.models.curated import CuratedRecipe
from diet_planner.services.meal_locator import (
    LIST_KEY_FOR_TYPE,
    locate_meal,
    parse_meal_identifier,
    plan_meals_field,
    set_meal,
)
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.recipe_retrieval import (
    _SLOT_DEFAULT_KCAL,
    per_portion_calories,
    render_curated_meal,
    required_tags_for_goal,
)

# Rounding through int()/_fmt_grams means an exact match is not expected.
TOLERANCE = 0.02

# Plural day-dict list keys -> the singular slot type they hold.
_TYPE_FOR_LIST_KEY = {v: k for k, v in LIST_KEY_FOR_TYPE.items()}


def expected_calories(curated: CuratedRecipe, servings) -> Optional[float]:
    """What a healthy row's stored calories would be: one portion x servings."""
    per_portion = per_portion_calories(curated)
    if per_portion is None:
        return None
    return per_portion * max(int(servings or 1), 1)


def is_stale(row: Recipe, curated: CuratedRecipe, tolerance: float = TOLERANCE) -> bool:
    """True when the row's nutrition can't be explained by the current corpus.
    Rows with no stored or no curated calories are left alone — absent data is
    not evidence of drift."""
    expected = expected_calories(curated, row.servings)
    stored = (row.nutritional_info or {}).get('calories')
    if expected is None or not isinstance(stored, (int, float)) or stored <= 0:
        return False
    return abs(stored - expected) > max(2.0, tolerance * expected)


def slot_key_for(meal_type: str) -> str:
    """Plan meal_type -> the slot key `_SLOT_DEFAULT_KCAL` is keyed by
    (accepts the plural list spelling too)."""
    return _TYPE_FOR_LIST_KEY.get(meal_type, meal_type)


def rebuild_meal(curated: CuratedRecipe, row: Recipe, meal_type: str, table=None):
    """The meal this position should hold given the current corpus, rendered
    exactly as the serving path renders it (side included). Portioned to the
    slot-type default target: the plan's own calories are what we're
    repairing, so they cannot also be the yardstick."""
    meal, _gap = render_curated_meal(
        curated,
        target_kcal=_SLOT_DEFAULT_KCAL.get(slot_key_for(meal_type)),
        required_tags=required_tags_for_goal(row.dietary_goal),
        table=table,
    )
    meal['meal_identifier'] = row.meal_identifier
    return meal


def _position_holds(plan: DietaryPlan, ref, slug: str) -> bool:
    """Whether the plan position `ref` still holds the curated recipe `slug`."""
    current = locate_meal(plan, ref)
    return current is not None and current.get('curated_recipe_slug') == slug


class Command(BaseCommand):
    help = 'Re-derive cached Recipe rows whose nutrition no longer matches the curated corpus.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write the repairs (default: dry-run).')
        parser.add_argument('--goal-id', type=int, default=None,
                            help='Restrict to one dietary goal.')

    def handle(self, *args, **options):
        # Imported here: views pulls in DRF and the URL conf, which a management
        # command has no reason to load at import time.
        from diet_planner.views import _recipe_cache_fields

        apply_changes = options['apply']
        rows = Recipe.objects.exclude(curated_recipe_slug='')
        if options['goal_id']:
            rows = rows.filter(dietary_goal_id=options['goal_id'])

        by_slug = {c.slug: c for c in CuratedRecipe.objects.filter(
            slug__in=rows.values_list('curated_recipe_slug', flat=True))}

        table = nutrition_table()  # once per run: side nutrients
        checked = stale = repaired = orphaned = unparseable = moved = 0

        for row in rows.select_related('dietary_goal').order_by('id'):
            checked += 1
            curated = by_slug.get(row.curated_recipe_slug)
            if curated is None:
                orphaned += 1
                self.stdout.write(self.style.WARNING(
                    f'  orphan  {row.meal_identifier}  "{row.name}"  '
                    f'-> no CuratedRecipe with slug {row.curated_recipe_slug!r}'))
                continue
            if not is_stale(row, curated):
                continue

            stale += 1
            try:
                ref = parse_meal_identifier(row.meal_identifier)
            except ValueError:
                unparseable += 1
                self.stdout.write(self.style.WARNING(
                    f'  skip    {row.meal_identifier}  "{row.name}"  '
                    f'-> unparseable meal identifier'))
                continue

            # The position may since hold a different dish (a swap, a
            # regenerated pool): never overwrite someone else's meal. Checked
            # in the dry run too, so its "repairable" count matches --apply.
            plan = DietaryPlan.objects.filter(dietary_goal_id=row.dietary_goal_id).first()
            if plan is not None and not _position_holds(plan, ref, curated.slug):
                moved += 1
                self.stdout.write(self.style.WARNING(
                    f'  moved   {row.meal_identifier}  "{row.name}"  '
                    f'-> plan position no longer holds {curated.slug!r}, skipped'))
                continue

            meal = rebuild_meal(curated, row, ref.slot, table)
            old_cal = (row.nutritional_info or {}).get('calories')
            new_cal = (meal.get('nutritional_info') or {}).get('calories')
            self.stdout.write(
                f'  stale   {row.meal_identifier}  "{row.name}"  '
                f'{row.servings}x {old_cal} kcal -> {meal["servings"]}x {new_cal} kcal')

            if not apply_changes:
                repaired += 1  # would repair
                continue

            with transaction.atomic():
                plan = DietaryPlan.objects.select_for_update().filter(
                    dietary_goal_id=row.dietary_goal_id).first()
                if plan is not None and not _position_holds(plan, ref, curated.slug):
                    # Changed between the check above and this write.
                    moved += 1
                    continue
                if plan is not None and set_meal(plan, ref, meal):
                    # Pool writes stamp the canonical identifier; keep the
                    # row's own string (differs only for legacy 3-part ids).
                    meal['meal_identifier'] = row.meal_identifier
                    plan.save(update_fields=[plan_meals_field(plan)])
                # .update(), not .save(): Recipe.save() re-promotes is_public and
                # re-derives the slug, neither of which a repair should trigger.
                # Cooked state is deliberately NOT reset — the dish is unchanged,
                # only the amounts were wrong.
                Recipe.objects.filter(pk=row.pk).update(
                    **_recipe_cache_fields(meal, meal.get('instructions', [])))
                repaired += 1

        summary = (f'checked {checked}, stale {stale}, '
                   f'{"repaired" if apply_changes else "repairable"} {repaired}, '
                   f'orphaned {orphaned}, unparseable {unparseable}, moved {moved}')
        self.stdout.write(self.style.SUCCESS(summary) if apply_changes else summary)
        if not apply_changes and repaired:
            self.stdout.write('Dry run — re-run with --apply to write these repairs.')
