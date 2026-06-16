"""
Tests for leaflet validity-window parsing and current/upcoming bucketing.

Covers:
- parse_validity_window() on the real Czech phrasings kupi.cz emits
  (full "od <from> – <until>" range vs. single "platí do <until>")
- year inference across the December -> January boundary
- PriceRecord .current() excludes future-dated rows; .upcoming() returns them
"""
import datetime as dt
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from diet_planner.scrapers.utils import parse_validity_window


def _now(year, month, day):
    return timezone.make_aware(dt.datetime(year, month, day, 12, 0, 0))


class ParseValidityWindowTest(SimpleTestCase):
    # Pure function, no DB — runs on any backend.
    def test_full_range_from_h1(self):
        # Real kupi.cz leaflet H1 (nbsp normalized): both endpoints present.
        now = _now(2026, 5, 28)
        vf, vu = parse_validity_window(
            "Lidl leták od čtvrtka , čt 28.\xa05. – ne 31.\xa05.", now=now
        )
        self.assertIsNotNone(vf)
        self.assertIsNotNone(vu)
        self.assertEqual(vf.date(), dt.date(2026, 5, 28))
        self.assertEqual(vu.date(), dt.date(2026, 5, 31))
        # from at start of day, until at end of day
        self.assertEqual((vf.hour, vf.minute), (0, 0))
        self.assertEqual((vu.hour, vu.minute, vu.second), (23, 59, 59))

    def test_single_until_date_from_listing_text(self):
        now = _now(2026, 5, 28)
        vf, vu = parse_validity_window("platí do neděle 31. 5.", now=now)
        self.assertIsNone(vf)
        self.assertEqual(vu.date(), dt.date(2026, 5, 31))

    def test_upcoming_window_resolves_in_future(self):
        now = _now(2026, 5, 28)
        vf, vu = parse_validity_window("od 5. 6. do 11. 6.", now=now)
        self.assertEqual(vf.date(), dt.date(2026, 6, 5))
        self.assertEqual(vu.date(), dt.date(2026, 6, 11))
        self.assertGreater(vf, now)  # genuinely upcoming

    def test_year_inference_across_december_boundary(self):
        # Scraped on 28 Dec 2026, a "5. 1." date belongs to Jan 2027, not 2026.
        now = _now(2026, 12, 28)
        vf, vu = parse_validity_window("od 28. 12. do 5. 1.", now=now)
        self.assertEqual(vf.date(), dt.date(2026, 12, 28))
        self.assertEqual(vu.date(), dt.date(2027, 1, 5))

    def test_no_dates_returns_none_pair(self):
        self.assertEqual(parse_validity_window("Lidl leták"), (None, None))
        self.assertEqual(parse_validity_window(""), (None, None))


class PriceRecordBucketingTest(TestCase):
    """current() must exclude future-dated rows; upcoming() must return them."""

    def _store_product(self):
        from diet_planner.models import GroceryStore, StoreProduct
        # get_or_create: LIDL_CZ is seeded by migration 0017.
        store, _ = GroceryStore.objects.get_or_create(
            code='LIDL_CZ',
            defaults=dict(name='Lidl', country='CZ', currency='CZK'),
        )
        return StoreProduct.objects.create(
            store=store, name='Mléko', normalized_name='mléko', is_active=True
        )

    def _record(self, sp, valid_from, valid_until):
        from diet_planner.models import PriceRecord, PriceSourceType
        return PriceRecord.objects.create(
            store_product=sp,
            price=Decimal('18.90'),
            currency='CZK',
            source_type=PriceSourceType.LEAFLET_DISCOUNT,
            valid_from=valid_from,
            valid_until=valid_until,
            scraped_at=timezone.now(),
        )

    def test_current_excludes_future_and_upcoming_returns_it(self):
        from diet_planner.models import PriceRecord
        sp = self._store_product()
        now = timezone.now()
        current = self._record(sp, now - dt.timedelta(days=1), now + dt.timedelta(days=2))
        upcoming = self._record(sp, now + dt.timedelta(days=3), now + dt.timedelta(days=10))

        current_ids = set(PriceRecord.objects.current().values_list('id', flat=True))
        upcoming_ids = set(PriceRecord.objects.upcoming().values_list('id', flat=True))

        self.assertIn(current.id, current_ids)
        self.assertNotIn(upcoming.id, current_ids)
        self.assertIn(upcoming.id, upcoming_ids)
        self.assertNotIn(current.id, upcoming_ids)
