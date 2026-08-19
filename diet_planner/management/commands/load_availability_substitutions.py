"""Load the Czech-availability substitution table into IngredientSubstitute.

Idempotent: re-running updates the swap's numbers but never duplicates a row,
and never touches rows whose purpose is not 'availability' (those are
hand-made preference/dietary swaps that predate this table).

See docs/superpowers/specs/2026-08-11-ingredient-obtainability-design.md §6
"""
from decimal import Decimal
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import CanonicalIngredient
from diet_planner.models.catalog import Availability, IngredientSubstitute

DEFAULT_PATH = (
    Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'ingredient_substitutions_cz.yaml'
)


class Command(BaseCommand):
    help = 'Load ingredient_substitutions_cz.yaml into IngredientSubstitute.'

    def add_arguments(self, parser):
        parser.add_argument('--path', default=str(DEFAULT_PATH))
        parser.add_argument('--dry-run', dest='dry_run', action='store_true')

    def handle(self, *args, **options):
        rows = yaml.safe_load(Path(options['path']).read_text(encoding='utf-8')) or []
        by_slug = {c.slug: c for c in CanonicalIngredient.objects.all()}

        # Resolve everything BEFORE writing anything: a typo must not leave a
        # half-loaded table behind.
        missing = sorted({
            slug
            for row in rows
            for slug in (row.get('ingredient'), row.get('substitute'))
            if slug not in by_slug
        })
        if missing:
            raise CommandError(
                f"unknown canonical slug(s) in {options['path']}: {', '.join(missing)}")

        # A swap onto an ingredient you also cannot buy achieves nothing. Only
        # enforced where the target carries a rating — UNRATED means we have
        # not judged it yet, which is not the same as knowing it is bad.
        unobtainable = sorted({
            row['substitute']
            for row in rows
            if by_slug[row['substitute']].availability in (
                Availability.FINDABLE, Availability.SPECIALTY)
        })
        if unobtainable:
            raise CommandError(
                'substitution target(s) not available in an ordinary Czech '
                'supermarket: ' + ', '.join(
                    f'{s} ({by_slug[s].availability})' for s in unobtainable))

        created = updated = 0
        for row in rows:
            ing = by_slug[row['ingredient']]
            sub = by_slug[row['substitute']]
            defaults = {
                'purpose': IngredientSubstitute.Purpose.AVAILABILITY,
                'quality_score': Decimal(str(row.get('quality_score', 0.80))),
                'conversion_factor': Decimal(str(row.get('conversion_factor', 1.0))),
                'substitute_unit': row.get('substitute_unit', '') or '',
            }
            existing = IngredientSubstitute.objects.filter(
                ingredient=ing, substitute=sub).first()

            if existing is None:
                created += 1
                if not options['dry_run']:
                    IngredientSubstitute.objects.create(
                        ingredient=ing, substitute=sub, **defaults)
                continue

            # Never rewrite a hand-made preference/dietary row.
            if existing.purpose != IngredientSubstitute.Purpose.AVAILABILITY:
                self.stdout.write(
                    f'  skip {ing.slug} -> {sub.slug} (purpose={existing.purpose})')
                continue

            if any(getattr(existing, key) != value for key, value in defaults.items()):
                updated += 1
                if not options['dry_run']:
                    for key, value in defaults.items():
                        setattr(existing, key, value)
                    existing.save(update_fields=list(defaults))

        # The file is the table. Without this, retiring a swap in the YAML
        # removed it from git and nowhere else: every already-seeded database
        # kept firing it, prod included. Scoped to AVAILABILITY rows — the
        # hand-made preference/dietary swaps are not in this file by design.
        wanted = {(by_slug[r['ingredient']].pk, by_slug[r['substitute']].pk)
                  for r in rows}
        stale = [
            row for row in IngredientSubstitute.objects.filter(
                purpose=IngredientSubstitute.Purpose.AVAILABILITY)
            if (row.ingredient_id, row.substitute_id) not in wanted
        ]
        for row in stale:
            self.stdout.write(
                f'  remove {row.ingredient.slug} -> {row.substitute.slug} '
                f'(no longer in the table)')
        if stale and not options['dry_run']:
            IngredientSubstitute.objects.filter(
                pk__in=[row.pk for row in stale]).delete()

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}loaded={len(rows)} created={created} updated={updated} '
            f'removed={len(stale)}'))
