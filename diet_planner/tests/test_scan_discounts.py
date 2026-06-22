"""scan_discounts expires stale leaflet records so the click-time read is honest."""
import datetime as dt
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from diet_planner.models import (
    CanonicalIngredient, CuratedRecipe, GroceryStore, PriceRecord,
    PriceSourceType, StoreProduct,
)


# Patch the scrapers at the import site used in scan_discounts.py so NOTHING
# touches the network. Constructing the real classes is fine (no network in
# __init__); only the network methods (run / scrape) are mocked.
ROHLIK_RUN = 'diet_planner.management.commands.scan_discounts.RohlikCzSearchScraper.run'
KUPI_SCRAPE = 'diet_planner.management.commands.scan_discounts.KupiCzScraper.scrape'


def _discounted_offer():
    return {
        'ingredient_name': 'kuřecí prsa',
        'display_name': 'Kuřecí prsní řízek',
        'price': Decimal('89.90'),
        'currency': 'CZK',
        'unit': 'kg',
        'price_type': 'DISCOUNTED',
        'original_price': Decimal('129.90'),
        'discount_percentage': 31,
        'source_url': 'https://www.kupi.cz/sleva/kureci-prsa',
    }


def _regular_offer():
    return {
        'ingredient_name': 'mléko',
        'display_name': 'Mléko polotučné 1l',
        'price': Decimal('19.90'),
        'currency': 'CZK',
        'unit': 'l',
        'source_url': 'https://www.kupi.cz/sleva/mleko',
    }


class ScanDiscountsExpiryTests(TestCase):
    def _store(self, code='LIDL_CZ', name='Lidl'):
        # get_or_create: migration 0017 seeds these stores into the test DB, so
        # a plain create() would collide on the unique `code`.
        store, _ = GroceryStore.objects.get_or_create(
            code=code,
            defaults=dict(
                name=name, chain=code.split('_')[0],
                country='CZ', currency='CZK', is_active=True,
            ),
        )
        return store

    def test_expires_past_leaflet_records(self):
        store = self._store('LIDL_CZ', 'Lidl')
        prod = StoreProduct.objects.create(
            store=store, name='Máslo', normalized_name='butter', is_active=True,
        )
        now = timezone.now()
        past = now - dt.timedelta(days=2)
        stale = PriceRecord.objects.create(
            store_product=prod, price=Decimal('30'), currency='CZK',
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_from=now - dt.timedelta(days=5),
            valid_until=past,
            scraped_at=now - dt.timedelta(days=5),
        )
        # A still-valid leaflet record on a second product: its valid_until is
        # in the future, so the expiry filter MUST NOT count it.
        fresh_prod = StoreProduct.objects.create(
            store=store, name='Mléko', normalized_name='milk', is_active=True,
        )
        fresh = PriceRecord.objects.create(
            store_product=fresh_prod, price=Decimal('20'), currency='CZK',
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_from=now - dt.timedelta(days=1),
            valid_until=now + dt.timedelta(days=5),
            scraped_at=now - dt.timedelta(days=1),
        )
        # Sanity: stale is out of the current() window; fresh is still in it.
        self.assertNotIn(stale, PriceRecord.objects.current())
        self.assertIn(fresh, PriceRecord.objects.current())

        out = StringIO()
        call_command('scan_discounts', '--no-scrape', stdout=out)

        stale.refresh_from_db()
        self.assertTrue(stale.is_expired)  # explicitly past its validity
        # Exactly one record (the stale one) is past valid_until; the fresh
        # future-dated leaflet record must be excluded from the count.
        self.assertIn('expired (past valid_until): 1', out.getvalue())


