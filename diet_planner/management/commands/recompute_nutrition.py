"""Recompute CuratedRecipe.base_nutrition from the per-100 g table.

Dry run (default) prints old -> new kcal per recipe, the worklist of lines
that cannot convert grouped by (canonical, unit, reason), and a summary.
`--apply` writes computed rows (incomplete rows only get their blockers
updated, nutrition untouched) and prints a REVERSAL map; it refuses while
any PUBLISHED recipe is incomplete unless `--skip-incomplete`.
A computed-but-implausible recipe counts as incomplete: an implausible number
never silently overwrites a published row.
After applying run `refresh_stale_recipe_cache --apply`.
"""
import csv
import json
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from diet_planner.models import CuratedRecipe
from diet_planner.services.nutrition_lookups import nutrition_table
from diet_planner.services.recipe_curation import apply_nutrition


class Command(BaseCommand):
    help = 'Recompute base_nutrition from ingredient lines and the canonical nutrition table.'

    def add_arguments(self, parser):
        parser.add_argument('--status', choices=['published', 'draft', 'all'], default='published')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--skip-incomplete', dest='skip_incomplete', action='store_true')
        parser.add_argument('--report', default=None)

    def handle(self, *args, **opts):
        qs = CuratedRecipe.objects.all().order_by('id')
        if opts['status'] != 'all':
            qs = qs.filter(status=opts['status'])
        table = nutrition_table()
        worklist = Counter()
        rows, incomplete_published, plans = [], [], {}
        for r in qs:
            fields = {'ingredients': r.ingredients or [], 'base_servings': r.base_servings}
            blockers = apply_nutrition(fields, dish_role=r.dish_role or None, table=table)
            old = (r.base_nutrition or {}).get('calories')
            new = (fields['base_nutrition'] or {}).get('calories')
            complete = bool(fields['base_nutrition']) and not blockers
            for b in blockers:
                worklist[(b.get('canonical') or b.get('name'), b.get('unit'), b['reason'])] += 1
            if not complete and r.status == CuratedRecipe.Status.PUBLISHED:
                incomplete_published.append(r)
            delta = (f'{(new - old) / old:+.0%}' if old and new else '')
            self.stdout.write(f'[{r.pk}] {r.name_cs[:34]:34} {old} -> {new} {delta} '
                              f'{"" if complete else "INCOMPLETE " + ", ".join(b["reason"] for b in blockers)}')
            rows.append({'id': r.pk, 'slug': r.slug, 'status': r.status, 'old_kcal': old, 'new_kcal': new,
                         'delta': delta, 'complete': complete, 'blockers': json.dumps(blockers, ensure_ascii=False)})
            plans[r.pk] = (r, fields['base_nutrition'], blockers, complete)
        self.stdout.write('')
        self.stdout.write('Worklist (canonical, unit, reason): count')
        for (c, u, reason), n in worklist.most_common():
            self.stdout.write(f'  {c} {u} {reason}: {n}')
        self.stdout.write(self.style.SUCCESS(
            f'recipes={len(rows)} complete={sum(1 for x in rows if x["complete"])} '
            f'incomplete={sum(1 for x in rows if not x["complete"])}'))
        if opts['report']:
            with open(opts['report'], 'w', newline='', encoding='utf-8') as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ['id'])
                w.writeheader()
                w.writerows(rows)
        if not opts['apply']:
            return
        if incomplete_published and not opts['skip_incomplete']:
            raise CommandError(f'{len(incomplete_published)} published recipe(s) are incomplete; '
                               f'fix the table (see worklist) or pass --skip-incomplete')
        reversal = {}
        with transaction.atomic():
            for r, base, blockers, complete in plans.values():
                if not complete:
                    if r.nutrition_blockers != blockers:
                        r.nutrition_blockers = blockers
                        r.save(update_fields=['nutrition_blockers', 'updated_at'])
                    continue
                reversal[str(r.pk)] = r.base_nutrition or {}
                r.base_nutrition = base
                r.nutrition_blockers = blockers
                r.save(update_fields=['base_nutrition', 'nutrition_blockers', 'updated_at'])
        self.stdout.write('REVERSAL')
        self.stdout.write(json.dumps(reversal, ensure_ascii=False))
        self.stdout.write(self.style.SUCCESS(f'applied={len(reversal)}'))
