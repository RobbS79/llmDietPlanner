"""
Scraper for rohlik.cz.
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


class RohlikCzScraper(BaseScraper):
    """
    Scraper for rohlik.cz leaflet.
    
    Scrapes current Rohlik CZ offers from rohlik.cz.
    """
    
    BASE_URL = "https://www.rohlik.cz"
    SEARCH_URL = "https://www.rohlik.cz/cs/akcni-nabidka"
    
    def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape Rohlik CZ offers from rohlik.cz.
        
        Returns:
            List of offer dictionaries
        """
        offers = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
            }
            
            # Try the action offers page first
            response = requests.get(self.SEARCH_URL, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Rohlik.cz structure: Look for product items
            product_items = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'product|item|card|ProductCard', re.I))
            
            if not product_items:
                # Try data attributes
                product_items = soup.find_all(['div', 'article'], {'data-product-id': True}) or \
                               soup.find_all('a', href=re.compile(r'/produkty/', re.I))
            
            logger.info(f"Found {len(product_items)} potential product items on rohlik.cz")
            
            for item in product_items[:100]:  # Limit to first 100 items
                try:
                    offer_data = self._parse_product_item(item, response.url)
                    if offer_data:
                        offers.append(offer_data)
                except Exception as e:
                    logger.debug(f"Error parsing product item: {e}")
                    continue
            
            # If still no offers, try parsing JSON-LD or other structured data
            if not offers:
                offers = self._parse_fallback(soup, response.url)
            
            logger.info(f"Successfully scraped {len(offers)} offers from rohlik.cz")
            
        except requests.RequestException as e:
            logger.error(f"Error fetching rohlik.cz: {e}")
        except Exception as e:
            logger.error(f"Error scraping rohlik.cz: {e}", exc_info=True)
        
        return offers
    
    def _parse_product_item(self, item, base_url: str) -> Dict[str, Any]:
        """Parse a single product item element."""
        offer = {}
        
        # Extract product name
        name_elem = item.find(['h2', 'h3', 'h4', 'a', 'span', 'div'], class_=re.compile(r'name|title|product-name|ProductCard-name', re.I))
        if not name_elem:
            name_elem = item.find(['h2', 'h3', 'h4', 'a'])
        
        if name_elem:
            display_name = name_elem.get_text(strip=True)
            if display_name:
                offer['display_name'] = display_name
                offer['ingredient_name'] = display_name
        
        # Extract price
        price_elem = item.find(['span', 'div', 'strong', 'b'], class_=re.compile(r'price|cost|cena|Price', re.I))
        if not price_elem:
            price_elem = item.find(string=re.compile(r'\d+[\s,.]*\d*\s*Kč', re.I))
        
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
                    offer['currency'] = 'CZK'
                except (ValueError, AttributeError):
                    pass
        
        # Extract unit
        unit_text = item.get_text()
        unit_match = re.search(r'(\d+)\s*(kg|g|ml|l|ks|piece|pieces|bal|balíček)', unit_text, re.I)
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
        
        price_pattern = re.compile(r'([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s]+?)\s+(\d+[\s,.]?\d*)\s*Kč', re.UNICODE)
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
                        'currency': 'CZK',
                        'source_url': base_url,
                    })
                except ValueError:
                    continue
        
        return offers

