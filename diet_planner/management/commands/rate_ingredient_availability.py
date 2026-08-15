"""Apply data/ingredient_availability.yaml to CanonicalIngredient rows.

Idempotent. Fails loudly when the YAML and the canonical table disagree in
either direction — growing the ingredient dictionary must not silently leave
rows unrated, and a stale YAML row must not pass unnoticed.
"""
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import Availability, CanonicalIngredient

DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'ingredient_availability.yaml'
VALID = {c for c in Availability.values if c != Availability.UNRATED}


class Command(BaseCommand):
    help = 'Apply the availability seed YAML to CanonicalIngredient rows.'

    def add_arguments(self, parser):
        parser.add_argument('--file', dest='file', default=str(DEFAULT_FILE))
        parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                            help='Print the diff, write nothing.')
        parser.add_argument('--report-uncertain', dest='report_uncertain',
                            action='store_true',
                            help='Print only the rows Claude is still guessing on.')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'Availability file not found: {path}')

        rows = yaml.safe_load(path.read_text(encoding='utf-8')) or []
        by_slug = {}
        for row in rows:
            slug = (row.get('slug') or '').strip()
            tier = (row.get('availability') or '').strip().lower()
            if not slug:
                raise CommandError(f'Row without a slug: {row!r}')
            if tier not in VALID:
                raise CommandError(f'{slug}: unknown tier {tier!r}')
            by_slug[slug] = row

        if options['report_uncertain']:
            uncertain = [r for r in rows if (r.get('confidence') or '') == 'low']
            for r in sorted(uncertain, key=lambda r: r['slug']):
                self.stdout.write(
                    f"  {r['slug']:<28} {r['availability']:<10} {r.get('note') or ''}")
            self.stdout.write(self.style.WARNING(
                f'{len(uncertain)} row(s) still resting on a guess.'))
            return

        db_slugs = set(CanonicalIngredient.objects.values_list('slug', flat=True))
        missing = sorted(db_slugs - set(by_slug))
        if missing:
            raise CommandError(
                f'{len(missing)} canonical(s) have no rating in {path.name}: '
                f'{", ".join(missing[:20])}'
                + (' ...' if len(missing) > 20 else '')
            )
        ghosts = sorted(set(by_slug) - db_slugs)
        if ghosts:
            raise CommandError(
                f'{len(ghosts)} rating(s) reference unknown canonicals: '
                f'{", ".join(ghosts[:20])}'
                + (' ...' if len(ghosts) > 20 else '')
            )

        changed = 0
        for ci in CanonicalIngredient.objects.all().order_by('slug'):
            row = by_slug[ci.slug]
            tier = row['availability'].strip().lower()
            note = (row.get('note') or '')[:200]
            if ci.availability == tier and ci.availability_note == note:
                continue
            self.stdout.write(
                f'  {ci.slug:<28} {ci.availability} -> {tier}')
            changed += 1
            if not options['dry_run']:
                ci.availability = tier
                ci.availability_note = note
                ci.save(update_fields=['availability', 'availability_note', 'updated_at'])

        prefix = '[dry-run] ' if options['dry_run'] else ''
        self.stdout.write(self.style.SUCCESS(
            f'{prefix}rated={len(by_slug)} changed={changed}'))
