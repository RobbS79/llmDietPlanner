"""
Scraper for kupi.cz — Czech leaflet aggregator.

Supports multiple stores: Lidl, Albert, Kaufland, Penny Market, Tesco.
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
from .utils import parse_validity_window

logger = logging.getLogger(__name__)

# How many leaflets to crawl per store. The listing lists the current weekly
# food leaflet plus seasonal/upcoming ones; we want upcoming food deals too,
# but cap the crawl so a store can't balloon into dozens of HTTP fetches.
MAX_LEAFLETS_PER_STORE = 5

# kupi.cz slugs and leaflet URL prefixes per store
KUPI_CZ_STORES = {
    'lidl': {
        'listing_url': 'https://www.kupi.cz/letaky/lidl',
        'leaflet_prefix': '/letak/lidl-',
        'skip_words': ['leták', 'letak', 'platí', 'končí', 'od pondělí', 'od čtvrtka', 'od pátku', 'nabídka spotřebního', 'lidl leták'],
    },
    'albert': {
        'listing_url': 'https://www.kupi.cz/letaky/albert',
        'leaflet_prefix': '/letak/albert-',
        'skip_words': ['leták', 'letak', 'platí', 'končí', 'od pondělí', 'albert leták', 'katalog'],
    },
    'kaufland': {
        'listing_url': 'https://www.kupi.cz/letaky/kaufland',
        'leaflet_prefix': '/letak/kaufland-',
        'skip_words': ['leták', 'letak', 'platí', 'končí', 'od pondělí', 'kaufland leták', 'spotřební zboží'],
    },
    'penny-market': {
        'listing_url': 'https://www.kupi.cz/letaky/penny-market',
        'leaflet_prefix': '/letak/penny-',
        'skip_words': ['leták', 'letak', 'platí', 'končí', 'od pondělí', 'penny leták'],
    },
    'tesco': {
        'listing_url': 'https://www.kupi.cz/letaky/tesco',
        'leaflet_prefix': '/letak/tesco-',
        'skip_words': ['leták', 'letak', 'platí', 'končí', 'od pondělí', 'tesco leták'],
    },
}


class KupiCzScraper(BaseScraper):
    """
    Scraper for kupi.cz leaflets. Parametrized by store_slug.
    Default: 'lidl' (backward compatible).
    """

    def __init__(self, store_slug: str = 'lidl'):
        if store_slug not in KUPI_CZ_STORES:
            raise ValueError(f"Unknown kupi.cz store: {store_slug}. Available: {list(KUPI_CZ_STORES.keys())}")
        self.store_slug = store_slug
        config = KUPI_CZ_STORES[store_slug]
        self.base_url = config['listing_url']
        self.leaflet_prefix = config['leaflet_prefix']
        self.skip_words = config['skip_words']

    def scrape(self) -> List[Dict[str, Any]]:
        all_offers = []

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
            }

            logger.info(f"[kupi.cz/{self.store_slug}] Fetching listing page: {self.base_url}")
            response = requests.get(self.base_url, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')

            leaflet_links = self._extract_leaflet_links(soup, response.url)
            logger.info(f"[kupi.cz/{self.store_slug}] Found {len(leaflet_links)} leaflet pages")

            if not leaflet_links:
                logger.warning(f"[kupi.cz/{self.store_slug}] No leaflet links found, trying akcni-zbozi fallback")
                offers = self._parse_akcni_zbozi_section(soup, response.url)
                all_offers.extend(offers)
            else:
                # Crawl every leaflet (capped), not just the first. Upcoming
                # leaflets carry a future validity window and surface future deals.
                for leaflet_url, link_text in leaflet_links[:MAX_LEAFLETS_PER_STORE]:
                    try:
                        logger.info(f"[kupi.cz/{self.store_slug}] Scraping leaflet: {leaflet_url}")
                        leaflet_offers = self._scrape_leaflet_page(leaflet_url, headers, link_text)
                        all_offers.extend(leaflet_offers)
                        logger.info(f"[kupi.cz/{self.store_slug}] Found {len(leaflet_offers)} products in {leaflet_url}")
                    except Exception as e:
                        logger.error(f"[kupi.cz/{self.store_slug}] Error scraping leaflet {leaflet_url}: {e}", exc_info=True)

            filtered = self._filter_offers(all_offers)
            logger.info(f"[kupi.cz/{self.store_slug}] {len(all_offers)} raw -> {len(filtered)} valid offers")
            return filtered

        except requests.RequestException as e:
            logger.error(f"[kupi.cz/{self.store_slug}] HTTP error: {e}")
        except Exception as e:
            logger.error(f"[kupi.cz/{self.store_slug}] Scraping error: {e}", exc_info=True)

        return all_offers

    def _extract_leaflet_links(self, soup: BeautifulSoup, base_url: str) -> List[tuple]:
        """Return [(full_url, link_text), ...] for each distinct leaflet link.

        The link text (e.g. "Lidl leták od čtvrtka platí do neděle 31. 5.")
        is a fallback source for the validity window when the leaflet detail
        page header can't be parsed.
        """
        links = []
        seen = set()
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if href.startswith(self.leaflet_prefix) or (self.leaflet_prefix in href):
                full_url = urljoin(base_url, href)
                if full_url in seen:
                    continue
                seen.add(full_url)
                link_text = ' '.join(link.get_text(' ', strip=True).split())
                links.append((full_url, link_text))
        return links

    def _is_skip_title(self, text: str) -> bool:
        text_lower = text.lower()
        return any(w in text_lower for w in self.skip_words)

    def _filter_offers(self, offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filtered = []
        for offer in offers:
            name = offer.get('display_name', '')
            if not name or self._is_skip_title(name):
                continue
            if offer.get('price') and offer.get('price', 0) > 0:
                filtered.append(offer)
        return filtered

    def _scrape_leaflet_page(self, leaflet_url: str, headers: Dict[str, str], link_text: str = '') -> List[Dict[str, Any]]:
        offers = []
        try:
            response = requests.get(leaflet_url, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'

            soup = BeautifulSoup(response.text, 'html.parser')

            # Validity window: the detail-page H1 carries the full range
            # (e.g. "Lidl leták od čtvrtka, čt 28. 5. – ne 31. 5."). Fall back
            # to the listing link text, which usually has the "do <date>" end.
            valid_from, valid_until = self._extract_validity_window(soup, link_text)

            product_items = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'product|item|offer|card', re.I))

            if not product_items:
                product_items = soup.find_all(['div', 'article'], {'data-product': True}) or \
                               soup.find_all(['div', 'article'], {'data-id': True})

            if not product_items:
                all_elements = soup.find_all(['div', 'article', 'li', 'a'])
                for elem in all_elements:
                    text = elem.get_text()
                    if re.search(r'\d+[\s,.]?\d*\s*Kč', text):
                        product_items.append(elem)

            for item in product_items[:200]:
                try:
                    offer_data = self._parse_product_item(item, leaflet_url)
                    if offer_data and offer_data.get('display_name'):
                        offers.append(offer_data)
                except Exception:
                    continue

            if not offers:
                offers = self._parse_fallback_text(soup, leaflet_url)

            # Stamp the leaflet's validity window onto every offer it produced,
            # so the price-recording layer can store real valid_from/valid_until
            # (and bucket current vs. upcoming deals) instead of a generic TTL.
            if valid_from is not None or valid_until is not None:
                for offer in offers:
                    if valid_from is not None:
                        offer['valid_from'] = valid_from
                    if valid_until is not None:
                        offer['valid_until'] = valid_until

        except requests.RequestException as e:
            logger.error(f"[kupi.cz/{self.store_slug}] Error fetching leaflet {leaflet_url}: {e}")
        except Exception as e:
            logger.error(f"[kupi.cz/{self.store_slug}] Error parsing leaflet {leaflet_url}: {e}", exc_info=True)

        return offers

    def _extract_validity_window(self, soup: BeautifulSoup, link_text: str = ''):
        """Derive (valid_from, valid_until) for a leaflet.

        Prefers the detail-page H1 (carries the full "od <from> – <until>"
        range); falls back to the listing link text (typically just the
        "do <until>" end). Returns (None, None) when neither parses.
        """
        h1 = soup.find('h1')
        if h1:
            valid_from, valid_until = parse_validity_window(h1.get_text(' ', strip=True))
            if valid_from is not None or valid_until is not None:
                return valid_from, valid_until
        return parse_validity_window(link_text)

    def _parse_product_item(self, item, base_url: str) -> Dict[str, Any]:
        offer = {}

        name_elem = item.find(['h2', 'h3', 'h4', 'a', 'span', 'div'], class_=re.compile(r'name|title|product-name|heading', re.I))
        if not name_elem:
            name_elem = item.find(['h2', 'h3', 'h4', 'strong', 'b'])

        if name_elem:
            display_name = name_elem.get_text(strip=True)
            if display_name and len(display_name) > 2:
                if self._is_skip_title(display_name):
                    return None
                offer['display_name'] = display_name
                offer['ingredient_name'] = display_name

        price_text = None
        price_elem = item.find(['span', 'div', 'strong', 'b', 'p'], class_=re.compile(r'price|cost|cena|Price', re.I))

        if not price_elem:
            price_elem = item.find(string=re.compile(r'\d+[\s,.]*\d*\s*Kč', re.I))

        if not price_elem:
            item_text = item.get_text()
            price_match = re.search(r'(\d+[\s,.]?\d*)\s*Kč', item_text, re.I)
            if price_match:
                price_text = price_match.group(0)

        if price_elem:
            price_text = price_elem.get_text(strip=True) if hasattr(price_elem, 'get_text') else str(price_elem).strip()

        if price_text:
            price_match = re.search(r'(\d+[\s,.]?\d*)\s*Kč', price_text, re.I)
            if not price_match:
                price_match = re.search(r'(\d+[\s,.]?\d*)', price_text.replace(',', '.').replace(' ', ''))
            if price_match:
                try:
                    price_str = price_match.group(1).replace(',', '.').replace(' ', '')
                    price_value = float(price_str)
                    if price_value > 0:
                        offer['price'] = Decimal(str(price_value))
                        offer['currency'] = 'CZK'
                except (ValueError, AttributeError):
                    pass

        # Detect discount marker: struck-through original price in <del>/<s> tags.
        # When present, the leaflet is explicitly signaling a price reduction.
        original_price = None
        strike_elem = item.find(['del', 's'])
        if strike_elem:
            strike_text = strike_elem.get_text(strip=True)
            orig_match = re.search(r'(\d+[\s,.]?\d*)', strike_text.replace(',', '.').replace(' ', ''))
            if orig_match:
                try:
                    original_price = float(orig_match.group(1))
                except (ValueError, AttributeError):
                    original_price = None
        if original_price and offer.get('price') and original_price > float(offer['price']):
            offer['original_price'] = Decimal(str(original_price))
            offer['price_type'] = 'DISCOUNTED'
            offer['discount_percentage'] = int(round(100 * (original_price - float(offer['price'])) / original_price))

        unit_text = item.get_text()
        unit_match = re.search(r'(\d+)\s*(kg|g|ml|l|ks|piece|pieces|bal|balíček)', unit_text, re.I)
        if unit_match:
            offer['unit'] = unit_match.group(2).lower()

        link_elem = item.find('a', href=True)
        if link_elem:
            offer['source_url'] = urljoin(base_url, link_elem['href'])
        else:
            offer['source_url'] = base_url

        if not offer.get('display_name'):
            return None
        return offer

    def _parse_akcni_zbozi_section(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        offers = []
        akcni_section = soup.find(string=re.compile(r'Akční zboží', re.I))
        if akcni_section:
            parent = akcni_section.find_parent(['section', 'div', 'article'])
            if parent:
                product_links = parent.find_all('a', href=re.compile(r'/sleva/', re.I))
                for link in product_links:
                    try:
                        name_elem = link.find(['strong', 'span', 'div'], class_=re.compile(r'name|title', re.I))
                        if not name_elem:
                            name_elem = link.find('strong')
                        display_name = name_elem.get_text(strip=True) if name_elem else link.get_text(strip=True)
                        if not display_name or self._is_skip_title(display_name):
                            continue

                        parent_elem = link.find_parent(['div', 'article'])
                        if parent_elem:
                            price_text = parent_elem.get_text()
                            price_match = re.search(r'(\d+[\s,.]?\d*)\s*Kč', price_text, re.I)
                            if price_match:
                                price_str = price_match.group(1).replace(',', '.').replace(' ', '')
                                price_value = float(price_str)
                                if price_value > 0 and display_name:
                                    offers.append({
                                        'display_name': display_name,
                                        'ingredient_name': display_name,
                                        'price': Decimal(str(price_value)),
                                        'currency': 'CZK',
                                        'source_url': urljoin(base_url, link.get('href', '')),
                                    })
                    except Exception:
                        continue
        return offers

    def _parse_fallback_text(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        offers = []

        # Strategy 1: "Product za X.XX Kč" pattern
        menu_items = soup.find_all(['menu', 'div', 'span'], class_=re.compile(r'menu', re.I))
        for menu_item in menu_items:
            menu_text = menu_item.get_text(strip=True)
            za_pattern = re.compile(
                r'([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s\-]+?)\s+za\s+(\d+[\s,.]?\d*)\s*Kč',
                re.UNICODE | re.I,
            )
            za_match = za_pattern.search(menu_text)
            if za_match:
                product_name = za_match.group(1).strip()
                price_text = za_match.group(2).replace(',', '.').replace(' ', '')
                if 3 < len(product_name) < 200 and not self._is_skip_title(product_name):
                    try:
                        price_value = float(price_text)
                        if price_value > 0:
                            offers.append({
                                'display_name': product_name,
                                'ingredient_name': product_name,
                                'price': Decimal(str(price_value)),
                                'currency': 'CZK',
                                'source_url': base_url,
                            })
                    except ValueError:
                        pass

        # Strategy 2: /sleva/ links
        if not offers:
            product_links = soup.find_all('a', href=re.compile(r'/sleva/', re.I))
            for link in product_links:
                link_text = link.get_text(strip=True)
                price_match = re.search(r'(\d+[\s,.]?\d*)\s*Kč', link_text, re.I)
                if price_match and len(link_text) > 5:
                    product_name = re.sub(r'\s+za\s+\d+[\s,.]?\d*\s*Kč.*$', '', link_text, flags=re.I).strip()
                    if not product_name:
                        product_name = link_text.replace(price_match.group(0), '').strip()
                    if 3 < len(product_name) < 200 and not self._is_skip_title(product_name):
                        try:
                            price_value = float(price_match.group(1).replace(',', '.').replace(' ', ''))
                            if price_value > 0:
                                offers.append({
                                    'display_name': product_name,
                                    'ingredient_name': product_name,
                                    'price': Decimal(str(price_value)),
                                    'currency': 'CZK',
                                    'source_url': urljoin(base_url, link.get('href', '')),
                                })
                        except ValueError:
                            pass

        # Strategy 3: General text-based parsing
        if not offers:
            text_content = soup.get_text()
            price_pattern = re.compile(
                r'([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s\-]+?)\s+(\d+[\s,.]?\d*)\s*Kč',
                re.UNICODE | re.I,
            )
            matches = price_pattern.findall(text_content)
            for match in matches[:100]:
                product_name = re.sub(r'^[\-\s]+|[\-\s]+$', '', match[0].strip())
                price_text = match[1].replace(',', '.').replace(' ', '')
                if 3 < len(product_name) < 200 and not self._is_skip_title(product_name):
                    try:
                        price_value = float(price_text)
                        if price_value > 0:
                            offers.append({
                                'display_name': product_name,
                                'ingredient_name': product_name,
                                'price': Decimal(str(price_value)),
                                'currency': 'CZK',
                                'source_url': base_url,
                            })
                    except ValueError:
                        continue

        return offers
