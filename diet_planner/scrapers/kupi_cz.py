"""
Scraper for kupi.cz (Lidl Czech Republic).
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


class KupiCzScraper(BaseScraper):
    """
    Scraper for kupi.cz leaflet (Lidl Czech Republic).
    
    Scrapes current Lidl CZ offers from kupi.cz.
    """
    
    BASE_URL = "https://kupi.cz/lidl"
    
    def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape Lidl CZ offers from kupi.cz.
        
        Returns:
            List of offer dictionaries with structure:
            {
                'ingredient_name': str,
                'display_name': str,
                'price': Decimal (optional),
                'currency': str,
                'unit': str (optional),
                'source_url': str (optional),
            }
        """
        offers = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(self.BASE_URL, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # kupi.cz structure: Look for product items
            # Common selectors for product listings on kupi.cz
            product_items = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'product|item|offer', re.I))
            
            # If no products found with class names, try more generic selectors
            if not product_items:
                product_items = soup.find_all(['div', 'article'], {'data-product': True}) or \
                               soup.find_all('a', href=re.compile(r'/produkt|/product', re.I))
            
            logger.info(f"Found {len(product_items)} potential product items on kupi.cz")
            
            for item in product_items[:100]:  # Limit to first 100 items
                try:
                    offer_data = self._parse_product_item(item, response.url)
                    if offer_data:
                        offers.append(offer_data)
                except Exception as e:
                    logger.debug(f"Error parsing product item: {e}")
                    continue
            
            # If still no offers, try parsing product cards or listings
            if not offers:
                offers = self._parse_fallback(soup, response.url)
            
            logger.info(f"Successfully scraped {len(offers)} offers from kupi.cz")
            
        except requests.RequestException as e:
            logger.error(f"Error fetching kupi.cz: {e}")
        except Exception as e:
            logger.error(f"Error scraping kupi.cz: {e}", exc_info=True)
        
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
                offer['ingredient_name'] = display_name  # Will be normalized later
        
        # Extract price
        price_elem = item.find(['span', 'div', 'strong'], class_=re.compile(r'price|cost|cena', re.I))
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
        
        # Extract unit (if available)
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
        """Fallback parsing method if primary parsing fails."""
        offers = []
        
        # Try to find any text that looks like products with prices
        text_content = soup.get_text()
        
        # Look for patterns like "Product Name - 99 Kč" or "Product Name 99,90 Kč"
        price_pattern = re.compile(r'([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s]+?)\s+(\d+[\s,.]?\d*)\s*Kč', re.UNICODE)
        matches = price_pattern.findall(text_content)
        
        for match in matches[:50]:  # Limit to 50 matches
            product_name = match[0].strip()
            price_text = match[1].replace(',', '.').replace(' ', '')
            
            if len(product_name) > 3 and len(product_name) < 100:  # Reasonable product name length
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

