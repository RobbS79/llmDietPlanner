"""scan_discounts expires stale leaflet records so the click-time read is honest."""
import datetime as dt
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from diet_planner.models import (
    GroceryStore, PriceRecord, PriceSourceType, StoreProduct,
)


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
        # Sanity: it's not in the current() window.
        self.assertNotIn(stale, PriceRecord.objects.current())

        out = StringIO()
        call_command('scan_discounts', '--no-scrape', stdout=out)

        stale.refresh_from_db()
        self.assertTrue(stale.is_expired)  # explicitly past its validity
        self.assertIn('expired', out.getvalue().lower())
