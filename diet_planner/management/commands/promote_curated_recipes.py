"""
Promote draft CuratedRecipe rows to status=published.

Only catalog-mapped drafts are promoted (is_catalog_mapped() == True);
others remain draft and are never served by retrieval. Idempotent —
already-published rows are untouched. See docs/recipe-corpus-scaling.md §5
and §8.

    python manage.py promote_curated_recipes
    python manage.py promote_curated_recipes --dry-run
    python manage.py promote_curated_recipes --min-judge-verdict minor_issues
"""
from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


JUDGE_VERDICT_ORDER = {
    'incoherent': 0,
    'unknown': 1,
    'minor_issues': 2,
    'coherent': 3,
}


class Command(BaseCommand):
    help = "Promote catalog-mapped CuratedRecipe drafts to status=published."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Print what would promote; do not modify any rows.",
        )
        parser.add_argument(
            '--min-judge-verdict',
            choices=['incoherent', 'unknown', 'minor_issues', 'coherent'],
            default=None,
            help="If set, also require quality_score.verdict to be at least this level "
                 "(coherent > minor_issues > unknown > incoherent).",
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        min_verdict = options['min_judge_verdict']
        min_rank = JUDGE_VERDICT_ORDER[min_verdict] if min_verdict else None

        drafts = CuratedRecipe.objects.filter(status=CuratedRecipe.Status.DRAFT).order_by('id')
        promoted = skipped_unmapped = skipped_judge = 0

        for r in drafts:
            if not r.is_catalog_mapped():
                skipped_unmapped += 1
                continue
            if min_rank is not None:
                v = (r.quality_score or {}).get('verdict', 'unknown')
                if JUDGE_VERDICT_ORDER.get(v, 0) < min_rank:
                    skipped_judge += 1
                    continue
            if not dry_run:
                r.status = CuratedRecipe.Status.PUBLISHED
                r.save(update_fields=['status', 'updated_at'])
            promoted += 1

        published_total = CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED,
        ).count()
        prefix = '[dry-run] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(
            f"{prefix}promoted={promoted} skipped_unmapped={skipped_unmapped} "
            f"skipped_judge={skipped_judge} published_total={published_total}"
        ))
