"""Audit (and optionally fix) implausible serving counts on public recipes.

The public showcase contains legacy LLM-generated Recipe rows whose `servings`
doesn't match the ingredient quantities (halušky: 1.5 kg potatoes, "1 porce").
The curation-side gate only covers CuratedRecipe; this command runs the same
plausibility check over `Recipe.objects.filter(is_public=True)` and proposes a
corrected serving count from the total weighable mass.

Dry-run by default — prints a table and changes nothing:

    python manage.py audit_recipe_servings

With --apply: fixable rows get the proposed `servings`; rows that stay
implausible even after correction are unpublished. Both go through queryset
.update() on purpose — Recipe.save() re-promotes is_public and re-derives the
slug, neither of which an audit should trigger.

    python manage.py audit_recipe_servings --apply
"""
from django.core.management.base import BaseCommand

from diet_planner.models import Recipe
from diet_planner.services.recipe_plausibility import check_portion_plausibility

# A cooked main-course portion runs ~350-700 g; 450 g is the corpus median-ish
# midpoint used to back out "how many portions do these quantities describe".
TYPICAL_PORTION_G = 450.0
MAX_PROPOSED_SERVINGS = 20  # matches the frontend portion stepper's ceiling


def normalize_weighable(ingredients):
    """kg -> g and l -> ml so the plausibility check (which only weighs g/ml)
    sees quantities LLM recipes often express in kilograms/litres."""
    normalized = []
    for ing in ingredients or []:
        if not isinstance(ing, dict):
            continue
        unit = ing.get('unit')
        unit = unit.strip().lower() if isinstance(unit, str) else ''
        if unit in ('kg', 'l'):
            try:
                quantity = float(str(ing.get('quantity')).strip().replace(',', '.')) * 1000
            except (TypeError, ValueError):
                normalized.append(ing)
                continue
            normalized.append({**ing, 'unit': 'g' if unit == 'kg' else 'ml', 'quantity': quantity})
        else:
            normalized.append(ing)
    return normalized


def propose_servings(per_portion_total_g: float, current_servings: int) -> int:
    total_g = per_portion_total_g * max(current_servings, 1)
    proposed = round(total_g / TYPICAL_PORTION_G)
    return max(1, min(proposed, MAX_PROPOSED_SERVINGS))


def audit_recipe(recipe):
    """Returns (status, detail) where status is 'ok' | 'fix' | 'unpublish'."""
    ingredients = normalize_weighable(recipe.ingredients)
    result = check_portion_plausibility(ingredients, recipe.servings)
    if result.ok:
        return 'ok', {'result': result}
    proposed = propose_servings(result.per_portion_total_g, recipe.servings)
    recheck = check_portion_plausibility(ingredients, proposed)
    if proposed != recipe.servings and recheck.ok:
        return 'fix', {'result': result, 'proposed': proposed, 'recheck': recheck}
    return 'unpublish', {'result': result, 'proposed': proposed, 'recheck': recheck}


class Command(BaseCommand):
    help = 'Flag public recipes whose servings do not match ingredient quantities; --apply fixes or unpublishes them'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true',
                            help='Write proposed servings / unpublish unfixable rows (default: report only)')

    def handle(self, *args, **options):
        apply_changes = options['apply']
        flagged = []

        for recipe in Recipe.objects.filter(is_public=True).order_by('pk'):
            status, detail = audit_recipe(recipe)
            if status == 'ok':
                continue
            flagged.append((status, recipe, detail))

        if not flagged:
            self.stdout.write(self.style.SUCCESS('All public recipes pass the servings plausibility check.'))
            return

        self.stdout.write(f'{"pk":>6}  {"action":<9} {"servings":>8} {"g/portion":>10} {"proposed":>8}  name')
        for status, recipe, detail in flagged:
            self.stdout.write(
                f'{recipe.pk:>6}  {status:<9} {recipe.servings:>8} '
                f'{detail["result"].per_portion_total_g:>10.0f} {detail.get("proposed", "-"):>8}  {recipe.name}'
            )
            for reason in detail['result'].reasons:
                self.stdout.write(f'{"":>8}- {reason}')

        fixes = [(r, d) for s, r, d in flagged if s == 'fix']
        unpublishes = [r for s, r, _ in flagged if s == 'unpublish']

        if not apply_changes:
            self.stdout.write(
                f'\nDry run: {len(fixes)} fixable, {len(unpublishes)} would be unpublished. '
                'Re-run with --apply to write.'
            )
            return

        for recipe, detail in fixes:
            Recipe.objects.filter(pk=recipe.pk).update(servings=detail['proposed'])
        if unpublishes:
            Recipe.objects.filter(pk__in=[r.pk for r in unpublishes]).update(is_public=False)

        self.stdout.write(self.style.SUCCESS(
            f'\nApplied: {len(fixes)} servings corrected, {len(unpublishes)} unpublished.'
        ))
