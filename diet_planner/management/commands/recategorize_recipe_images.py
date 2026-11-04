"""Re-derive Recipe.food_category with today's guess_category.

Dry run by default; --apply writes. Prints `<id> <name>: old -> new` per change
so the run doubles as its own reversal record.
"""
from django.core.management.base import BaseCommand

from diet_planner.food_categories import guess_category
from diet_planner.models import Recipe


class Command(BaseCommand):
    help = (
        'Fix stale Recipe.food_category values (wrong stock photo). Dry run unless --apply. '
        'Note: a per-dish image (food_images.has_dish_image(slug)) takes precedence over '
        'the category photo, so recipes with a dish image look right either way.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write the changes (default: dry run).')
        parser.add_argument('--public-only', action='store_true', help='Only process recipes with is_public=True.')
        # Kept so old invocations still parse; dry run is now the default anyway.
        parser.add_argument('--dry-run', action='store_true', help='No-op (dry run is the default).')

    def handle(self, *args, apply=False, public_only=False, **opts):
        changed = 0
        qs = Recipe.objects.filter(is_public=True) if public_only else Recipe.objects.all()
        for r in qs.only('id', 'name', 'food_category', 'ingredients').iterator():
            new = guess_category(r.name, r.ingredients or [])
            if new and new != r.food_category:
                changed += 1
                self.stdout.write(f'{r.id} {r.name}: {r.food_category} -> {new}')
                if apply:
                    Recipe.objects.filter(pk=r.pk).update(food_category=new)
        self.stdout.write(f"{'Applied' if apply else 'Dry run'}: {changed} change(s).")
