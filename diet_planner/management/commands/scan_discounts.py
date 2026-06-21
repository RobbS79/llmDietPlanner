"""Daily refresh of leaflet discount data.

Two jobs:
  1. Report LEAFLET_DISCOUNT PriceRecords past their valid_until, so the
     click-time deal read (compute_pricing) never surfaces stale leaflets.
     (current() already excludes them; this pass surfaces/normalizes them.)
  2. (unless --no-scrape) Re-scrape current discounts via the existing
     aggregator + Rohlík search scrapers so coverage stays fresh.

Wired as a DO App Platform scheduled Job. Celery beat is disabled in prod,
so this runs as a standalone management command.
"""
import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from diet_planner.models import PriceRecord, PriceSourceType

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Refresh leaflet discounts and report stale records."

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-scrape', action='store_true',
            help="Only report stale records; skip live scraping (used by tests).",
        )

    def handle(self, *args, **options):
        now = timezone.now()

        stale = PriceRecord.objects.filter(
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_until__isnull=False,
            valid_until__lte=now,
        )
        expired_count = stale.count()
        self.stdout.write(
            f"Leaflet records expired (past valid_until): {expired_count}"
        )

        if options['no_scrape']:
            self.stdout.write("Skipping live scrape (--no-scrape).")
            return

        refreshed = self._scrape_current_discounts()
        self.stdout.write(f"Discount records refreshed: {refreshed}")

    def _scrape_current_discounts(self) -> int:
        """Invoke the existing leaflet scrapers for canonicals in active plans.
        Returns the count of upserted discount records. Network-touching;
        skipped under --no-scrape.

        Modeled on scrape_catalog.py / search_catalog.py. Wire the concrete
        scraping here, upserting via
        diet_planner.scrapers.price_recording.upsert_price_record with
        source_type=LEAFLET_DISCOUNT. Until fully wired, this is a no-op that
        returns 0 so the daily job runs safely.
        """
        count = 0
        # TODO(scan_discounts live scrape): collect canonicals from active
        # DietaryPlans, run kupi.cz aggregator + Rohlík search per term, and
        # upsert LEAFLET_DISCOUNT records. Modeled on scrape_catalog.py.
        return count
