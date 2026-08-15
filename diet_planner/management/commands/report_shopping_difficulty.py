"""Read-only measurement of corpus obtainability. Writes nothing.

This is the report the spec gates corpus mutation on: the number that matters
is not "how many recipes are clean" but "does each slot still have a pool".
"""
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand

from diet_planner.models import Availability, CuratedRecipe

ORDER = [Availability.COMMON, Availability.FINDABLE,
         Availability.SPECIALTY, Availability.UNRATED]


class Command(BaseCommand):
    help = 'Report how much of the published corpus is unshoppable. Read-only.'

    def add_arguments(self, parser):
        parser.add_argument('--top-blockers', type=int, default=25,
                            help='How many blocking ingredients to list.')

    def handle(self, *args, **options):
        recipes = list(CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED,
        ).only('id', 'shopping_difficulty', 'shopping_blockers',
               'meal_types', 'dietary_tags'))

        total = len(recipes)
        self.stdout.write(f'published recipes: {total}')
        if not total:
            return

        tiers = Counter(r.shopping_difficulty for r in recipes)
        self.stdout.write('\n-- distribution --')
        for tier in ORDER:
            n = tiers.get(tier, 0)
            self.stdout.write(f'  {tier:<10} {n:>4}  ({100.0 * n / total:.1f}%)')
        if tiers.get(Availability.UNRATED):
            self.stdout.write(self.style.WARNING(
                '  NOTE: "unrated" here means the rollup has not run for those '
                'rows — run recompute_shopping_difficulty.'))

        # The number that actually matters: does each slot keep a pool?
        self.stdout.write('\n-- pool by meal_type x dietary_tag (common / total) --')
        pools = defaultdict(lambda: [0, 0])
        for r in recipes:
            tags = list(r.dietary_tags or []) or ['(none)']
            for slot in (r.meal_types or ['(untagged)']):
                for tag in tags:
                    cell = pools[(slot, tag)]
                    cell[1] += 1
                    if r.shopping_difficulty == Availability.COMMON:
                        cell[0] += 1
        for (slot, tag), (clean, tot) in sorted(pools.items()):
            flag = '  <-- THIN' if clean < 10 else ''
            self.stdout.write(f'  {slot:<12} {tag:<16} {clean:>4} / {tot:<4}{flag}')

        self.stdout.write('\n-- blocking ingredients by recipes cost --')
        blockers = Counter()
        for r in recipes:
            for slug in (r.shopping_blockers or []):
                blockers[slug] += 1
        limit = options['top_blockers']
        for slug, n in blockers.most_common(limit):
            self.stdout.write(f'  {n:>4}  {slug}')
        if len(blockers) > limit:
            self.stdout.write(
                f'  ... and {len(blockers) - limit} more blocking ingredient(s) '
                f'not shown (raise --top-blockers)')

        non_common = total - tiers.get(Availability.COMMON, 0)
        self.stdout.write(self.style.WARNING(
            f'\n{non_common} of {total} published recipes '
            f'({100.0 * non_common / total:.1f}%) fail the one-stop bar.'))
