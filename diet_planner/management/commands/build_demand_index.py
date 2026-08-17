"""Build the committed demand snapshot from public CZ recipe-site rankings.

Sampling is per-category on purpose. The all-time global rankings on both sites
are dominated by sweet baking (perník, buchty, bublanina), which a meal planner
has no slot for; per-category sampling is what makes lunch/dinner demand
visible at all. Global pages are still harvested — they inform the miss list
and the overall picture — but CATEGORY_SLOTS maps 'global' to None, so they
never enter the scored denominator.

The live fetch only happens under --refresh. A plain run reports what the
committed snapshot holds, so tests and CI never touch the network.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import requests
import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from diet_planner.services.demand_index import enrich_term, parse_ranking

DEFAULT_PATH = Path(settings.BASE_DIR) / 'diet_planner' / 'data' / 'demand_index_cz.yaml'

USER_AGENT = 'Mozilla/5.0 (compatible; VartoResearch/1.0; +https://eatalnicek.eu)'

#: (url, source, category). Categories map to meal slots in
#: demand_index.CATEGORY_SLOTS.
SOURCES = [
    ('https://www.toprecepty.cz/top-star.php', 'toprecepty.cz', 'global'),
    ('https://www.toprecepty.cz/kategorie/46-maso/', 'toprecepty.cz', 'maso'),
    ('https://www.toprecepty.cz/kategorie/16-polevky/', 'toprecepty.cz', 'polevky'),
    ('https://www.toprecepty.cz/kategorie/17-testoviny/', 'toprecepty.cz', 'testoviny'),
    ('https://www.toprecepty.cz/kategorie/27-moucniky/', 'toprecepty.cz', 'moucniky'),
    ('https://www.recepty.cz/recept/oblibene', 'recepty.cz', 'global'),
    ('https://www.recepty.cz/polevky-kucharka', 'recepty.cz', 'polevky'),
    ('https://www.recepty.cz/salaty-kucharka', 'recepty.cz', 'salaty'),
]


class Command(BaseCommand):
    help = 'Build diet_planner/data/demand_index_cz.yaml from CZ recipe rankings.'

    def add_arguments(self, parser):
        parser.add_argument('--refresh', action='store_true',
                            help='Fetch the live rankings (otherwise report only)')
        parser.add_argument('--output', default=str(DEFAULT_PATH))
        parser.add_argument('--per-source', type=int, default=40,
                            help='Keep at most this many terms per source page')

    def _fetch(self, url: str) -> str:
        response = requests.get(url, timeout=30, headers={'User-Agent': USER_AGENT})
        response.raise_for_status()
        return response.text

    def handle(self, *args, **options):
        path = Path(options['output'])

        if not options['refresh']:
            if not path.exists():
                self.stdout.write(self.style.WARNING(
                    f'no snapshot at {path}; run with --refresh to build one'))
                return
            payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
            terms = payload.get('terms', [])
            in_scope = sum(1 for t in terms if t.get('in_scope'))
            self.stdout.write(f'snapshot terms={len(terms)} in_scope={in_scope}')
            return

        rows: List[dict] = []
        for url, source, category in SOURCES:
            try:
                html = self._fetch(url)
            except Exception as exc:  # noqa: BLE001 - any fetch failure is fatal
                raise CommandError(
                    f'fetch failed for {url}: {exc}. Previous snapshot left untouched.')
            parsed = parse_ranking(html, source=source, category=category)
            kept = parsed[:options['per_source']]
            self.stdout.write(f'  {source} {category}: {len(kept)} terms')
            rows.extend(enrich_term(term) for term in kept)

        if not rows:
            raise CommandError(
                'every source parsed to zero terms — refusing to write an empty '
                'index, which would make corpus coverage look perfect. '
                'Check the site markup against the parser fixtures.')

        payload = {
            'generated_from': [url for url, _, _ in SOURCES],
            'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'note': ('Positional ranks from public listing pages. Recipe-site '
                     'demand is dish-first; a meal planner is week-first. This '
                     'is a proxy, not demand truth.'),
            'terms': rows,
        }
        path.write_text(
            yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
            encoding='utf-8')

        in_scope = sum(1 for r in rows if r['in_scope'])
        self.stdout.write(self.style.SUCCESS(
            f'terms={len(rows)} in_scope={in_scope} -> {path}'))
