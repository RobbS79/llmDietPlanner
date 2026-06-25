"""
Recompute each recipe's food_category (the stock-image slug) from its name and
ingredients using the current guess_category logic.

Existing recipes were categorised at creation time, before guess_category was
changed to match the dish NAME first. That left dishes like "Kuřecí parmigiana"
(chicken) tagged 'vajicka' (eggs) because an egg in the ingredient list matched
ahead of the chicken rule. This backfills them with the corrected logic.

Read-only unless run without --dry-run.

    python manage.py recategorize_recipe_images --dry-run
    python manage.py recategorize_recipe_images
    python manage.py recategorize_recipe_images --public-only
"""
from django.core.management.base import BaseCommand

from diet_planner.food_categories import guess_category
from diet_planner.models import Recipe


class Command(BaseCommand):
    help = "Recompute Recipe.food_category from name/ingredients via guess_category."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Report what would change without writing.',
        )
        parser.add_argument(
            '--public-only', action='store_true',
            help='Only process recipes with is_public=True.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        qs = Recipe.objects.all()
        if options['public_only']:
            qs = qs.filter(is_public=True)

        total = qs.count()
        changed = []
        for recipe in qs.iterator():
            new_cat = guess_category(recipe.name, recipe.ingredients)
            if new_cat != recipe.food_category:
                changed.append((recipe.pk, recipe.name, recipe.food_category, new_cat))
                if not dry_run:
                    recipe.food_category = new_cat
                    recipe.save(update_fields=['food_category'])

        for pk, name, old, new in changed:
            self.stdout.write(f"  #{pk} {name!r}: {old or '(empty)'} -> {new}")

        verb = 'would change' if dry_run else 'changed'
        self.stdout.write(self.style.SUCCESS(
            f"\n{len(changed)}/{total} recipes {verb}."
            + (" (dry run — nothing written)" if dry_run else "")
        ))
