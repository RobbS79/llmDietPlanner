"""Daily refresh of leaflet discount data.

Two jobs:
  1. Report LEAFLET_DISCOUNT PriceRecords past their valid_until, so the
     click-time deal read (recipe_deals) never surfaces stale leaflets.
     (current() already excludes them; this pass surfaces/normalizes them.)
  2. (unless --no-scrape) Re-scrape current discounts via the existing
     kupi.cz aggregator + Rohlík search scrapers so coverage stays fresh.

Wired as a DO App Platform scheduled Job. Celery beat is disabled in prod,
so this runs as a standalone management command.
"""
import logging
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from diet_planner.models import (
    CanonicalIngredient,
    CuratedRecipe,
    PriceRecord,
    PriceSourceType,
)
from diet_planner.scrapers.kupi_cz import KupiCzScraper
from diet_planner.scrapers.price_recording import upsert_price_record
from diet_planner.scrapers.rohlik_cz_search import RohlikCzSearchScraper
from diet_planner.services.canonical_lookup import resolve_canonical

logger = logging.getLogger(__name__)

# kupi.cz store slug -> GroceryStore code for persistence.
KUPI_STORE_CODES = {
    'lidl': 'LIDL_CZ',
    'albert': 'ALBERT_CZ',
    'kaufland': 'KAUFLAND_CZ',
    'penny-market': 'PENNY_CZ',
    'tesco': 'TESCO_CZ',
}

# Politeness pause between kupi.cz stores (seconds).
KUPI_INTER_STORE_DELAY = 1.0

# Retail-noise guard. The canonical resolver is tuned for clean recipe-ingredient
# text; on raw leaflet names it can strip a category word and mis-map a non-food
# product to a food canonical ("Pasta na zuby" -> pasta, "Koření Avokádo" ->
# avocado). We drop a leaflet offer when its name carries drogerie/hygiene/pet
# signals, or leads with a flavouring word ("koření …", "dochucovadlo …") — the
# product is a seasoning of X, not X itself.
_NONFOOD_MARKERS = (
    'zuby', 'zubní', 'zubni', 'šampon', 'sampon', 'mýdlo', 'mydlo', 'sprchov',
    'deodorant', 'antiperspirant', 'toaletní', 'toaletni', 'ubrousky', 'pleny',
    'prací', 'praci', 'aviváž', 'avivaz', 'čisticí', 'cistici', 'osvěžovač',
    'osvezovac', 'holení', 'holeni', 'tělov', 'telov', 'pleťov', 'pletov',
    'vlas', 'krém na', 'krem na', 'granule', 'pro psy', 'pro kočky', 'pro kocky',
)
_FLAVOURING_LEADS = ('koření', 'koreni', 'dochucovadlo', 'směs koření', 'smes koreni')


def _looks_nonfood(name: str) -> bool:
    """True when a leaflet name signals a non-food / wrong-category product the
    canonical resolver would otherwise mis-map to a food ingredient."""
    n = (name or '').strip().lower()
    if not n:
        return True
    if any(n.startswith(lead) for lead in _FLAVOURING_LEADS):
        return True
    return any(marker in n for marker in _NONFOOD_MARKERS)


