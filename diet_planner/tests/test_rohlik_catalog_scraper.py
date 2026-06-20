"""
Unit tests for the Rohlik.cz catalog scraper's price extraction.

Rohlik is a client-side-rendered (Next.js) SPA: the displayed price is NOT
present in any static HTML element. The only reliable price in the server
response lives in the `application/ld+json` Product block. These tests pin
that behaviour so a future Rohlik markup change fails loudly instead of
silently writing garbage prices (the prod "1 Kč" / 0-products regression).
"""
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup
from django.test import SimpleTestCase

from diet_planner.scrapers.rohlik_cz_catalog import RohlikCzCatalogScraper

FIXTURE = Path(__file__).parent / "fixtures" / "rohlik_product.html"


class RohlikPriceExtractionTest(SimpleTestCase):
    def setUp(self):
        self.scraper = RohlikCzCatalogScraper(dry_run=True)
        self.soup = BeautifulSoup(FIXTURE.read_text(encoding="utf-8"), "html.parser")

    def test_extracts_real_price_from_ldjson(self):
        # The real price is 20.90 CZK, only available in the ld+json Product block.
        self.assertEqual(self.scraper._extract_price(self.soup), Decimal("20.90"))

    def test_does_not_return_decoy_marketing_price(self):
        # The old regex fallback grabbed "1 Kč" from a marketing banner. Never again.
        self.assertNotEqual(self.scraper._extract_price(self.soup), Decimal("1"))

    def test_ldjson_product_parsed_with_name_and_availability(self):
        product = self.scraper._extract_ldjson_product(self.soup)
        self.assertIsNotNone(product)
        self.assertEqual(product["price"], Decimal("20.90"))
        self.assertEqual(product["name"], "Racio Chlebíčky rýžové")
        self.assertTrue(product["in_stock"])

    def test_missing_ldjson_returns_none_price(self):
        bare = BeautifulSoup("<html><body><h1>No price here</h1></body></html>", "html.parser")
        self.assertIsNone(self.scraper._extract_price(bare))
