"""
Run a full sitemap-driven catalog scrape for a single store. Writes one
StoreProduct + one PriceRecord(STORE_REGULAR) per product. Canonical
matching happens later via `match_canonical_ingredients`.

Usage:
    python manage.py scrape_catalog --store=ROHLIK
    python manage.py scrape_catalog --store=ROHLIK --limit=100 --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from diet_planner.scrapers.scraper_service import ScraperService


class Command(BaseCommand):
    help = 'Run a sitemap-driven catalog scrape and write to PriceRecord/StoreProduct.'

    def add_arguments(self, parser):
        parser.add_argument('--store', required=True, help='GroceryStore code, e.g. ROHLIK')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        store = options['store']
        scraper_cls = ScraperService.CATALOG_SCRAPER_MAP.get(store)
        if scraper_cls is None:
            raise CommandError(
                f'No catalog scraper registered for {store}. '
                f'Available: {sorted(ScraperService.CATALOG_SCRAPER_MAP)}'
            )

        scraper = scraper_cls(limit=options['limit'], dry_run=options['dry_run'])
        result = scraper.run()

        self.stdout.write(self.style.SUCCESS(
            f"{store} catalog scrape: urls={result['urls']} recorded={result['recorded']} "
            f"skipped={result['skipped']} duration={result['duration_seconds']}s "
            f"dry_run={result['dry_run']}"
        ))
