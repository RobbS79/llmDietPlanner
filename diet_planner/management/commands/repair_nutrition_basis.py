"""Repair curated recipes whose `base_nutrition` holds ONE portion.

`base_nutrition` is contractually "per base_servings", but a large share of the
corpus stores a per-portion figure there, so dividing by base_servings again
yields a 30-kcal main course. That understatement is not cosmetic:
`portions_for_target` sizes slots from per-portion calories, so an understated
recipe gets OVER-SERVED, and `score_recipe` mis-ranks it.

Sibling of the read-only `audit_nutrition_plausibility`, which sizes the
problem. This one fixes it — but only where the recipe's own ingredients agree.
The wrong-basis signature also matches recipes whose `base_servings` counts
PIECES (4 hard-boiled eggs, 12 egg muffins), where the stored total is already
correct and multiplying would invent calories. `nutrition_basis_repair` weighs
both readings against the energy the ingredients actually carry and refuses
those; they are reported as skips for re-curation, not silently rewritten.

Dry run by default. `--apply` writes, and prints a REVERSAL map (slug -> the
previous base_nutrition) so any change can be undone from the run's own output.

    python manage.py repair_nutrition_basis
    python manage.py repair_nutrition_basis --csv /tmp/basis.csv
    python manage.py repair_nutrition_basis --apply

After applying, run `refresh_stale_recipe_cache` — cached `Recipe` rows built
from the old nutrition do not invalidate themselves.
"""
import csv
import json
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.services.nutrition_basis_repair import plan_basis_repair
from diet_planner.services.nutrition_lookups import category_table, piece_weight_table

_FIELDS = [
    'slug', 'name_cs', 'dish_role', 'base_servings', 'action', 'reason',
    'stored_kcal', 'corrected_kcal', 'estimated_kcal', 'stored_vs_estimate',
    'corrected_vs_estimate', 'mass_g', 'coverage', 'category_coverage',
]


class Command(BaseCommand):
    help = "Rewrite base_nutrition where it stores one portion instead of the whole recipe."

    def add_arguments(self, parser):
        parser.add_argument(
            '--status', choices=['all', 'draft', 'vetted', 'published'],
            default='published',
            help="Limit to recipes of a given status (default: published).")
        parser.add_argument('--apply', action='store_true',
                            help="Write the repairs (default: dry run).")
        parser.add_argument('--csv', dest='csv_path', default=None,
                            help="Write one row per candidate to this CSV path.")

    def handle(self, *args, **options):
        status, apply_changes, csv_path = (
            options['status'], options['apply'], options['csv_path'])

        weights = piece_weight_table()
        categories = category_table()
        qs = CuratedRecipe.objects.all().order_by('id')
        if status != 'all':
            qs = qs.filter(status=status)

        rows, repairs, reasons = [], [], Counter()

        for recipe in qs.iterator():
            plan = plan_basis_repair(
                recipe.base_nutrition, recipe.base_servings,
                getattr(recipe, 'dish_role', '') or '', recipe.ingredients,
                piece_weights=weights, categories=categories)
            if plan.reason == 'not_a_basis_candidate':
                continue
            reasons[plan.reason] += 1
            evidence = plan.evidence
            rows.append({
                'slug': recipe.slug,
                'name_cs': recipe.name_cs,
                'dish_role': getattr(recipe, 'dish_role', '') or '',
                'base_servings': recipe.base_servings,
                'action': plan.action,
                'reason': plan.reason,
                'stored_kcal': evidence.get('stored_kcal'),
                'corrected_kcal': evidence.get('corrected_kcal'),
                'estimated_kcal': evidence.get('estimated_kcal'),
                'stored_vs_estimate': evidence.get('stored_vs_estimate'),
                'corrected_vs_estimate': evidence.get('corrected_vs_estimate'),
                'mass_g': evidence.get('mass_g'),
                'coverage': evidence.get('coverage'),
                'category_coverage': evidence.get('category_coverage'),
            })
            if plan.action == 'repair':
                repairs.append((recipe, plan))

        self.stdout.write(
            f'{len(rows)} wrong-basis candidate(s) in status={status}: '
            f'{len(repairs)} repairable, {len(rows) - len(repairs)} left for review.')
        for reason, count in reasons.most_common():
            self.stdout.write(f'  {reason}: {count}')

        for recipe, plan in repairs:
            self.stdout.write(
                '  [{n}x {role}] {slug}: {before:.0f} -> {after:.0f} kcal total '
                '(ingredients carry ~{est:.0f}; {ratio}x vs {stored_ratio}x before)'.format(
                    n=recipe.base_servings,
                    role=getattr(recipe, 'dish_role', '') or 'unknown',
                    slug=recipe.slug,
                    before=plan.evidence['stored_kcal'],
                    after=plan.evidence['corrected_kcal'],
                    est=plan.evidence['estimated_kcal'],
                    ratio=plan.evidence['corrected_vs_estimate'],
                    stored_ratio=plan.evidence['stored_vs_estimate']))

        skipped = [r for r in rows if r['action'] == 'skip']
        if skipped:
            self.stdout.write('Left for re-curation (not rewritten):')
            for row in skipped:
                self.stdout.write(
                    '  [{base_servings}x {dish_role}] {slug}: {reason}'.format(**row))

        if csv_path:
            with open(csv_path, 'w', newline='') as fh:
                writer = csv.DictWriter(fh, fieldnames=_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(f'Wrote {len(rows)} row(s) to {csv_path}.')

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                'DRY RUN — nothing written. Re-run with --apply to commit.'))
            return

        reversal = {recipe.slug: recipe.base_nutrition for recipe, _ in repairs}
        with transaction.atomic():
            for recipe, plan in repairs:
                recipe.base_nutrition = plan.proposed
                recipe.save(update_fields=['base_nutrition', 'updated_at'])

        self.stdout.write(self.style.SUCCESS(f'Repaired {len(repairs)} recipe(s).'))
        self.stdout.write('REVERSAL (previous base_nutrition, to undo this run):')
        self.stdout.write(json.dumps(reversal, ensure_ascii=False, sort_keys=True))
        self.stdout.write(
            'Now run: python manage.py refresh_stale_recipe_cache --apply')
