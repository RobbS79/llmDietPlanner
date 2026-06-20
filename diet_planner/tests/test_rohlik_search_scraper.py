"""
Unit tests for the Rohlik targeted *search* scraper.

These cover the pure parse + match-selection logic against a saved copy of a
real `search-metadata` response, with no network or DB. The match heuristic is
the quality-critical part: searching "rýže" must price plain rice, never the
rice-flour ("Rýžová mouka") that ranks first in Rohlik's results.
"""
import json
from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase

from diet_planner.scrapers.rohlik_cz_search import RohlikCzSearchScraper

FIXTURE = Path(__file__).parent / "fixtures" / "rohlik_search_ryze.json"


class RohlikSearchParseTest(SimpleTestCase):
    def setUp(self):
        self.scraper = RohlikCzSearchScraper(dry_run=True)
        self.payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.products = self.scraper._extract_products(self.payload)

    def test_extracts_all_products_with_prices(self):
        self.assertEqual(len(self.products), 3)
        self.assertTrue(all(p.price > 0 for p in self.products))

    def test_parses_price_and_package_from_payload(self):
        flour = next(p for p in self.products if "mouka" in p.name.lower())
        self.assertEqual(flour.price, Decimal("66.9"))
        self.assertEqual(flour.unit, "kg")
        self.assertEqual(flour.package_size, Decimal("1"))

    def test_parses_sale_fields(self):
        jasmine = next(p for p in self.products if "jasmín" in p.name.lower())
        self.assertTrue(jasmine.on_sale)
        self.assertEqual(jasmine.discount_percentage, 20)
        self.assertEqual(jasmine.original_price, Decimal("26.9"))

    def test_match_prefers_plain_rice_over_flour(self):
        best = self.scraper.pick_best_match("rýže", self.products)
        self.assertIsNotNone(best)
        self.assertNotIn("mouka", best.name.lower())
        # Both Kitchin rice items are valid; either is correct, flour is not.
        self.assertIn(best.external_id, {"1454459", "1454458"})

    def test_match_keeps_derivative_when_it_is_the_canonical(self):
        # When the searched canonical IS a derivative (flour), the "mouka"
        # penalty must not fire — flour should win, not be demoted.
        best = self.scraper.pick_best_match("rýžová mouka", self.products)
        self.assertIsNotNone(best)
        self.assertEqual(best.external_id, "1343853")  # the Rýžová mouka item

    def test_match_skips_out_of_stock(self):
        for p in self.products:
            p.in_stock = False
        self.assertIsNone(self.scraper.pick_best_match("rýže", self.products))

    def test_no_match_when_nothing_relevant(self):
        # A term unrelated to any product name should score everything <= 0.
        self.assertIsNone(self.scraper.pick_best_match("hovězí", self.products))
