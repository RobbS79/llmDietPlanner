"""
Audit per-portion nutrition plausibility across the CuratedRecipe corpus.

Read-only. Sibling of `audit_portion_plausibility`, which audits per-portion
QUANTITIES; this one audits per-portion CALORIES.

`base_nutrition` is contractually "per base_servings", but a large share of the
corpus holds a PER-PORTION figure there instead, so dividing it again yields a
30-kcal main course. That understatement drives `portions_for_target` to
over-serve the slot, so it is a plan-quality bug, not just a display one.

Use it to size the problem, to list the recipes worth re-curating, and to
calibrate the thresholds in diet_planner/services/nutrition_plausibility.py.

    python manage.py audit_nutrition_plausibility
    python manage.py audit_nutrition_plausibility --status all
    python manage.py audit_nutrition_plausibility --role main
    python manage.py audit_nutrition_plausibility --csv /tmp/nutrition.csv
"""
import csv
from collections import defaultdict

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services.nutrition_plausibility import check_nutrition_plausibility

_FIELDS = [
    'slug', 'name_cs', 'dish_role', 'base_servings', 'total_kcal',
    'per_portion_kcal', 'atwater_kcal', 'suspected_basis', 'ok', 'reasons',
]


def _percentile(values, pct):
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


class Command(BaseCommand):
    help = "Report recipes with implausible per-portion calories (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--status', choices=['all', 'draft', 'vetted', 'published'],
            default='published',
            help="Limit to recipes of a given status (default: published).")
        parser.add_argument('--role', default=None,
                            help="Limit to one dish_role (main, light, side, ...).")
        parser.add_argument('--csv', dest='csv_path', default=None,
                            help="Write per-recipe rows to this CSV path.")

    def handle(self, *args, **options):
        status, role, csv_path = options['status'], options['role'], options['csv_path']

        qs = CuratedRecipe.objects.all().order_by('id')
        if status != 'all':
            qs = qs.filter(status=status)
        if role:
            qs = qs.filter(dish_role=role)

        rows, flagged, skipped = [], [], []
        by_role = defaultdict(list)

        for recipe in qs.iterator():
            dish_role = getattr(recipe, 'dish_role', '') or ''
            try:
                result = check_nutrition_plausibility(
                    recipe.base_nutrition, recipe.base_servings, dish_role)
            except Exception as exc:  # never let one bad row abort the report
                skipped.append((recipe.slug, str(exc)))
                continue
            if result.per_portion_kcal is None:
                continue  # no stored calories — nothing to judge
            row = {
                'slug': recipe.slug,
                'name_cs': recipe.name_cs,
                'dish_role': dish_role,
                'base_servings': recipe.base_servings,
                'total_kcal': result.total_kcal,
                'per_portion_kcal': result.per_portion_kcal,
                'atwater_kcal': result.atwater_kcal,
                'suspected_basis': result.suspected_basis or '',
                'ok': result.ok,
                'reasons': '; '.join(result.reasons),
            }
            rows.append(row)
            by_role[dish_role or 'none'].append(result.per_portion_kcal)
            if not result.ok:
                flagged.append(row)

        scanned = len(rows)
        self.stdout.write(f'Scanned {scanned} recipe(s) with stored calories (status={status}).')

        if scanned:
            self.stdout.write('per-portion kcal by dish_role:')
            for name, values in sorted(by_role.items(), key=lambda kv: -len(kv[1])):
                self.stdout.write(
                    '  {:<10} n={:<5} p25={:<7.0f} p50={:<7.0f} p75={:<7.0f}'.format(
                        name, len(values), _percentile(values, 25),
                        _percentile(values, 50), _percentile(values, 75)))

            wrong_basis = [r for r in flagged if r['suspected_basis'] == 'per_portion']
            self.stdout.write(
                f'Flagged {len(flagged)} ({100 * len(flagged) / scanned:.0f}%), '
                f'of which {len(wrong_basis)} look like base_nutrition holds ONE portion.')

        for row in sorted(flagged, key=lambda r: r['per_portion_kcal']):
            self.stdout.write(
                '  [{base_servings}x {dish_role}] {slug}: {per_portion_kcal:.0f} kcal/portion'
                ' — {reasons}'.format(**row))

        if skipped:
            self.stdout.write(f'Skipped {len(skipped)} row(s) with errors:')
            for slug, err in skipped:
                self.stdout.write(f'  {slug}: {err}')

        if csv_path:
            with open(csv_path, 'w', newline='') as fh:
                writer = csv.DictWriter(fh, fieldnames=_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(f'Wrote {len(rows)} row(s) to {csv_path}.')
