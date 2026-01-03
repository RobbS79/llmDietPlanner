"""
Scraper for rohlik.cz.
"""
from typing import List, Dict, Any
import logging

from .base import BaseScraper

logger = logging.getLogger(__name__)


class RohlikCzScraper(BaseScraper):
    """
    Scraper for rohlik.cz leaflet.
    
    MVP: Placeholder implementation.
    TODO: Implement actual scraping logic using requests + BeautifulSoup4 or Selenium.
    """
    
    def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape Rohlik offers from rohlik.cz.
        
        Returns:
            List of offer dictionaries
        """
        logger.warning("RohlikCzScraper.scrape() called - placeholder implementation")
        # TODO: Implement actual scraping
        # For MVP, return empty list
        return []