class ScanDiscountsScrapeTests(TestCase):
    """Live-scrape body, with all scrapers MOCKED — zero network access."""

    def _store(self, code, name):
        store, _ = GroceryStore.objects.get_or_create(
            code=code,
            defaults=dict(
                name=name, chain=code.split('_')[0],
                country='CZ', currency='CZK', is_active=True,
            ),
        )
        return store

    def _seed_canonical_and_recipe(self):
        canon = CanonicalIngredient.objects.create(
            name='chicken breast', name_cs='kuřecí prsa', slug='chicken-breast',
        )
        CuratedRecipe.objects.create(
            name_cs='Kuřecí salát',
            source_url='https://example.com/recipe',
            source_name='Example',
            status=CuratedRecipe.Status.PUBLISHED,
            ingredients=[{'name': 'kuřecí prsa', 'canonical': 'chicken-breast'}],
        )
        return canon

    @mock.patch('diet_planner.management.commands.scan_discounts.time.sleep', lambda *_: None)
    @mock.patch(KUPI_SCRAPE)
    @mock.patch(ROHLIK_RUN)
    def test_scrape_refreshes_from_mocked_scrapers(self, mock_rohlik, mock_kupi):
        self._seed_canonical_and_recipe()
        # kupi.cz stores must exist for upsert_price_record to persist.
        for code, name in [
            ('LIDL_CZ', 'Lidl'), ('ALBERT_CZ', 'Albert'),
            ('KAUFLAND_CZ', 'Kaufland'), ('PENNY_CZ', 'Penny'),
            ('TESCO_CZ', 'Tesco'),
        ]:
            self._store(code, name)

        mock_rohlik.return_value = {
            'canonicals': 1, 'priced': 1, 'missed': 0, 'on_sale': 2, 'dry_run': False,
        }
        # One DISCOUNTED + one regular offer per store call.
        mock_kupi.return_value = [_discounted_offer(), _regular_offer()]

        out = StringIO()
        call_command('scan_discounts', stdout=out)
        output = out.getvalue()

        # Rohlík on_sale=2 + 5 stores × 1 DISCOUNTED offer each = 7.
        self.assertIn('Discount records refreshed: 7', output)

        # LEAFLET_DISCOUNT records were created for the DISCOUNTED offers only.
        leaflet = PriceRecord.objects.filter(
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
        )
        self.assertEqual(leaflet.count(), 5)  # one per store
        # The regular offer ('mléko') resolves to no seeded canonical, so under
        # the strict-canonical rule it must NOT be persisted at all.
        self.assertFalse(
            PriceRecord.objects.filter(price=Decimal('19.90')).exists()
        )
        # Every persisted leaflet record is mapped to its canonical, so the deal
        # engine (which matches strictly by canonical_id) can surface it.
        canon = CanonicalIngredient.objects.get(slug='chicken-breast')
        for rec in leaflet:
            self.assertEqual(rec.store_product.canonical_ingredient_id, canon.id)
        # Rohlík run was invoked once; kupi scrape once per store (5).
        self.assertEqual(mock_rohlik.call_count, 1)
        self.assertEqual(mock_kupi.call_count, 5)

    @mock.patch('diet_planner.management.commands.scan_discounts.time.sleep', lambda *_: None)
    @mock.patch(KUPI_SCRAPE)
    @mock.patch(ROHLIK_RUN)
    def test_leaflet_offer_without_struck_original_persists_mapped(self, mock_rohlik, mock_kupi):
        """kupi.cz leaflet cards carry no original price (only name + promo
        price). Such an offer must still persist as a LEAFLET_DISCOUNT mapped
        to its canonical; an offer whose name resolves to no canonical is
        skipped (strict-canonical rule — never a floating/fabricated discount).
        """
        canon = self._seed_canonical_and_recipe()
        # Canonicals the retail-noise names would mis-map to via the loose
        # resolver — present so the test proves the precision GUARD (not a
        # missing canonical) is what drops them.
        CanonicalIngredient.objects.create(name='pasta', name_cs='těstoviny', slug='pasta')
        CanonicalIngredient.objects.create(name='avocado', name_cs='avokádo', slug='avocado')
        from diet_planner.services.canonical_lookup import clear_cache
        clear_cache()  # the normalized index is process-cached; rebuild for this DB
        for code, name in [
            ('LIDL_CZ', 'Lidl'), ('ALBERT_CZ', 'Albert'),
            ('KAUFLAND_CZ', 'Kaufland'), ('PENNY_CZ', 'Penny'),
            ('TESCO_CZ', 'Tesco'),
        ]:
            self._store(code, name)

        mock_rohlik.return_value = {
            'canonicals': 1, 'priced': 1, 'missed': 0, 'on_sale': 0, 'dry_run': False,
        }
        # No price_type, no original_price — exactly what the live kupi parser
        # produces now. One genuine food offer + three that must be dropped:
        # an unresolvable name, and two retail-noise names that DO resolve to a
        # canonical but aren't that food (toothpaste -> pasta, spice -> avocado).
        resolvable = {
            'ingredient_name': 'kuřecí prsa', 'display_name': 'Kuřecí prsa Vodňany',
            'price': Decimal('99.90'), 'currency': 'CZK', 'unit': 'kg',
            'source_url': 'https://www.kupi.cz/x',
        }
        unresolvable = {
            'ingredient_name': 'pivo plzeňský prazdroj', 'display_name': 'Pivo',
            'price': Decimal('25.90'), 'currency': 'CZK',
            'source_url': 'https://www.kupi.cz/y',
        }
        toothpaste = {  # "Pasta na zuby" -> resolver strips 'na zuby' -> pasta
            'ingredient_name': 'pasta na zuby odol', 'display_name': 'Pasta na zuby',
            'price': Decimal('39.90'), 'currency': 'CZK',
            'source_url': 'https://www.kupi.cz/z',
        }
        spice = {  # "Koření Avokádo" -> resolver strips 'koření' -> avocado
            'ingredient_name': 'koření avokádo', 'display_name': 'Koření Avokádo',
            'price': Decimal('8.90'), 'currency': 'CZK',
            'source_url': 'https://www.kupi.cz/w',
        }
        mock_kupi.return_value = [resolvable, unresolvable, toothpaste, spice]

        out = StringIO()
        call_command('scan_discounts', stdout=out)

        leaflet = PriceRecord.objects.filter(
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
        )
        self.assertEqual(leaflet.count(), 5)  # resolvable offer, one per store
        for rec in leaflet:
            self.assertEqual(rec.store_product.canonical_ingredient_id, canon.id)
            self.assertIsNone(rec.original_price)  # no struck original required
        # The unresolvable offer and both retail-noise offers are never persisted.
        for price in (Decimal('25.90'), Decimal('39.90'), Decimal('8.90')):
            self.assertFalse(PriceRecord.objects.filter(price=price).exists())

    @mock.patch('diet_planner.management.commands.scan_discounts.time.sleep', lambda *_: None)
    @mock.patch(KUPI_SCRAPE)
    @mock.patch(ROHLIK_RUN)
    def test_scrape_survives_scraper_failure(self, mock_rohlik, mock_kupi):
        self._seed_canonical_and_recipe()
        mock_rohlik.return_value = {
            'canonicals': 1, 'priced': 1, 'missed': 0, 'on_sale': 3, 'dry_run': False,
        }
        # Every kupi store raises — must not abort; Rohlík count still reported.
        mock_kupi.side_effect = RuntimeError('boom')

        out = StringIO()
        # Must NOT raise.
        call_command('scan_discounts', stdout=out)
        output = out.getvalue()

        # Rohlík's 3 still counted; kupi contributed 0.
        self.assertIn('Discount records refreshed: 3', output)
        # All 5 stores were attempted despite each failing.
        self.assertEqual(mock_kupi.call_count, 5)
