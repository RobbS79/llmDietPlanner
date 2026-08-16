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

        # Two canonicals claiming the same alias is unresolvable: seeding would
        # hand it to whichever row is processed last, so consecutive runs flip
        # the owner and ingredient resolution silently changes underneath the
        # corpus. Refuse to run rather than pick arbitrarily.
        claims = {}
        conflicts = []
        for row in data:
            row_slug = row.get('slug') or slugify(row.get('name') or '')[:255]
            for alias in row.get('aliases') or []:
                alias_text = (alias.get('alias') or '').strip()
                if not alias_text:
                    continue
                key = (alias_text, alias.get('language_code') or '')
                if key in claims and claims[key] != row_slug:
                    conflicts.append(f'{alias_text!r} claimed by '
                                     f'{claims[key]} and {row_slug}')
                else:
                    claims[key] = row_slug
        if conflicts:
            raise CommandError(
                'duplicate alias claims in %s:\n  %s' % (path, '\n  '.join(conflicts)))

        created = updated = aliases_created = aliases_repointed = 0
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
                # update_or_create, NOT get_or_create: when the YAML moves an
                # alias to a different canonical (splitting `vanilkové aroma`
                # out of `vanilla` into its own product), get_or_create matched
                # the existing row and dropped the new owner on the floor —
                # `defaults` only apply on creation. The YAML edit then looked
                # applied while silently no-opping on every already-seeded
                # database, dev and prod included.
                existing = IngredientAlias.objects.filter(
                    alias=alias_text, language_code=lang,
                ).first()
                if existing is None:
                    IngredientAlias.objects.create(
                        alias=alias_text, language_code=lang,
                        canonical_ingredient=obj,
                    )
                    aliases_created += 1
                elif existing.canonical_ingredient_id != obj.id:
                    existing.canonical_ingredient = obj
                    existing.save(update_fields=['canonical_ingredient'])
                    aliases_repointed += 1
                    self.stdout.write(
                        f'  realias {alias_text!r} -> {obj.slug}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Canonical ingredients: created={created} updated={updated} '
                f'new_aliases={aliases_created} repointed={aliases_repointed} '
                f'(dry_run={options["dry_run"]})'
            )
        )
