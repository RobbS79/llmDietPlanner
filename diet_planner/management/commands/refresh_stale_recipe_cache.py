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

Repair re-portions the meal against the slot's DEFAULT calorie target, not the
plan's own stored calories — those are the stale data being repaired.

Dry-run by default; prints a table and changes nothing:

    python manage.py refresh_stale_recipe_cache

With --apply, each stale row is rewritten in place from the current corpus,
along with its plan slot so the two cannot disagree:

    python manage.py refresh_stale_recipe_cache --apply [--goal-id N]
"""
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import DietaryPlan, Recipe
from diet_planner.models.curated import CuratedRecipe
from diet_planner.services.recipe_retrieval import (
    per_portion_calories,
    portions_for_target,
    scale_recipe_to_meal,
    slot_target,
)

# Rounding through int()/_fmt_grams means an exact match is not expected.
TOLERANCE = 0.02

_LIST_SLOTS = {'small_meals': 'small_meal', 'snacks': 'snack'}


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
    """Plan meal_type -> the slot key `slot_target` keys its defaults by."""
    return _LIST_SLOTS.get(meal_type, meal_type)


def rebuild_meal(curated: CuratedRecipe, meal_identifier: str, day_number: int, meal_type: str):
    """The meal this slot should hold given the current corpus. Portioned to the
    slot-type default target: the plan's own calories are what we're repairing,
    so they cannot also be the yardstick."""
    target = slot_target(None, day_number, slot_key_for(meal_type))
    meal = scale_recipe_to_meal(curated, portions=portions_for_target(curated, target))
    meal['meal_identifier'] = meal_identifier
    return meal


def _write_plan_slot(plan: DietaryPlan, day_number: int, meal_type: str, meal) -> bool:
    """Replace the slot in plan.days. Returns whether anything was written."""
    day = next((d for d in (plan.days or []) if d.get('day_number') == day_number), None)
    if not isinstance(day, dict):
        return False
    if meal_type in _LIST_SLOTS:
        entries = day.get(meal_type) or []
        for i, existing in enumerate(entries):
            if isinstance(existing, dict) and \
                    existing.get('meal_identifier') == meal['meal_identifier']:
                entries[i] = meal
                day[meal_type] = entries
                return True
        return False
    if not isinstance(day.get(meal_type), dict):
        return False
    day[meal_type] = meal
    return True


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
        from diet_planner.views import _parse_meal_identifier, _recipe_cache_fields

        apply_changes = options['apply']
        rows = Recipe.objects.exclude(curated_recipe_slug='')
        if options['goal_id']:
            rows = rows.filter(dietary_goal_id=options['goal_id'])

        by_slug = {c.slug: c for c in CuratedRecipe.objects.filter(
            slug__in=rows.values_list('curated_recipe_slug', flat=True))}

        checked = stale = repaired = orphaned = unparseable = 0

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
                _, day_number, meal_type = _parse_meal_identifier(row.meal_identifier)
            except (ValueError, IndexError):
                unparseable += 1
                self.stdout.write(self.style.WARNING(
                    f'  skip    {row.meal_identifier}  "{row.name}"  '
                    f'-> unparseable meal identifier'))
                continue

            meal = rebuild_meal(curated, row.meal_identifier, day_number, meal_type)
            old_cal = (row.nutritional_info or {}).get('calories')
            new_cal = (meal.get('nutritional_info') or {}).get('calories')
            self.stdout.write(
                f'  stale   {row.meal_identifier}  "{row.name}"  '
                f'{row.servings}x {old_cal} kcal -> {meal["servings"]}x {new_cal} kcal')

            if not apply_changes:
                continue

            with transaction.atomic():
                plan = DietaryPlan.objects.filter(
                    dietary_goal_id=row.dietary_goal_id).first()
                if plan is not None and _write_plan_slot(plan, day_number, meal_type, meal):
                    plan.save(update_fields=['days'])
                # .update(), not .save(): Recipe.save() re-promotes is_public and
                # re-derives the slug, neither of which a repair should trigger.
                # Cooked state is deliberately NOT reset — the dish is unchanged,
                # only the amounts were wrong.
                Recipe.objects.filter(pk=row.pk).update(
                    **_recipe_cache_fields(meal, meal.get('instructions', [])))
            repaired += 1

        summary = (f'checked {checked}, stale {stale}, '
                   f'{"repaired" if apply_changes else "repairable"} {repaired if apply_changes else stale}, '
                   f'orphaned {orphaned}, unparseable {unparseable}')
        self.stdout.write(self.style.SUCCESS(summary) if apply_changes else summary)
        if not apply_changes and stale:
            self.stdout.write('Dry run — re-run with --apply to write these repairs.')
