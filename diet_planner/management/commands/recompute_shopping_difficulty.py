"""Recompute CuratedRecipe.shopping_difficulty / shopping_blockers.

Walks every status, not just published: drafts must be correct the moment
they are promoted. Writes nothing else.
"""
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services.ingredient_availability import (
    availability_index,
    compute_shopping_difficulty,
)


class Command(BaseCommand):
    help = 'Recompute the shopping-difficulty rollup for every curated recipe.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')

    def handle(self, *args, **options):
        index = availability_index()
        changed = 0
        total = 0

        for r in CuratedRecipe.objects.all().only(
            'id', 'slug', 'ingredients', 'shopping_difficulty', 'shopping_blockers',
        ).iterator():
            total += 1
            tier, blockers = compute_shopping_difficulty(r, index=index)
            if r.shopping_difficulty == tier and (r.shopping_blockers or []) == blockers:
                continue
            changed += 1
            if not options['dry_run']:
                r.shopping_difficulty = tier
                r.shopping_blockers = blockers
                r.save(update_fields=[
                    'shopping_difficulty', 'shopping_blockers', 'updated_at'])

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}recipes={total} changed={changed}'))
