"""
Flight Search Service - Aggregates results from multiple providers
"""
from typing import List, Optional
from datetime import date
import logging

from app.schemas.flight import FlightOffer
from app.services.providers import ProviderManager, provider_manager

logger = logging.getLogger(__name__)


class FlightService:
    """
    Service for searching flights across multiple providers with automatic failover.
    
    Supports multiple search strategies:
    - fallback: Try providers in priority order (fastest, best for single results)
    - parallel: Search all providers at once (widest selection)
    - best_price: Search all, deduplicate by cheapest (best value)
    """
    
    def __init__(self, manager: Optional[ProviderManager] = None):
        self.manager = manager or provider_manager
    
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        passengers: int = 1,
        cabin_class: str = "economy",
        direct_only: bool = False,
        strategy: str = "fallback",
    ) -> List[FlightOffer]:
        """
        Search for flights across all configured providers.
        
        Args:
            origin: Origin airport IATA code (e.g., "DUB")
            destination: Destination airport IATA code (e.g., "BCN")
            departure_date: Departure date
            return_date: Return date (optional for one-way)
            passengers: Number of passengers
            cabin_class: Cabin class (economy, premium_economy, business, first)
            direct_only: Filter to direct flights only
            strategy: Search strategy ("fallback", "parallel", "best_price")
        
        Returns:
            List of flight offers sorted by price
        """
        logger.info(
            f"Searching flights: {origin} -> {destination}, "
            f"date: {departure_date}, passengers: {passengers}, "
            f"strategy: {strategy}"
        )
        
        # Search using provider manager
        offers = await self.manager.search(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            passengers=passengers,
            cabin_class=cabin_class,
            strategy=strategy,
        )
        
        # Filter direct flights if requested
        if direct_only:
            offers = [o for o in offers if o.is_direct]
        
        logger.info(f"Found {len(offers)} flight offers")
        return offers
    
    async def search_multi_city(
        self,
        routes: List[dict],
        passengers: int = 1,
    ) -> List[FlightOffer]:
        """
        Search for multi-city itineraries.
        
        Uses Kiwi provider which specializes in complex itineraries.
        
        Args:
            routes: List of route dicts with "from", "to", "date" keys
            passengers: Number of passengers
        
        Returns:
            List of flight offers for the complete multi-city trip
        """
        kiwi = self.manager.get_provider("kiwi")
        
        if kiwi and kiwi.is_configured and kiwi.is_available:
            try:
                return await kiwi.search_multi_city(routes, passengers)
            except Exception as e:
                logger.error(f"Multi-city search failed: {e}")
        
        return []
    
    async def search_flexible_dates(
        self,
        origin: str,
        destination: str,
        date_from: date,
        date_to: date,
        nights_from: int = 3,
        nights_to: int = 7,
        passengers: int = 1,
    ) -> List[FlightOffer]:
        """
        Search flights with flexible dates.
        
        Uses Kiwi provider which excels at flexible date searches.
        
        Args:
            origin: Origin airport code
            destination: Destination airport code
            date_from: Start of date range
            date_to: End of date range
            nights_from: Minimum nights at destination
            nights_to: Maximum nights at destination
            passengers: Number of passengers
        
        Returns:
            Best flight offers within the flexible date range
        """
        kiwi = self.manager.get_provider("kiwi")
        
        if kiwi and kiwi.is_configured and kiwi.is_available:
            try:
                return await kiwi.search_flexible_dates(
                    origin, destination, date_from, date_to,
                    nights_from, nights_to, passengers
                )
            except Exception as e:
                logger.error(f"Flexible date search failed: {e}")
        
        return []
    
    async def get_cheapest_dates(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
    ) -> List[dict]:
        """
        Get cheapest prices for each day of a month.
        
        Useful for displaying price calendars.
        
        Args:
            origin: Origin airport code
            destination: Destination airport code
            year: Year
            month: Month (1-12)
        
        Returns:
            List of dicts with "date", "price", "currency" keys
        """
        return await self.manager.get_price_calendar(origin, destination, year, month)
    
    async def get_provider_status(self) -> dict:
        """
        Get status and statistics for all flight providers.
        
        Useful for monitoring and debugging.
        """
        stats = self.manager.get_provider_stats()
        health = await self.manager.health_check()
        
        return {
            "providers": stats,
            "health": health,
            "available_providers": [p.name for p in self.manager.available_providers],
        }


# Singleton instance
flight_service = FlightService()
