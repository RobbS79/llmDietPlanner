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
    Strategy: Navigate to leaflet listing page, extract individual leaflet URLs,
    then scrape each leaflet page for products with prices.
    """
    
    BASE_URL = "https://www.kupi.cz/letaky/lidl"
    
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
        all_offers = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Step 1: Get list of leaflet URLs
            logger.info(f"Fetching leaflet listing page: {self.BASE_URL}")
            response = requests.get(self.BASE_URL, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract leaflet URLs - look for links to /letak/lidl-*
            leaflet_links = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                if href.startswith('/letak/lidl-') or href.startswith('https://www.kupi.cz/letak/lidl-'):
                    full_url = urljoin(response.url, href)
                    if full_url not in leaflet_links:
                        leaflet_links.append(full_url)
            
            logger.info(f"Found {len(leaflet_links)} leaflet pages to scrape")
            
            if not leaflet_links:
                logger.warning(f"No leaflet links found on {self.BASE_URL}")
                # Try fallback: scrape "Akční zboží" section from listing page
                offers = self._parse_akcni_zbozi_section(soup, response.url)
                all_offers.extend(offers)
            else:
                # Step 2: Scrape only the first (current) leaflet page
                leaflet_url = leaflet_links[0]
                try:
                    logger.info(f"Scraping current Lidl leaflet: {leaflet_url}")
                    leaflet_offers = self._scrape_leaflet_page(leaflet_url, headers)
                    all_offers.extend(leaflet_offers)
                    logger.info(f"Found {len(leaflet_offers)} products in leaflet")
                except Exception as e:
                    logger.error(f"Error scraping leaflet {leaflet_url}: {e}", exc_info=True)
            
            logger.info(f"Successfully scraped {len(all_offers)} total offers from kupi.cz")
            
        except requests.RequestException as e:
            logger.error(f"Error fetching kupi.cz: {e}")
        except Exception as e:
            logger.error(f"Error scraping kupi.cz: {e}", exc_info=True)
        
        return all_offers
    
    def _scrape_leaflet_page(self, leaflet_url: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Scrape a single leaflet page for products.
        
        Args:
            leaflet_url: URL of the leaflet page
            headers: HTTP headers to use
            
        Returns:
            List of offer dictionaries
        """
        offers = []
        
        try:
            response = requests.get(leaflet_url, headers=headers, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for product items - try various selectors
            product_items = []
            
            # Strategy 1: Look for common product container classes
            product_items = soup.find_all(['div', 'article', 'li'], class_=re.compile(r'product|item|offer|card', re.I))
            
            # Strategy 2: Look for elements with product-like attributes
            if not product_items:
                product_items = soup.find_all(['div', 'article'], {'data-product': True}) or \
                               soup.find_all(['div', 'article'], {'data-id': True})
            
            # Strategy 3: Look for links containing product names and prices
            if not product_items:
                # Try to find any container with price patterns
                all_elements = soup.find_all(['div', 'article', 'li', 'a'])
                for elem in all_elements:
                    text = elem.get_text()
                    if re.search(r'\d+[\s,.]?\d*\s*Kč', text):
                        product_items.append(elem)
            
            logger.debug(f"Found {len(product_items)} potential product items on leaflet page")
            
            for item in product_items[:200]:  # Limit to first 200 items per leaflet
                try:
                    offer_data = self._parse_product_item(item, leaflet_url)
                    if offer_data and offer_data.get('display_name'):
                        offers.append(offer_data)
                except Exception as e:
                    logger.debug(f"Error parsing product item: {e}")
                    continue
            
            # If no products found, try text-based parsing
            if not offers:
                logger.debug("No products found with DOM parsing, trying text-based fallback")
                offers = self._parse_fallback_text(soup, leaflet_url)
            
        except requests.RequestException as e:
            logger.error(f"Error fetching leaflet page {leaflet_url}: {e}")
        except Exception as e:
            logger.error(f"Error parsing leaflet page {leaflet_url}: {e}", exc_info=True)
        
        return offers
    
    def _parse_product_item(self, item, base_url: str) -> Dict[str, Any]:
        """Parse a single product item element."""
        offer = {}
        
        # Extract product name - try multiple strategies
        name_elem = item.find(['h2', 'h3', 'h4', 'a', 'span', 'div'], class_=re.compile(r'name|title|product-name|heading', re.I))
        if not name_elem:
            # Try to find any heading or strong element
            name_elem = item.find(['h2', 'h3', 'h4', 'strong', 'b'])
        
        if name_elem:
            display_name = name_elem.get_text(strip=True)
            if display_name and len(display_name) > 2:
                offer['display_name'] = display_name
                offer['ingredient_name'] = display_name  # Will be normalized later
        
        # Extract price - try multiple strategies
        price_elem = None
        price_text = None
        
        # Strategy 1: Look for price in common classes
        price_elem = item.find(['span', 'div', 'strong', 'b', 'p'], class_=re.compile(r'price|cost|cena|Price', re.I))
        
        # Strategy 2: Look for text containing price pattern
        if not price_elem:
            price_elem = item.find(string=re.compile(r'\d+[\s,.]*\d*\s*Kč', re.I))
        
        # Strategy 3: Look for any element containing price pattern
        if not price_elem:
            item_text = item.get_text()
            price_match = re.search(r'(\d+[\s,.]?\d*)\s*Kč', item_text, re.I)
            if price_match:
                price_text = price_match.group(0)
        
        if price_elem:
            if hasattr(price_elem, 'get_text'):
                price_text = price_elem.get_text(strip=True)
            else:
                price_text = str(price_elem).strip()
        
        if price_text:
            # Improved regex for Czech price formats: "99 Kč", "99,90 Kč", "99.90 Kč", "99 Kč/kg"
            price_match = re.search(r'(\d+[\s,.]?\d*)\s*Kč', price_text, re.I)
            if not price_match:
                # Try without Kč symbol
                price_match = re.search(r'(\d+[\s,.]?\d*)', price_text.replace(',', '.').replace(' ', ''))
            
            if price_match:
                try:
                    price_str = price_match.group(1).replace(',', '.').replace(' ', '')
                    price_value = float(price_str)
                    if price_value > 0:  # Validate positive price
                        offer['price'] = Decimal(str(price_value))
                        offer['currency'] = 'CZK'
                        logger.debug(f"Extracted price: {price_value} CZK from text: '{price_text}'")
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Failed to parse price from text '{price_text}': {e}")
        
        # Extract unit (if available)
        unit_text = item.get_text()
        unit_match = re.search(r'(\d+)\s*(kg|g|ml|l|ks|piece|pieces|bal|balíček)', unit_text, re.I)
        if unit_match:
            offer['unit'] = unit_match.group(2).lower()
        
        # Extract URL
        link_elem = item.find('a', href=True)
        if link_elem:
            href = link_elem['href']
            offer['source_url'] = urljoin(base_url, href)
        else:
            offer['source_url'] = base_url
        
        return offer if offer.get('display_name') else None
    
    def _parse_akcni_zbozi_section(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """
        Fallback: Parse the "Akční zboží v Lidl" section from the listing page.
        This section contains direct product links with prices.
        """
        offers = []
        
        # Look for section with heading "Akční zboží" or similar
        akcni_section = soup.find(string=re.compile(r'Akční zboží', re.I))
        if akcni_section:
            parent = akcni_section.find_parent(['section', 'div', 'article'])
            if parent:
                # Find all links in this section
                product_links = parent.find_all('a', href=re.compile(r'/sleva/', re.I))
                
                for link in product_links:
                    try:
                        # Get product name from link text or nearby elements
                        name_elem = link.find(['strong', 'span', 'div'], class_=re.compile(r'name|title', re.I))
                        if not name_elem:
                            name_elem = link.find('strong')
                        
                        display_name = name_elem.get_text(strip=True) if name_elem else link.get_text(strip=True)
                        
                        # Get price from nearby elements
                        price_elem = link.find_next(['span', 'div', 'generic'], class_=re.compile(r'price|cost|cena', re.I))
                        if not price_elem:
                            # Look in parent or siblings
                            parent_elem = link.find_parent(['div', 'article'])
                            if parent_elem:
                                price_text = parent_elem.get_text()
                                price_match = re.search(r'(\d+[\s,.]?\d*)\s*Kč', price_text, re.I)
                                if price_match:
                                    price_str = price_match.group(1).replace(',', '.').replace(' ', '')
                                    try:
                                        price_value = float(price_str)
                                        if price_value > 0 and display_name:
                                            offers.append({
                                                'display_name': display_name,
                                                'ingredient_name': display_name,
                                                'price': Decimal(str(price_value)),
                                                'currency': 'CZK',
                                                'source_url': urljoin(base_url, link.get('href', '')),
                                            })
                                    except (ValueError, AttributeError):
                                        pass
                    except Exception as e:
                        logger.debug(f"Error parsing Akční zboží item: {e}")
                        continue
        
        return offers
    
    def _parse_fallback_text(self, soup: BeautifulSoup, base_url: str) -> List[Dict[str, Any]]:
        """Fallback parsing method if primary parsing fails."""
        offers = []
        
        # Try to find any text that looks like products with prices
        text_content = soup.get_text()
        
        # Look for patterns like "Product Name - 99 Kč" or "Product Name 99,90 Kč"
        # Improved regex to handle Czech characters and various price formats
        price_pattern = re.compile(r'([A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽa-záčďéěíňóřšťúůýž\s\-]+?)\s+(\d+[\s,.]?\d*)\s*Kč', re.UNICODE | re.I)
        matches = price_pattern.findall(text_content)
        
        logger.debug(f"Fallback parsing found {len(matches)} potential price matches")
        
        for match in matches[:100]:  # Limit to 100 matches
            product_name = match[0].strip()
            price_text = match[1].replace(',', '.').replace(' ', '')
            
            # Clean product name - remove common prefixes/suffixes
            product_name = re.sub(r'^[\-\s]+|[\-\s]+$', '', product_name)
            
            if len(product_name) > 3 and len(product_name) < 100:  # Reasonable product name length
                try:
                    price_value = float(price_text)
                    if price_value > 0:  # Validate positive price
                        offers.append({
                            'display_name': product_name,
                            'ingredient_name': product_name,
                            'price': Decimal(str(price_value)),
                            'currency': 'CZK',
                            'source_url': base_url,
                        })
                        logger.debug(f"Fallback parsed: {product_name} - {price_value} CZK")
                except ValueError as e:
                    logger.debug(f"Failed to parse price '{price_text}' for '{product_name}': {e}")
                    continue
        
        return offers
