"""Repair the prose the availability rescue left stale.

`apply_availability_substitutions` filters `.filter(adaptation_note='')`, so
every row it has already touched is beyond its reach — and until PR #80 it
rewrote neither the prose nor the `optional` ingredient entries. This command is
the complement: it finishes rewrites the corpus has already disclosed, and it
introduces no swap the recipe does not already claim.

Nothing here rescues a recipe. The gating was settled when the row was adapted.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.services.ingredient_availability import (
    availability_index, compute_shopping_difficulty,
)
from diet_planner.services.ingredient_substitution import (
    SubstitutionPlan, apply_changes_to_ingredients, diff_applied_changes,
    disclosed_swaps, plan_substitutions, substitution_table,
)
from diet_planner.services.recipe_curation import judge_curated_recipe
from diet_planner.services.substitution_rewrite import (
    RewriteError, reset_usage, rewrite_prose, usage_snapshot,
)

_NOTE_PREFIX = 'Upraveno pro dostupnost v českých obchodech: '
_NOTE_MAX = CuratedRecipe._meta.get_field('adaptation_note').max_length


def _judge_rejected(verdict: dict) -> bool:
    """Did the judge actively reject this rewrite?

    `judge_curated_recipe` returns `JudgeVerdict.as_stats()`, which has no
    'passed' key — the same shape the rescue command reads.
    """
    if not verdict.get('ran'):
        return False
    return (verdict.get('verdict') != 'coherent'
            or bool(verdict.get('high_severity_count')))


class Command(BaseCommand):
    help = 'Repair stale prose and optional ingredient lines on adapted recipes'

    def add_arguments(self, parser):
        parser.add_argument('--slug', help='Restrict to one recipe')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--skip-judge', action='store_true',
            help='Skip the coherence judge (for offline reruns; not for prod)')

    def handle(self, *args, **options):
        reset_usage()
        repaired = skipped = failed = unjudged = 0

        qs = CuratedRecipe.objects.exclude(adaptation_note='').order_by('id')
        if options['slug']:
            qs = qs.filter(slug=options['slug'])

        for recipe in qs.iterator():
            if options['limit'] is not None and repaired >= options['limit']:
                break
            skipped += 1

        summary = f'repaired={repaired} skipped={skipped} failed={failed}'
        if unjudged:
            summary += f' unjudged={unjudged}'
        self.stdout.write(self.style.SUCCESS(summary))
