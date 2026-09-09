"""Copy the demand map onto CuratedRecipe rows (all statuses).

Idempotent: every run recomputes every row, so a recipe whose term vanished
from the map goes back to blank. Tier-2 (name) attaches are printed so the
owner can pin mistakes into data/demand_overrides.yaml and re-run.
"""
import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import CuratedRecipe
from diet_planner.services.demand_map import (
    DEFAULT_MAP, DEFAULT_OVERRIDES, load_demand_map, load_overrides, match_demand_term,
)


class Command(BaseCommand):
    help = 'Attach demand terms, scores and peak months to curated recipes.'

    def add_arguments(self, parser):
        parser.add_argument('--map', default=str(DEFAULT_MAP))
        parser.add_argument('--overrides', default=str(DEFAULT_OVERRIDES))
        parser.add_argument('--ratings', default=None,
                            help='JSON list of {slug, score}; sets owner_rating (1-5).')
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        terms = load_demand_map(Path(options['map']))
        overrides = load_overrides(Path(options['overrides']))
        dry = options['dry_run']

        ratings = {}
        if options['ratings']:
            p = Path(options['ratings'])
            if not p.exists():
                raise CommandError(f'ratings file not found: {p}')
            for row in json.loads(p.read_text(encoding='utf-8')):
                score = int(row.get('score') or 0)
                if row.get('slug') and 1 <= score <= 5:
                    ratings[row['slug']] = score

        how_counts = Counter()
        attached = changed = rated = 0
        for recipe in CuratedRecipe.objects.all().order_by('slug'):
            term, how = match_demand_term(recipe, terms, overrides)
            how_counts[how or 'none'] += 1
            new = dict(
                demand_term=term.term if term else '',
                demand_score=term.demand if term else None,
                demand_peak_month=term.peak_month if term else None,
            )
            if recipe.slug in ratings:
                new['owner_rating'] = ratings[recipe.slug]
                rated += 1
            if term:
                attached += 1
                if how == 'name':
                    self.stdout.write(f"  {recipe.slug:<48} -> {term.term}  ({term.demand:.0f})")
            diff = {k: v for k, v in new.items() if getattr(recipe, k) != v}
            if diff:
                changed += 1
                if not dry:
                    for k, v in diff.items():
                        setattr(recipe, k, v)
                    recipe.save(update_fields=list(diff))

        self.stdout.write(self.style.SUCCESS(
            f"{'[dry-run] ' if dry else ''}recipes={CuratedRecipe.objects.count()} attached={attached} "
            f"by_override={how_counts['override']} by_name={how_counts['name']} "
            f"blank={how_counts['none']} changed={changed} ratings={rated}"
        ))
