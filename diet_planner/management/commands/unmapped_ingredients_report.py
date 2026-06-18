"""
Report unmapped ingredient names across the CuratedRecipe corpus.

An ingredient is "unmapped" if it has neither `canonical` nor `catalog_id`
set on the recipe's stored `ingredients` JSON. The report ranks names by
frequency so the human curator can grow `data/canonical_ingredients.yaml`
against the most-impactful misses. See docs/recipe-corpus-scaling.md §4.

    python manage.py unmapped_ingredients_report
    python manage.py unmapped_ingredients_report --top 100
    python manage.py unmapped_ingredients_report --csv
    python manage.py unmapped_ingredients_report --status published
"""
import collections
import csv

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe


class Command(BaseCommand):
    help = "Frequency-rank unmapped ingredient names across CuratedRecipe."

    def add_arguments(self, parser):
        parser.add_argument('--top', type=int, default=50,
                            help="Show this many top entries (default 50).")
        parser.add_argument('--csv', action='store_true',
                            help="Emit machine-readable CSV (name,count) on stdout.")
        parser.add_argument(
            '--status',
            choices=['all', 'draft', 'vetted', 'published'],
            default='all',
            help="Limit to recipes of a given status (default: all).",
        )

    def handle(self, *args, **options):
        top = options['top']
        as_csv = options['csv']
        status = options['status']

        qs = CuratedRecipe.objects.all()
        if status != 'all':
            qs = qs.filter(status=status)

        counter: collections.Counter[str] = collections.Counter()
        recipes_with_unmapped = 0
        for r in qs.only('ingredients'):
            had_unmapped = False
            for ing in (r.ingredients or []):
                if ing.get('canonical') or ing.get('catalog_id'):
                    continue
                name = (ing.get('name') or '').strip()
                if not name:
                    continue
                counter[name] += 1
                had_unmapped = True
            if had_unmapped:
                recipes_with_unmapped += 1

        ranked = counter.most_common(top)

        if as_csv:
            writer = csv.writer(self.stdout)
            writer.writerow(['name', 'count'])
            for name, count in ranked:
                writer.writerow([name, count])
            return

        total_distinct = len(counter)
        total_occurrences = sum(counter.values())
        self.stdout.write(self.style.NOTICE(
            f"Unmapped ingredients: {total_distinct} distinct, "
            f"{total_occurrences} total occurrences, "
            f"{recipes_with_unmapped} recipes with ≥1 unmapped."
        ))
        for name, count in ranked:
            self.stdout.write(f"  {count:5d}  {name}")
