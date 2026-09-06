"""
Backfill CuratedRecipe.dish_role / meal_types / side_options / dish_family via
services.dish_classification, with a dry-run REVIEW REPORT the owner reads
before anything is written.

`meal_types` says WHEN a dish may appear; `dish_role` says whether it can BE
the meal (a Czech oběd is a warm main; lečo is a supper — see
recipe_retrieval._SLOT_ALLOWED_ROLES). `side_options` is the příloha it is
eaten with; `dish_family` is the dedupe key.

Prod usage (via prod_run.py or the DO console):
  python manage.py retag_dish_roles --force --dry-run   # review report
  python manage.py retag_dish_roles --force             # write
Runbook: docs/dish-roles-ops.md
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services import dish_classification as dc
from diet_planner.services.dish_classification import Classification
from diet_planner.services.recipe_retrieval import eligible_recipes_for_slot

LUNCH_POOL_MIN = 15
LUNCH_TAG_SETS = (
    ('none', set()), ('vegetarian', {'vegetarian'}), ('vegan', {'vegan'}),
    ('gluten_free', {'gluten_free'}), ('dairy_free', {'dairy_free'}),
)


class Command(BaseCommand):
    help = "Classify CuratedRecipe dish_role/meal_types/side_options/dish_family via LLM + overrides."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Report, write nothing.')
        parser.add_argument('--force', action='store_true',
                            help='Re-tag every recipe, including light/already-tagged rows.')
        parser.add_argument('--batch-size', type=int, default=25)

    def handle(self, *args, **opts):
        qs = CuratedRecipe.objects.order_by('id')
        if not opts['force']:
            qs = qs.filter(dish_role='')
        recipes: List[CuratedRecipe] = list(qs)
        if not recipes:
            self.stdout.write('Nothing to tag.')
            return

        # classify_and_override batches internally; batch_size is honoured via
        # a thin wrapper so the flag still means something.
        answers: Dict[str, Classification] = {}
        for start in range(0, len(recipes), opts['batch_size']):
            answers.update(dc.classify_and_override(recipes[start:start + opts['batch_size']]))

        published = list(CuratedRecipe.objects.filter(status=CuratedRecipe.Status.PUBLISHED))
        before_hist = Counter(r.dish_role or '(empty)' for r in published)
        before_pool = self._lunch_pool(published)

        changes = defaultdict(list)   # cuisine -> lines
        written = skipped = 0
        proposed: Dict[int, Classification] = {}
        for r in recipes:
            c = answers.get(r.slug)
            if c is None or not c.dish_role:
                self.stdout.write(f'SKIP {r.slug}: unusable role '
                                  f'{(c.problems if c else ["no answer"])!r}')
                skipped += 1
                continue
            for p in c.problems:
                self.stdout.write(f'  note {r.slug}: {p}')
            old_role = r.dish_role or '(empty)'
            old_mt = list(r.meal_types or [])
            line = (f'{r.slug} | {r.name_cs} | {old_role} -> {c.dish_role} | '
                    f'meal_types {old_mt} -> {c.meal_types} | sides {c.side_options} | family {c.dish_family}')
            if old_role != c.dish_role or old_mt != c.meal_types:
                changes[r.cuisine or '(none)'].append(line)
            self.stdout.write(line)
            proposed[r.id] = c
            written += 1

        # Simulate the outcome in memory for the histogram + pool report.
        for r in published:
            c = proposed.get(r.id)
            if c:
                r.dish_role, r.meal_types = c.dish_role, c.meal_types
        after_hist = Counter(r.dish_role or '(empty)' for r in published)
        after_pool = self._lunch_pool(published)

        self.stdout.write('\n== Changes (role or meal_types), Czech first ==')
        for cuisine in sorted(changes, key=lambda k: (k != 'czech', k)):
            self.stdout.write(f'[{cuisine}]')
            for line in changes[cuisine]:
                self.stdout.write('  ' + line)
        self.stdout.write('\n== Role histogram (published) ==')
        self.stdout.write('  before: ' + ', '.join(f'{k} {v}' for k, v in before_hist.most_common()))
        self.stdout.write('  after:  ' + ', '.join(f'{k} {v}' for k, v in after_hist.most_common()))
        self.stdout.write('\n== Lunch pool (published, role main, lunch in meal_types, catalog-mapped) ==')
        for label, _ in LUNCH_TAG_SETS:
            b, a = before_pool[label], after_pool[label]
            warn = '  WARNING: below %d' % LUNCH_POOL_MIN if a < LUNCH_POOL_MIN else ''
            self.stdout.write(f'  {label}: {b} -> {a}{warn}')

        if not opts['dry_run']:
            for r in recipes:
                c = proposed.get(r.id)
                if not c:
                    continue
                r.dish_role, r.meal_types = c.dish_role, c.meal_types
                r.side_options, r.dish_family = c.side_options, c.dish_family
                r.save(update_fields=['dish_role', 'meal_types', 'side_options', 'dish_family'])

        verb = 'Would write' if opts['dry_run'] else 'Wrote'
        self.stdout.write(self.style.SUCCESS(
            f'\n{verb} {written} recipe(s), skipped {skipped}, of {len(recipes)} candidate(s).'
        ))

    @staticmethod
    def _lunch_pool(pool: List[CuratedRecipe]) -> Dict[str, int]:
        return {
            label: len(eligible_recipes_for_slot('lunch', tags, pool=pool))
            for label, tags in LUNCH_TAG_SETS
        }