class Command(BaseCommand):
    help = "Refresh leaflet discounts and report stale records."

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-scrape', action='store_true',
            help="Only report stale records; skip live scraping (used by tests).",
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Run scrapers but do not persist any records.",
        )
        parser.add_argument(
            '--limit', type=int, default=None,
            help="Cap the number of canonicals scraped (testing / scheduled job).",
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

        refreshed = self._scrape_current_discounts(
            dry_run=options['dry_run'],
            limit=options['limit'],
        )
        self.stdout.write(f"Discount records refreshed: {refreshed}")

    def _target_canonicals(self):
        """CanonicalIngredients referenced by PUBLISHED CuratedRecipes.

        Mirrors search_catalog.Command._target_canonicals (non-all branch):
        published recipes reference canonicals by slug, with a name fallback.
        Plans are built from published recipes, so this is the set worth
        refreshing discounts for.
        """
        slugs = set()
        recipes = CuratedRecipe.objects.filter(
            status=CuratedRecipe.Status.PUBLISHED
        ).values_list('ingredients', flat=True)
        for ingredients in recipes:
            for ing in ingredients or []:
                ref = (ing.get('canonical') or '').strip()
                if ref:
                    slugs.add(ref)

        qs = CanonicalIngredient.objects.filter(slug__in=slugs)
        found = list(qs)
        # Defensive: some recipes may store the canonical *name* rather than slug.
        found_slugs = {c.slug for c in found}
        leftover = slugs - found_slugs
        if leftover:
            by_name = CanonicalIngredient.objects.filter(name__in=leftover)
            found.extend(c for c in by_name if c.slug not in found_slugs)

        return sorted(found, key=lambda c: c.slug)

    def _scrape_current_discounts(self, *, dry_run: bool = False, limit=None) -> int:
        """Invoke the existing leaflet scrapers for canonicals in published
        recipes and refresh LEAFLET_DISCOUNT records.

        Robust by design: this runs as a daily scheduled job, so a single
        store/network failure must NOT abort the whole pass. Each source is
        wrapped in try/except and logged, then execution continues.

        Returns the count of leaflet-discount records refreshed
        (Rohlík on_sale + kupi.cz DISCOUNTED offers persisted).
        """
        canonicals = self._target_canonicals()
        if limit is not None:
            canonicals = canonicals[:limit]
        self.stdout.write(
            f"Targeting {len(canonicals)} canonical ingredients for discount refresh"
        )

        total = 0
        rohlik_count = 0
        kupi_count = 0

        # ── Rohlík search scraper (writes its own records, incl. discounts) ──
        if not canonicals:
            self.stdout.write("No published-recipe canonicals; skipping Rohlík scrape.")
        else:
            try:
                scraper = RohlikCzSearchScraper(delay_seconds=0.4, dry_run=dry_run)
                result = scraper.run(canonicals)
                rohlik_count = result.get('on_sale', 0)
                total += rohlik_count
                self.stdout.write(
                    f"Rohlík: priced={result.get('priced', 0)} "
                    f"missed={result.get('missed', 0)} on_sale={rohlik_count} "
                    f"dry_run={result.get('dry_run', dry_run)}"
                )
            except Exception as exc:  # noqa: BLE001 - daily job must not crash
                logger.warning("[scan_discounts] Rohlík scrape failed: %s", exc, exc_info=True)
                self.stderr.write(f"Rohlík scrape failed: {exc}")

        # ── kupi.cz leaflet scrapers (caller persists DISCOUNTED offers) ─────
        store_slugs = list(KUPI_STORE_CODES)
        for idx, store_slug in enumerate(store_slugs):
            shop_code = KUPI_STORE_CODES[store_slug]
            try:
                scraper = KupiCzScraper(store_slug=store_slug)
                offers = scraper.scrape()
                persisted = 0
                for offer in offers:
                    # A kupi.cz leaflet entry IS a promotion — leaflet pages
                    # carry only name + promo price (no struck-through original),
                    # so we don't gate on `<del>` markup. Instead we gate on a
                    # strict canonical match: an offer that maps to no canonical
                    # is dropped (pricing-integrity rule — never a discount that
                    # can't be tied to a real ingredient). Savings are computed
                    # downstream against the Rohlík baseline.
                    name = offer.get('ingredient_name') or offer.get('display_name') or ''
                    if _looks_nonfood(name):
                        continue
                    canonical = resolve_canonical(name)
                    if canonical is None:
                        continue
                    offer.setdefault('price_type', 'DISCOUNTED')
                    if not dry_run:
                        upsert_price_record(
                            shop_code=shop_code,
                            offer_data=offer,
                            valid_from=offer.get('valid_from') or timezone.now(),
                            valid_until=offer.get('valid_until')
                            or (timezone.now() + timedelta(days=7)),
                            canonical=canonical,
                        )
                    persisted += 1
                kupi_count += persisted
                total += persisted
                self.stdout.write(
                    f"kupi.cz/{store_slug} ({shop_code}): "
                    f"discounted offers refreshed={persisted}"
                )
            except Exception as exc:  # noqa: BLE001 - one store must not abort the rest
                logger.warning(
                    "[scan_discounts] kupi.cz/%s scrape failed: %s",
                    store_slug, exc, exc_info=True,
                )
                self.stderr.write(f"kupi.cz/{store_slug} scrape failed: {exc}")

            # Politeness pause between stores (skip after the last one).
            if idx < len(store_slugs) - 1:
                time.sleep(KUPI_INTER_STORE_DELAY)

        self.stdout.write(
            f"Discount sources: Rohlík={rohlik_count} kupi.cz={kupi_count}"
        )
        return total
