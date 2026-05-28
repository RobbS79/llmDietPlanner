"""
Bulk-load StoreProduct rows for a single chain from a YAML staples file.

Usage:
    python manage.py seed_store_staples --chain=LIDL_CZ
    python manage.py seed_store_staples --chain=LIDL_CZ --file path/to/lidl_cz.yaml --dry-run
"""
from decimal import Decimal
from pathlib import Path
from typing import Optional

import yaml
from django.core.management.base import BaseCommand, CommandError

from diet_planner.models import (
    CanonicalIngredient,
    GroceryStore,
    IngredientAlias,
    StoreProduct,
)
from diet_planner.scrapers.utils import normalize_ingredient_name


DATA_DIR = Path(__file__).resolve().parents[2] / 'data' / 'staples'


def _resolve_canonical(slug_or_name: str) -> Optional[CanonicalIngredient]:
    if not slug_or_name:
        return None
    obj = CanonicalIngredient.objects.filter(slug=slug_or_name).first()
    if obj:
        return obj
    # Fall back to localized name lookup or alias.
    for field in ('name', 'name_cs', 'name_sk'):
        obj = CanonicalIngredient.objects.filter(**{f'{field}__iexact': slug_or_name}).first()
        if obj:
            return obj
    alias = IngredientAlias.objects.filter(alias__iexact=slug_or_name).first()
    return alias.canonical_ingredient if alias else None


class Command(BaseCommand):
    help = 'Seed StoreProduct rows for a chain from data/staples/<chain>.yaml'

    def add_arguments(self, parser):
        parser.add_argument('--chain', required=True, help='GroceryStore code, e.g. LIDL_CZ')
        parser.add_argument('--file', type=str, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        chain = options['chain']
        try:
            store = GroceryStore.objects.get(code=chain)
        except GroceryStore.DoesNotExist:
            raise CommandError(f'Unknown GroceryStore code: {chain}')

        path = Path(options['file']) if options['file'] else (DATA_DIR / f'{chain.lower()}.yaml')
        if not path.exists():
            raise CommandError(f'Staples file not found: {path}')

        with path.open('r', encoding='utf-8') as fh:
            rows = yaml.safe_load(fh) or []

        created = updated = unmatched_canonical = 0
        for row in rows:
            name = row.get('name') or row.get('display_name')
            if not name:
                self.stdout.write(self.style.WARNING(f'Skipping row without name: {row}'))
                continue

            canonical_key = row.get('canonical_slug') or row.get('canonical_name_cs') or ''
            canonical = _resolve_canonical(canonical_key) if canonical_key else None
            if canonical_key and canonical is None:
                unmatched_canonical += 1
                self.stdout.write(
                    self.style.WARNING(
                        f'  no CanonicalIngredient for "{canonical_key}" (product "{name}")'
                    )
                )

            normalized = normalize_ingredient_name(name)
            package_size = row.get('package_size')
            defaults = {
                'name': name,
                'brand': row.get('brand', ''),
                'package_size': Decimal(str(package_size)) if package_size is not None else None,
                'package_unit': row.get('package_unit', ''),
                'external_id': row.get('external_id', ''),
                'source_url': row.get('source_url') or None,
                'canonical_ingredient': canonical,
                'is_active': True,
            }

            if options['dry_run']:
                self.stdout.write(f'[dry-run] {chain}: would upsert "{name}"')
                continue

            _, was_created = StoreProduct.objects.update_or_create(
                store=store,
                normalized_name=normalized,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'{chain}: created={created} updated={updated} '
                f'unmatched_canonical={unmatched_canonical} (dry_run={options["dry_run"]})'
            )
        )
