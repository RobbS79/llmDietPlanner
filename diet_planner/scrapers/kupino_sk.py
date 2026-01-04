"""
Scraper for kupino.sk (Lidl Slovakia).
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


class KupinoSkScraper(BaseScraper):
    """
    Scraper for kupino.sk leaflet (Lidl Slovakia).
    
    Scrapes current Lidl SK offers from kupino.sk.
    """
    
    BASE_URL = "https://kupino.sk/lidl"
    
    def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape Lidl SK offers from kupino.sk.
        
        Returns:
            List of offer dictionaries
        """
        offers = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'sk-SK,sk;q=0.9,en;q=0.8',
            }
            
            response = requests.get(self.BASE_URL, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # kupino.sk structure: Look for product items
            product_items = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'product|item|offer', re.I))
            
            if not product_items:
                product_items = soup.find_all(['div', 'article'], {'data-product': True}) or \
                               soup.find_all('a', href=re.compile(r'/produkt|/product', re.I))
            
            logger.info(f"Found {len(product_items)} potential product items on kupino.sk")
            
            if not product_items:
                logger.warning(f"No product items found on kupino.sk - HTML structure may have changed")
                logger.debug(f"HTML sample (first 2000 chars): {response.text[:2000]}")
            
            parsed_count = 0
            for item in product_items[:100]:
                try:
                    offer_data = self._parse_product_item(item, response.url)
                    if offer_data:
                        offers.append(offer_data)
                        parsed_count += 1
                        logger.debug(f"Parsed item {parsed_count}: {offer_data.get('display_name')} - {offer_data.get('price')}")
                except Exception as e:
                    logger.debug(f"Error parsing product item: {e}", exc_info=True)
                    continue
            
            logger.info(f"Parsed {parsed_count}/{len(product_items[:100])} items successfully")
            
            if not offers:
                logger.warning(f"No offers parsed with primary method, trying fallback parsing")
                offers = self._parse_fallback(soup, response.url)
                logger.info(f"Fallback parsing found {len(offers)} offers")
            
            logger.info(f"Successfully scraped {len(offers)} offers from kupino.sk")
            
        except requests.RequestException as e:
            logger.error(f"Error fetching kupino.sk: {e}")
        except Exception as e:
            logger.error(f"Error scraping kupino.sk: {e}", exc_info=True)
        
        return offers
    
    def _parse_product_item(self, item, base_url: str) -> Dict[str, Any]:
        """Parse a single product item element."""
        offer = {}
        
        # Extract product name
        name_elem = item.find(['h2', 'h3', 'h4', 'a', 'span'], class_=re.compile(r'name|title|product-name', re.I))
        if not name_elem:
            name_elem = item.find(['h2', 'h3', 'h4', 'a', 'span'])
        
        if name_elem:
            display_name = name_elem.get_text(strip=True)
            if display_name:
                offer['display_name'] = display_name
                offer['ingredient_name'] = display_name
        
        # Extract price (EUR for Slovakia)
        price_elem = item.find(['span', 'div', 'strong'], class_=re.compile(r'price|cost|cena', re.I))
        if not price_elem:
            price_elem = item.find(string=re.compile(r'\d+[\s,.]*\d*\s*(€|EUR|euro)', re.I))
        
        if price_elem:
            if hasattr(price_elem, 'get_text'):
                price_text = price_elem.get_text(strip=True)
            else:
                price_text = str(price_elem).strip()
            
            price_match = re.search(r'(\d+[\s,.]?\d*)', price_text.replace(',', '.'))
            if price_match:
                try:
                    price_value = float(price_match.group(1).replace(' ', ''))
                    offer['price'] = Decimal(str(price_value))
                    offer['currency'] = 'EUR'
                except (ValueError, AttributeError):
                    pass
        
        # Extract unit
        unit_text = item.get_text()
        unit_match = re.search(r'(\d+)\s*(kg|g|ml|l|ks|piece|pieces)', unit_text, re.I)
        if unit_match:
            offer['unit'] = unit_match.group(2).lower()
        
        # Extract URL
        link_elem = item.find('a', href=True)
        if link_elem:
            href = link_elem['href']
            offer['source_url'] = urljoin(base_url, href)
        
        return offer if offer.get('display_name') else None
    
    def _parse_fallback(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Fallback parsing method."""
        offers = []
        text_content = soup.get_text()
        
        price_pattern = re.compile(r'([A-ZÁÄČĎÉÍĽĹŇÓÔŔŠŤÚÝŽa-záäčďéíľĺňóôŕšťúýž\s]+?)\s+(\d+[\s,.]?\d*)\s*(€|EUR)', re.UNICODE)
        matches = price_pattern.findall(text_content)
        
        for match in matches[:50]:
            product_name = match[0].strip()
            price_text = match[1].replace(',', '.').replace(' ', '')
            
            if len(product_name) > 3 and len(product_name) < 100:
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

