"""
Scraper for kupino.sk — Slovak leaflet aggregator.

Supports multiple stores: Lidl, Kaufland.
The store_slug parameter controls which store's leaflets are scraped.
"""
from typing import List, Dict, Any
import logging
import requests
from bs4 import BeautifulSoup
from decimal import Decimal
import re
from urllib.parse import urljoin

from .base import BaseScraper

logger = logging.getLogger(__name__)

KUPINO_SK_STORES = {
    'lidl': {
        'listing_url': 'https://kupino.sk/lidl',
        'link_contains': '/lidl',
        'skip_words': ['leták', 'letak', 'platí', 'končí', 'od pondelka', 'lidl leták'],
    },
    'kaufland': {
        'listing_url': 'https://kupino.sk/kaufland',
        'link_contains': '/kaufland',
        'skip_words': ['leták', 'letak', 'platí', 'končí', 'od pondelka', 'kaufland leták'],
    },
}


class KupinoSkScraper(BaseScraper):
    """
    Scraper for kupino.sk leaflets. Parametrized by store_slug.
    Default: 'lidl' (backward compatible).
    """

    def __init__(self, store_slug: str = 'lidl'):
        if store_slug not in KUPINO_SK_STORES:
            raise ValueError(f"Unknown kupino.sk store: {store_slug}. Available: {list(KUPINO_SK_STORES.keys())}")
        self.store_slug = store_slug
        config = KUPINO_SK_STORES[store_slug]
        self.base_url = config['listing_url']
        self.link_contains = config['link_contains']
        self.skip_words = config['skip_words']

    def scrape(self) -> List[Dict[str, Any]]:
        offers = []

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'sk-SK,sk;q=0.9,en;q=0.8',
            }

            logger.info(f"[kupino.sk/{self.store_slug}] Fetching: {self.base_url}")
            response = requests.get(self.base_url, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')

            product_items = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'product|item|offer', re.I))

            if not product_items:
                product_items = soup.find_all(['div', 'article'], {'data-product': True}) or \
                               soup.find_all('a', href=re.compile(r'/produkt|/product', re.I))

            logger.info(f"[kupino.sk/{self.store_slug}] Found {len(product_items)} potential items")

            parsed_count = 0
            for item in product_items[:100]:
                try:
                    offer_data = self._parse_product_item(item, response.url)
                    if offer_data:
                        offers.append(offer_data)
                        parsed_count += 1
                except Exception:
                    continue

            logger.info(f"[kupino.sk/{self.store_slug}] Parsed {parsed_count}/{min(len(product_items), 100)} items")

            if not offers:
                logger.info(f"[kupino.sk/{self.store_slug}] Trying fallback parsing")
                offers = self._parse_fallback(soup, response.url)
                logger.info(f"[kupino.sk/{self.store_slug}] Fallback found {len(offers)} offers")

            logger.info(f"[kupino.sk/{self.store_slug}] Total: {len(offers)} offers")

        except requests.RequestException as e:
            logger.error(f"[kupino.sk/{self.store_slug}] HTTP error: {e}")
        except Exception as e:
            logger.error(f"[kupino.sk/{self.store_slug}] Scraping error: {e}", exc_info=True)

        return offers

    def _is_skip_title(self, text: str) -> bool:
        text_lower = text.lower()
        return any(w in text_lower for w in self.skip_words)

    def _parse_product_item(self, item, base_url: str) -> Dict[str, Any]:
        offer = {}

        name_elem = item.find(['h2', 'h3', 'h4', 'a', 'span'], class_=re.compile(r'name|title|product-name', re.I))
        if not name_elem:
            name_elem = item.find(['h2', 'h3', 'h4', 'a', 'span'])

        if name_elem:
            display_name = name_elem.get_text(strip=True)
            if display_name and not self._is_skip_title(display_name):
                offer['display_name'] = display_name
                offer['ingredient_name'] = display_name

        price_elem = item.find(['span', 'div', 'strong'], class_=re.compile(r'price|cost|cena', re.I))
        if not price_elem:
            price_elem = item.find(string=re.compile(r'\d+[\s,.]*\d*\s*(€|EUR|euro)', re.I))

        if price_elem:
            price_text = price_elem.get_text(strip=True) if hasattr(price_elem, 'get_text') else str(price_elem).strip()
            price_match = re.search(r'(\d+[\s,.]?\d*)', price_text.replace(',', '.'))
            if price_match:
                try:
                    price_value = float(price_match.group(1).replace(' ', ''))
                    offer['price'] = Decimal(str(price_value))
                    offer['currency'] = 'EUR'
                except (ValueError, AttributeError):
                    pass

        unit_text = item.get_text()
        unit_match = re.search(r'(\d+)\s*(kg|g|ml|l|ks|piece|pieces)', unit_text, re.I)
        if unit_match:
            offer['unit'] = unit_match.group(2).lower()

        link_elem = item.find('a', href=True)
        if link_elem:
            offer['source_url'] = urljoin(base_url, link_elem['href'])

        return offer if offer.get('display_name') else None

    def _parse_fallback(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        offers = []
        text_content = soup.get_text()

        price_pattern = re.compile(
            r'([A-ZÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽa-záäčďéíľĺňóôŕšťúýž\s]+?)\s+(\d+[\s,.]?\d*)\s*(€|EUR)',
            re.UNICODE,
        )
        matches = price_pattern.findall(text_content)

        for match in matches[:50]:
            product_name = match[0].strip()
            price_text = match[1].replace(',', '.').replace(' ', '')
            if 3 < len(product_name) < 100 and not self._is_skip_title(product_name):
                try:
                    price_value = float(price_text)
                    offers.append({
                        'display_name': product_name,
                        'ingredient_name': product_name,
                        'price': Decimal(str(price_value)),
                        'currency': 'EUR',
                        'source_url': base_url,
                    })
                except ValueError:
                    continue

        return offers
