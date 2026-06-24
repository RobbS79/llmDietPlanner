"""
Audit per-portion quantity plausibility across the CuratedRecipe corpus.

Read-only. Flags recipes whose weighable mass per portion is implausibly high
(a base_servings mismatch inflates every ingredient). Use it to find offenders
and to calibrate the thresholds in
diet_planner/services/recipe_plausibility.py.

    python manage.py audit_portion_plausibility
    python manage.py audit_portion_plausibility --status all
    python manage.py audit_portion_plausibility --csv /tmp/audit.csv
"""
import csv

from django.core.management.base import BaseCommand

from diet_planner.models import CuratedRecipe
from diet_planner.services.recipe_plausibility import check_portion_plausibility

_FIELDS = [
    'slug', 'name_cs', 'base_servings', 'per_portion_total_g',
    'worst_ingredient', 'worst_g_per_portion', 'ok', 'reasons',
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
    help = "Report recipes with implausible per-portion weighable mass (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--status',
            choices=['all', 'draft', 'vetted', 'published'],
            default='published',
            help="Limit to recipes of a given status (default: published).",
        )
        parser.add_argument('--csv', dest='csv_path', default=None,
                            help="Write per-recipe rows to this CSV path.")

    def handle(self, *args, **options):
        status = options['status']
        csv_path = options['csv_path']

        qs = CuratedRecipe.objects.all()
        if status != 'all':
            qs = qs.filter(status=status)

        rows = []
        totals = []
        flagged = []
        skipped = []
        for recipe in qs.iterator():
            try:
                r = check_portion_plausibility(recipe.ingredients or [], recipe.base_servings)
            except Exception as exc:  # never let one bad row abort the report
                skipped.append((recipe.slug, str(exc)))
                continue
            worst = max(r.offenders, key=lambda o: o['grams_per_portion'], default=None)
            row = {
                'slug': recipe.slug,
                'name_cs': recipe.name_cs,
                'base_servings': recipe.base_servings,
                'per_portion_total_g': r.per_portion_total_g,
                'worst_ingredient': worst['name'] if worst else '',
                'worst_g_per_portion': worst['grams_per_portion'] if worst else 0,
                'ok': r.ok,
                'reasons': '; '.join(r.reasons),
            }
            rows.append(row)
            totals.append(r.per_portion_total_g)
            if not r.ok:
                flagged.append(row)

        scanned = len(rows)
        self.stdout.write(f"Scanned {scanned} recipe(s) (status={status}).")
        if scanned:
            self.stdout.write(
                "per_portion_total_g  p50={:.0f}  p75={:.0f}  p90={:.0f}  "
                "p95={:.0f}  max={:.0f}".format(
                    _percentile(totals, 50), _percentile(totals, 75),
                    _percentile(totals, 90), _percentile(totals, 95), max(totals)))
            self.stdout.write(f"Flagged {len(flagged)} ({100 * len(flagged) / scanned:.0f}%).")
        else:
            self.stdout.write("Flagged 0.")

        for row in sorted(flagged, key=lambda r: r['per_portion_total_g'], reverse=True):
            self.stdout.write(
                "  [{base_servings}] {slug}: total {per_portion_total_g:.0f} g/p"
                " — {reasons}".format(**row))

        if skipped:
            self.stdout.write(f"Skipped {len(skipped)} row(s) with errors:")
            for slug, err in skipped:
                self.stdout.write(f"  {slug}: {err}")

        if csv_path:
            with open(csv_path, 'w', newline='') as fh:
                writer = csv.DictWriter(fh, fieldnames=_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            self.stdout.write(f"Wrote {len(rows)} row(s) to {csv_path}.")
