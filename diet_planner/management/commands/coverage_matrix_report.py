"""
Report the eligible-published CuratedRecipe count per (meal slot x dietary tag)
cell. Eligibility mirrors the retrieval hard gate in
`select_recipes_for_plan`: status=published, slot in meal_types,
dietary_tags ⊇ {tag}, and is_catalog_mapped().

The intent: verify a balanced corpus before/after each curation batch.
The B2 push target is ≥15–20 recipes per cell — see
docs/recipe-corpus-scaling.md §1.

    python manage.py coverage_matrix_report
    python manage.py coverage_matrix_report --csv
    python manage.py coverage_matrix_report --include-drafts
"""
import csv

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


SLOTS = ['breakfast', 'lunch', 'dinner', 'small_meal', 'snack']
DIETARY_TAGS = [
    'none',  # synthetic — no dietary restriction
    'vegetarian',
    'vegan',
    'gluten_free',
    'dairy_free',
    'low_carb',
    'high_protein',
]


class Command(BaseCommand):
    help = "Eligible-published CuratedRecipe count per (slot x dietary tag)."

    def add_arguments(self, parser):
        parser.add_argument('--csv', action='store_true',
                            help="Emit machine-readable CSV on stdout.")
        parser.add_argument(
            '--include-drafts', action='store_true',
            help="Count drafts and vetted too (debug aid; default published-only).",
        )

    def handle(self, *args, **options):
        as_csv = options['csv']
        include_drafts = options['include_drafts']

        qs = CuratedRecipe.objects.all().order_by('id')
        if not include_drafts:
            qs = qs.filter(status=CuratedRecipe.Status.PUBLISHED)

        # Pre-filter on is_catalog_mapped() in Python (it walks the JSON).
        eligible = [r for r in qs if r.is_catalog_mapped()]

        # Build the 2-D count grid.
        grid = {slot: {tag: 0 for tag in DIETARY_TAGS} for slot in SLOTS}
        for r in eligible:
            slots = r.meal_types or []
            tags = set(r.dietary_tags or [])
            for slot in slots:
                if slot not in grid:
                    continue
                # The synthetic 'none' column counts recipes with no dietary tag.
                if not tags:
                    grid[slot]['none'] += 1
                for tag in DIETARY_TAGS:
                    if tag == 'none':
                        continue
                    if tag in tags:
                        grid[slot][tag] += 1

        if as_csv:
            writer = csv.writer(self.stdout)
            writer.writerow(['slot'] + DIETARY_TAGS + ['total'])
            for slot in SLOTS:
                row = [grid[slot][tag] for tag in DIETARY_TAGS]
                writer.writerow([slot] + row + [sum(row)])
            return

        # Human-readable text grid.
        col_w = 12
        header = f"{'slot':<12}" + "".join(f"{tag:>{col_w}}" for tag in DIETARY_TAGS) \
                 + f"{'total':>{col_w}}"
        self.stdout.write(self.style.NOTICE(header))
        self.stdout.write('-' * len(header))
        for slot in SLOTS:
            row = [grid[slot][tag] for tag in DIETARY_TAGS]
            line = f"{slot:<12}" + "".join(f"{v:>{col_w}}" for v in row) \
                   + f"{sum(row):>{col_w}}"
            self.stdout.write(line)
        self.stdout.write('')
        self.stdout.write(
            f"Total eligible recipes: {len(eligible)}"
        )
