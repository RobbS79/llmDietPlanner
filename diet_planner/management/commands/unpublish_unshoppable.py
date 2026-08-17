"""Demote published recipes you still cannot shop for in a Czech supermarket.

Draft, never delete: shopping_blockers records exactly why each one went, so a
future substitution table or a wider bar can bring it straight back.
"""
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.models.catalog import Availability


class Command(BaseCommand):
    help = 'Move specialty-difficulty published recipes to draft.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')

    def handle(self, *args, **options):
        qs = CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED,
            shopping_difficulty=Availability.SPECIALTY,
        ).order_by('slug')

        demoted = 0
        for recipe in qs.iterator():
            demoted += 1
            self.stdout.write(
                f'  {recipe.slug}: {", ".join(recipe.shopping_blockers or [])}')
            if not options['dry_run']:
                recipe.status = CuratedRecipe.Status.DRAFT
                recipe.save(update_fields=['status', 'updated_at'])

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(f'{prefix}demoted={demoted}'))
