"""
Rohlik.cz catalog scraper — sitemap-driven, BeautifulSoup-based.

Writes one StoreProduct + one PriceRecord(source_type=STORE_REGULAR) per
product. Canonical-ingredient matching is deliberately deferred to Phase C
(`match_canonical_ingredients` management command).

This scraper is scheduled — not on-demand. Catalog scrapes touch thousands
of pages and must not run on the user-facing request path.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from django.utils import timezone

from ..models import GroceryStore, PriceSourceType, ScrapeRun
from .price_recording import CONFIDENCE_CATALOG_DIRECT, upsert_price_record

logger = logging.getLogger(__name__)


SITEMAP_INDEX = "https://www.rohlik.cz/sitemap.xml"
PRODUCT_SITEMAP_HINTS = ("products", "produkty")
PRODUCT_URL_RE = re.compile(r"/(\d+)-([a-z0-9\-]+)$", re.I)
PRICE_RE = re.compile(r"(\d+[\s,.]\d+|\d+)\s*Kč", re.I)
PACKAGE_RE = re.compile(r"(\d+[\.,]?\d*)\s*(kg|g|ml|l|ks)", re.I)


@dataclass
class CatalogItem:
    external_id: str
    name: str
    price: Decimal
    package_size: Optional[Decimal]
    package_unit: str
    source_url: str


class RohlikCzCatalogScraper:
    STORE_CODE = "ROHLIK"
    BASE_URL = "https://www.rohlik.cz"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
    }

    REQUEST_DELAY_SECONDS = 0.3   # be polite — Rohlik product pages

    def __init__(
        self,
        *,
        limit: Optional[int] = None,
        dry_run: bool = False,
        batch_size: int = 50,
        delay_seconds: Optional[float] = None,
    ):
        self.limit = limit
        self.dry_run = dry_run
        self.batch_size = batch_size
        self.delay_seconds = self.REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ─── Sitemap discovery ───────────────────────────────────────────────

    def discover_product_urls(self) -> List[str]:
        """Walk the sitemap index, return all product detail URLs."""
        urls: List[str] = []
        for chunk_url in self._iter_product_sitemap_chunks():
            urls.extend(self._extract_product_urls(chunk_url))
            if self.limit and len(urls) >= self.limit:
                urls = urls[: self.limit]
                break
        logger.info(f"[rohlik catalog] discovered {len(urls)} product URLs")
        return urls

    def _iter_product_sitemap_chunks(self) -> Iterable[str]:
        try:
            resp = self.session.get(SITEMAP_INDEX, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "xml")
            for loc in soup.find_all("loc"):
                href = (loc.text or "").strip()
                if any(hint in href.lower() for hint in PRODUCT_SITEMAP_HINTS):
                    yield href
        except requests.RequestException as exc:
            logger.error(f"[rohlik catalog] sitemap index fetch failed: {exc}")

    def _extract_product_urls(self, chunk_url: str) -> List[str]:
        try:
            resp = self.session.get(chunk_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "xml")
            urls = [(loc.text or "").strip() for loc in soup.find_all("loc")]
            return [u for u in urls if PRODUCT_URL_RE.search(u or "")]
        except requests.RequestException as exc:
            logger.warning(f"[rohlik catalog] chunk fetch failed {chunk_url}: {exc}")
            return []

    # ─── Product page parsing ────────────────────────────────────────────

    def parse_product(self, url: str) -> Optional[CatalogItem]:
        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.debug(f"[rohlik catalog] page fetch failed {url}: {exc}")
            return None

        match = PRODUCT_URL_RE.search(url)
        external_id = match.group(1) if match else ""

        soup = BeautifulSoup(resp.text, "html.parser")

        # Rohlik is a client-side-rendered SPA; the authoritative price and name
        # live in the ld+json Product block, not in any static HTML element.
        product = self._extract_ldjson_product(soup)

        name = (product or {}).get("name") or ""
        if not name:
            name_el = soup.find("h1")
            name = (name_el.get_text(strip=True) if name_el else "").strip()
        if not name:
            return None

        price = self._extract_price(soup)
        if price is None:
            return None

        pkg_size, pkg_unit = self._extract_package(name, soup)

        return CatalogItem(
            external_id=external_id,
            name=name[:255],
            price=price,
            package_size=pkg_size,
            package_unit=pkg_unit,
            source_url=url,
        )

    def _extract_price(self, soup: BeautifulSoup) -> Optional[Decimal]:
        # Authoritative source: the ld+json Product block. Rohlik renders the
        # visible price with JS, so it is absent from static HTML — a regex over
        # page text grabs marketing decoys ("Doprava od 1 Kč") instead.
        product = self._extract_ldjson_product(soup)
        if product and product.get("price") is not None:
            return product["price"]

        # Legacy fallbacks, kept only for resilience if ld+json ever disappears.
        for sel in ("[data-test='product-price']", ".price__current", ".product-price"):
            node = soup.select_one(sel)
            if node:
                m = PRICE_RE.search(node.get_text(" ", strip=True))
                if m:
                    return self._normalize_price(m.group(1))
        return None

    def _extract_ldjson_product(self, soup: BeautifulSoup) -> Optional[dict]:
        """Parse the schema.org/Product ld+json block: price, name, stock.

        A Rohlik page carries several ld+json blocks (Organization,
        BreadcrumbList, Product); only the Product one carries an offer.
        """
        for tag in soup.find_all("script", type="application/ld+json"):
            raw = tag.string or tag.get_text() or ""
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except (ValueError, TypeError):
                continue

            for node in data if isinstance(data, list) else [data]:
                if not isinstance(node, dict):
                    continue
                node_type = node.get("@type")
                types = node_type if isinstance(node_type, list) else [node_type]
                if "Product" not in types:
                    continue

                offers = node.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                price = self._normalize_price(str(offers.get("price", "")))
                availability = str(offers.get("availability", "")).lower()

                return {
                    "name": (node.get("name") or "").strip()[:255],
                    "price": price,
                    "currency": offers.get("priceCurrency", ""),
                    "in_stock": "outofstock" not in availability,
                    "external_id": str(node.get("sku") or node.get("gtin13") or ""),
                }
        return None

    @staticmethod
    def _normalize_price(raw: str) -> Optional[Decimal]:
        cleaned = raw.replace("\xa0", "").replace(" ", "").replace(",", ".")
        try:
            value = Decimal(cleaned)
            return value if value > 0 else None
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _extract_package(name: str, soup: BeautifulSoup) -> tuple[Optional[Decimal], str]:
        for source in (name, soup.get_text(" ", strip=True)):
            m = PACKAGE_RE.search(source)
            if m:
                try:
                    size = Decimal(m.group(1).replace(",", "."))
                    return size, m.group(2).lower()
                except (InvalidOperation, ValueError):
                    continue
        return None, ""

    # ─── Top-level run ──────────────────────────────────────────────────

    def run(self) -> dict:
        store = GroceryStore.objects.filter(code=self.STORE_CODE).first()
        if not store:
            raise RuntimeError(f"No GroceryStore with code {self.STORE_CODE}")

        scrape_run = None
        if not self.dry_run:
            scrape_run = ScrapeRun.objects.create(
                store=store,
                status=ScrapeRun.Status.RUNNING,
                method=ScrapeRun.Method.CATALOG,
            )

        started = time.time()
        urls = self.discover_product_urls()

        valid_from = timezone.now()
        valid_until = valid_from + timedelta(days=30)

        recorded = 0
        skipped = 0
        for idx, url in enumerate(urls, start=1):
            item = self.parse_product(url)
            if not item:
                skipped += 1
                continue

            if self.dry_run:
                logger.info(
                    f"[rohlik catalog] [dry-run] {item.name} — {item.price} CZK "
                    f"(pkg={item.package_size}{item.package_unit})"
                )
                recorded += 1
            else:
                try:
                    upsert_price_record(
                        shop_code=self.STORE_CODE,
                        offer_data={
                            "ingredient_name": item.name,
                            "display_name": item.name,
                            "price": item.price,
                            "currency": store.currency,
                            "unit": item.package_unit,
                            "package_size": item.package_size,
                            "price_type": "REGULAR",
                            "source_url": item.source_url,
                            "external_id": item.external_id,
                        },
                        valid_from=valid_from,
                        valid_until=valid_until,
                        scrape_run=scrape_run,
                        confidence=CONFIDENCE_CATALOG_DIRECT,
                    )
                    recorded += 1
                except Exception as exc:
                    logger.warning(f"[rohlik catalog] upsert failed for {url}: {exc}")
                    skipped += 1

            if idx % self.batch_size == 0:
                logger.info(f"[rohlik catalog] progress: {idx}/{len(urls)} processed")

            if self.delay_seconds > 0 and idx < len(urls):
                time.sleep(self.delay_seconds)

        duration = time.time() - started
        result = {
            "store": self.STORE_CODE,
            "urls": len(urls),
            "recorded": recorded,
            "skipped": skipped,
            "duration_seconds": round(duration, 1),
            "dry_run": self.dry_run,
        }
        logger.info(f"[rohlik catalog] done: {result}")

        if scrape_run:
            scrape_run.status = ScrapeRun.Status.COMPLETED if skipped < len(urls) else ScrapeRun.Status.PARTIAL
            scrape_run.completed_at = timezone.now()
            scrape_run.duration_seconds = duration
            scrape_run.products_found = len(urls)
            scrape_run.prices_recorded = recorded
            scrape_run.errors_count = skipped
            scrape_run.save()

        return result
