"""
Bulk-load CanonicalIngredient + IngredientAlias rows from a YAML file.

Usage:
    python manage.py seed_canonical_ingredients
    python manage.py seed_canonical_ingredients --file path/to/file.yaml --dry-run
"""
from pathlib import Path

import yaml
from django.core.management.base import BaseCommand, CommandError
from django.utils.text import slugify

from diet_planner.models import CanonicalIngredient, IngredientAlias


DEFAULT_FILE = Path(__file__).resolve().parents[2] / 'data' / 'canonical_ingredients.yaml'


class Command(BaseCommand):
    help = 'Seed CanonicalIngredient rows from data/canonical_ingredients.yaml'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, default=str(DEFAULT_FILE))
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['file'])
        if not path.exists():
            raise CommandError(f'Canonical ingredient file not found: {path}')

        with path.open('r', encoding='utf-8') as fh:
            data = yaml.safe_load(fh) or []

        created = updated = aliases_created = 0
        for row in data:
            name = row.get('name')
            if not name:
                self.stdout.write(self.style.WARNING(f'Skipping row without name: {row}'))
                continue
            slug = row.get('slug') or slugify(name)[:255]
            defaults = {
                'name': name,
                'name_cs': row.get('name_cs') or '',
                'name_sk': row.get('name_sk') or '',
                'category': row.get('category', CanonicalIngredient.Category.OTHER),
                'default_unit': row.get('default_unit', 'g'),
                'typical_unit': row.get('typical_unit', ''),
                'is_pantry_staple': bool(row.get('is_pantry_staple', False)),
                'estimated_price_czk': row.get('estimated_price_czk'),
                'estimated_price_eur': row.get('estimated_price_eur'),
                'typical_package_sizes': row.get('typical_package_sizes') or [],
            }
            if options['dry_run']:
                self.stdout.write(f'[dry-run] would upsert {slug} ({name})')
                continue

            obj, was_created = CanonicalIngredient.objects.update_or_create(
                slug=slug, defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

            for alias in row.get('aliases') or []:
                alias_text = (alias.get('alias') or '').strip()
                lang = alias.get('language_code') or ''
                if not alias_text:
                    continue
                _, alias_was_created = IngredientAlias.objects.get_or_create(
                    alias=alias_text,
                    language_code=lang,
                    defaults={'canonical_ingredient': obj},
                )
                if alias_was_created:
                    aliases_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Canonical ingredients: created={created} updated={updated} '
                f'new_aliases={aliases_created} (dry_run={options["dry_run"]})'
            )
        )
