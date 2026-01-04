"""
Scraper service for managing leaflet data scraping and caching.
"""
from typing import List, Dict, Any, Optional
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q
import logging

from ..models import LeafletOffer, SHOP_TO_SOURCE_URL, COUNTRY_TO_SHOPS, get_currency_for_country
from .kupi_cz import KupiCzScraper
from .rohlik_cz import RohlikCzScraper
from .kupino_sk import KupinoSkScraper
from .lunys_sk import LunysSkScraper
from .utils import normalize_ingredient_name

logger = logging.getLogger(__name__)

# Cache expiry time: 24 hours
CACHE_EXPIRY_HOURS = 24


class ScraperService:
    """
    Service for managing leaflet scraping and caching.
    
    Routes shop selection to correct scraper, checks cache validity,
    triggers scraping if needed, and stores results.
    """
    
    # Map shop codes to scraper classes
    SCRAPER_MAP = {
        'LIDL_CZ': KupiCzScraper,
        'ROHLIK': RohlikCzScraper,
        'LIDL_SK': KupinoSkScraper,
        'LUNYS': LunysSkScraper,
    }
    
    @classmethod
    def get_scraper(cls, shop: str):
        """
        Get scraper instance for a shop.
        
        Args:
            shop: Shop code (e.g., 'LIDL_CZ')
            
        Returns:
            Scraper instance
            
        Raises:
            ValueError: If shop is not supported
        """
        scraper_class = cls.SCRAPER_MAP.get(shop)
        if not scraper_class:
            raise ValueError(f"Unsupported shop: {shop}")
        return scraper_class()
    
    @classmethod
    def is_cache_valid(cls, shop: str, country: str) -> bool:
        """
        Check if cached data exists and is still valid.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            True if valid cache exists, False otherwise
        """
        now = timezone.now()
        cached_count = LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            expires_at__gt=now
        ).count()
        
        return cached_count > 0
    
    @classmethod
    def get_cached_offers(cls, shop: str, country: str) -> List[LeafletOffer]:
        """
        Get cached offers that are still valid.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            List of LeafletOffer instances
        """
        now = timezone.now()
        return list(LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            expires_at__gt=now
        ).order_by('ingredient_name'))
    
    @classmethod
    def scrape_and_store(cls, shop: str, country: str) -> List[LeafletOffer]:
        """
        Scrape leaflet data and store in database.
        
        Args:
            shop: Shop code
            country: Country code
            
        Returns:
            List of created LeafletOffer instances
        """
        logger.info(f"Scraping leaflet data for {shop} ({country})")
        
        # Get scraper instance
        scraper = cls.get_scraper(shop)
        
        # Scrape data
        try:
            offers_data = scraper.scrape()
        except Exception as e:
            logger.error(f"Error scraping {shop} ({country}): {e}", exc_info=True)
            raise
        
        # Delete old expired offers for this shop/country
        now = timezone.now()
        LeafletOffer.objects.filter(
            shop=shop,
            country=country
        ).filter(
            Q(expires_at__lte=now) | Q(expires_at__isnull=True)
        ).delete()
        
        # Calculate expiry time
        expires_at = now + timedelta(hours=CACHE_EXPIRY_HOURS)
        currency = get_currency_for_country(country)
        
        # Store offers
        created_offers = []
        for offer_data in offers_data:
            # Normalize ingredient name
            ingredient_name = normalize_ingredient_name(
                offer_data.get('ingredient_name') or offer_data.get('display_name', '')
            )
            
            if not ingredient_name:
                logger.warning(f"Skipping offer with empty ingredient name: {offer_data}")
                continue
            
            offer = LeafletOffer.objects.create(
                shop=shop,
                country=country,
                ingredient_name=ingredient_name,
                display_name=offer_data.get('display_name', ingredient_name),
                price=offer_data.get('price'),
                currency=offer_data.get('currency', currency),
                unit=offer_data.get('unit'),
                expires_at=expires_at,
                source_url=offer_data.get('source_url'),
            )
            created_offers.append(offer)
        
        logger.info(f"Stored {len(created_offers)} offers for {shop} ({country})")
        return created_offers
    
    @classmethod
    def get_available_ingredients(cls, shop: str, country: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Get available ingredients for a shop/country.
        
        Checks cache first, scrapes if needed.
        
        Args:
            shop: Shop code
            country: Country code
            force_refresh: If True, force re-scraping even if cache is valid
            
        Returns:
            List of ingredient dictionaries with 'name' and 'display_name'
        """
        # Check cache
        if not force_refresh and cls.is_cache_valid(shop, country):
            logger.info(f"Using cached offers for {shop} ({country})")
            offers = cls.get_cached_offers(shop, country)
        else:
            # Scrape and store
            offers = cls.scrape_and_store(shop, country)
        
        # Convert to list of dictionaries for LLM prompt
        ingredients = []
        for offer in offers:
            ingredients.append({
                'name': offer.ingredient_name,
                'display_name': offer.display_name,
            })
        
        return ingredients
    
    @classmethod
    def match_ingredient_price(cls, ingredient_name: str, shop: str, country: str) -> Optional[Dict[str, Any]]:
        """
        Match an ingredient name with a price from LeafletOffer.
        
        Args:
            ingredient_name: Normalized ingredient name to match
            shop: Shop code
            country: Country code
            
        Returns:
            Dict with price info or None if not found:
            {
                'price': Decimal,
                'currency': str,
                'unit': str,
                'display_name': str,
            }
        """
        from django.utils import timezone
        
        normalized_name = normalize_ingredient_name(ingredient_name)
        
        # Try to find matching offer
        current_time = timezone.now()
        offer = LeafletOffer.objects.filter(
            shop=shop,
            country=country,
            ingredient_name=normalized_name,
            expires_at__gt=current_time,
            price__isnull=False
        ).order_by('-scraped_at').first()
        
        if offer:
            return {
                'price': Decimal(str(offer.price)),
                'currency': offer.currency,
                'unit': offer.unit or '',
                'display_name': offer.display_name,
            }
        
        return None
    
    @classmethod
    def match_shopping_list_prices(cls, shopping_list: List[Dict[str, Any]], shop: str, country: str) -> List[Dict[str, Any]]:
        """
        Match shopping list items with prices from LeafletOffer.
        
        Args:
            shopping_list: List of shopping list items (from LLM)
            shop: Shop code
            country: Country code
            
        Returns:
            List of shopping list items with price information added
        """
        enhanced_list = []
        for item in shopping_list:
            ingredient_name = item.get('ingredient', '')
            if ingredient_name:
                price_info = cls.match_ingredient_price(ingredient_name, shop, country)
                if price_info:
                    item['price'] = price_info['price']
                    item['currency'] = price_info['currency']
                    item['offer_unit'] = price_info['unit']
                    item['offer_display_name'] = price_info['display_name']
                else:
                    # No price found, mark as unavailable
                    item['price'] = None
                    item['currency'] = get_currency_for_country(country)
                    item['offer_unit'] = None
                    item['offer_display_name'] = None
            enhanced_list.append(item)
        
        return enhanced_list

