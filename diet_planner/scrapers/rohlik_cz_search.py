"""
Rohlik.cz targeted search scraper.

Unlike the sitemap crawler (``rohlik_cz_catalog``), which downloads all ~22k
product pages indiscriminately (~7h, mostly non-food), this scraper is driven
by the *canonical ingredients our recipes actually use*. For each canonical it
hits Rohlik's JSON search endpoint once, picks the best in-stock match, and
writes a StoreProduct (pre-mapped to that canonical) + PriceRecord.

Benefits over the crawler:
  * One request per ingredient — hundreds of calls (minutes), not 22k (hours).
  * The price attaches to a *known* canonical, so no separate
    `match_canonical_ingredients` pass and no mis-mapping.
  * The search payload carries discount fields (goodPrice / originalPrice /
    sale %), so promotional offers are captured in the same pass.

The endpoint returns fully-formed price data (no per-product page fetch):
    GET /services/frontend-service/search-metadata?search=<term>&offset=0&limit=N
    -> {"data": {"productList": [ {productId, productName, price:{full},
        pricePerUnit:{full}, originalPrice:{full}, goodPrice, unit,
        textualAmount, inStock, brand, link}, ... ]}}
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional

import requests
from django.utils import timezone

from ..models import CanonicalIngredient, GroceryStore, ScrapeRun
from .price_recording import upsert_price_record
from .utils import normalize_ingredient_name

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.rohlik.cz/services/frontend-service/search-metadata"
PACKAGE_RE = re.compile(r"(\d+[.,]?\d*)\s*(kg|g|ml|l|ks)", re.I)

# Tokens that mark a *derived* product, not the plain staple. Searching "rýže"
# surfaces "Rýžová mouka" (rice flour) and "Rýžový nápoj" (rice milk) — never
# the right price for a recipe that wants plain rice.
DERIVATIVE_TOKENS = {
    "mouka", "moučka", "nápoj", "napoj", "chlebíčky", "chlebicky", "chipsy",
    "vločky", "vlocky", "sušenky", "susenky", "tyčinky", "tycinky", "olej",
    "krekry", "krekery", "pufované", "extrakt", "sirup", "pasta", "protein",
}


@dataclass
class SearchProduct:
    external_id: str
    name: str
    brand: str
    price: Decimal
    price_per_unit: Optional[Decimal]
    unit: str
    package_size: Optional[Decimal]
    in_stock: bool
    on_sale: bool
    original_price: Optional[Decimal]
    discount_percentage: Optional[int]
    source_url: str


class RohlikCzSearchScraper:
    STORE_CODE = "ROHLIK"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        "Accept": "application/json",
    }
    REQUEST_DELAY_SECONDS = 0.4

    def __init__(
        self,
        *,
        limit_per_term: int = 12,
        dry_run: bool = False,
        delay_seconds: Optional[float] = None,
    ):
        self.limit_per_term = limit_per_term
        self.dry_run = dry_run
        self.delay_seconds = self.REQUEST_DELAY_SECONDS if delay_seconds is None else delay_seconds
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ─── Network ─────────────────────────────────────────────────────────

    def _fetch(self, term: str) -> Optional[dict]:
        try:
            resp = self.session.get(
                SEARCH_URL,
                params={"search": term, "offset": 0, "limit": self.limit_per_term},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("[rohlik search] '%s' fetch failed: %s", term, exc)
            return None

    def search(self, term: str) -> List[SearchProduct]:
        return self._extract_products(self._fetch(term))

    # ─── Parsing (pure) ──────────────────────────────────────────────────

    def _extract_products(self, payload: Optional[dict]) -> List[SearchProduct]:
        data = (payload or {}).get("data") or {}
        out: List[SearchProduct] = []
        for raw in data.get("productList", []) or []:
            parsed = self._parse_product(raw)
            if parsed:
                out.append(parsed)
        return out

    def _parse_product(self, raw: dict) -> Optional[SearchProduct]:
        price = self._money(raw.get("price"))
        name = (raw.get("productName") or "").strip()
        if price is None or not name:
            return None

        original = self._money(raw.get("originalPrice"))
        pct = raw.get("goodPriceSalePercentage")
        on_sale = bool(raw.get("goodPrice"))
        pkg_size, pkg_unit = self._parse_amount(raw.get("textualAmount"), raw.get("unit"))

        return SearchProduct(
            external_id=str(raw.get("productId") or ""),
            name=name[:255],
            brand=(raw.get("brand") or "")[:100],
            price=price,
            price_per_unit=self._money(raw.get("pricePerUnit")),
            unit=pkg_unit,
            package_size=pkg_size,
            in_stock=bool(raw.get("inStock", True)),
            on_sale=on_sale,
            original_price=original if on_sale else None,
            discount_percentage=int(pct) if on_sale and pct else None,
            source_url=raw.get("link") or "",
        )

    @staticmethod
    def _money(node) -> Optional[Decimal]:
        """Rohlik prices are {full, whole, fraction, currency}; use `full`."""
        if not isinstance(node, dict):
            return None
        try:
            value = Decimal(str(node.get("full")))
            return value if value > 0 else None
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _parse_amount(textual, unit) -> tuple[Optional[Decimal], str]:
        if textual:
            m = PACKAGE_RE.search(str(textual))
            if m:
                try:
                    return Decimal(m.group(1).replace(",", ".")), m.group(2).lower()
                except (InvalidOperation, ValueError):
                    pass
        return None, (unit or "")[:10]

    # ─── Match selection ─────────────────────────────────────────────────

    def pick_best_match(self, term: str, products: List[SearchProduct]) -> Optional[SearchProduct]:
        """Pick the product that best *is* the searched staple.

        In-stock only; score by name relevance, demoting derived products
        (flour/milk/chips) and overly long names (branded variants).
        """
        term_norm = normalize_ingredient_name(term)
        scored = [
            (self._score(term_norm, p), p)
            for p in products
            if p.in_stock
        ]
        scored = [(s, p) for s, p in scored if s > 0]
        if not scored:
            return None
        scored.sort(key=lambda sp: sp[0], reverse=True)
        return scored[0][1]

    @staticmethod
    def _score(term_norm: str, product: SearchProduct) -> float:
        name = normalize_ingredient_name(product.name)
        words = name.split()
        term_words = set(term_norm.split())
        score = 0.0
        if term_norm and term_norm in name:
            score += 10                      # full phrase appears verbatim
        if term_norm in words:               # whole-word match, strongest signal
            score += 6
        score += 4 * len(term_words & set(words))   # per-word overlap credit
        # Penalize derivative products (flour/milk/chips) — but only when the
        # derivative token is NOT itself what we searched for (e.g. a flour
        # canonical legitimately wants "mouka").
        if any(tok in words for tok in DERIVATIVE_TOKENS if tok not in term_words):
            score -= 9
        score -= 0.5 * max(0, len(words) - 2)  # prefer concise staple names
        return score

    # ─── Top-level run ───────────────────────────────────────────────────

    def run(self, canonicals: Iterable[CanonicalIngredient]) -> dict:
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

        valid_from = timezone.now()
        valid_until = valid_from + timedelta(days=30)
        priced = 0
        missed = 0
        on_sale = 0

        canonicals = list(canonicals)
        for idx, canonical in enumerate(canonicals, start=1):
            term = canonical.name_cs or canonical.name
            if not term:
                missed += 1
                continue

            products = self.search(term)
            best = self.pick_best_match(term, products)
            if self.delay_seconds:
                time.sleep(self.delay_seconds)

            if not best:
                missed += 1
                logger.info("[rohlik search] no match for '%s'", term)
                continue

            if self.dry_run:
                priced += 1
                if best.on_sale:
                    on_sale += 1
                logger.info(
                    "[rohlik search] [dry-run] %s -> %s %s Kč%s",
                    term, best.name, best.price,
                    f" (sale -{best.discount_percentage}%)" if best.on_sale else "",
                )
                continue

            record = upsert_price_record(
                shop_code=self.STORE_CODE,
                offer_data={
                    "ingredient_name": best.name,
                    "display_name": best.name,
                    "price": best.price,
                    "currency": store.currency,
                    "unit": best.unit,
                    "package_size": best.package_size,
                    "external_id": best.external_id,
                    "source_url": best.source_url,
                    "price_type": "DISCOUNTED" if best.on_sale else "STORE_REGULAR",
                    "original_price": best.original_price,
                    "discount_percentage": best.discount_percentage,
                },
                valid_from=valid_from,
                valid_until=valid_until,
                scrape_run=scrape_run,
            )
            if record is None:
                missed += 1
                continue

            # Attach to the canonical we searched for — pre-mapped, no LLM pass.
            sp = record.store_product
            if sp.canonical_ingredient_id != canonical.id:
                sp.canonical_ingredient = canonical
                sp.save(update_fields=["canonical_ingredient"])
            priced += 1
            if best.on_sale:
                on_sale += 1

        if scrape_run is not None:
            scrape_run.status = ScrapeRun.Status.COMPLETED
            scrape_run.completed_at = timezone.now()
            scrape_run.products_found = priced
            scrape_run.save(update_fields=["status", "completed_at", "products_found"])

        result = {
            "canonicals": len(canonicals),
            "priced": priced,
            "missed": missed,
            "on_sale": on_sale,
            "dry_run": self.dry_run,
        }
        logger.info("[rohlik search] done: %s", result)
        return result
