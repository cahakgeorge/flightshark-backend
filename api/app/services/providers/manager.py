"""
Provider Manager - Orchestrates multiple flight search providers with failover
"""
from typing import List, Optional, Dict
from datetime import date
import asyncio
import logging
from collections import defaultdict

from app.schemas.flight import FlightOffer
from .base import FlightProvider, ProviderResult, ProviderStatus, ProviderError
from .amadeus import AmadeusProvider
from .skyscanner import SkyscannerProvider
from .kiwi import KiwiProvider

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Manages multiple flight search providers with:
    - Priority-based search
    - Automatic failover
    - Result aggregation and deduplication
    - Provider health tracking
    """
    
    def __init__(self):
        # Initialize all providers
        self._providers: List[FlightProvider] = [
            AmadeusProvider(),
            SkyscannerProvider(),
            KiwiProvider(),
        ]
        
        # Sort by priority (lower = higher priority)
        self._providers.sort(key=lambda p: p.priority)
        
        # Track provider stats
        self._search_stats: Dict[str, Dict] = defaultdict(lambda: {
            "total_searches": 0,
            "successful_searches": 0,
            "total_results": 0,
            "avg_response_time_ms": 0,
        })
    
    @property
    def providers(self) -> List[FlightProvider]:
        """Get all registered providers"""
        return self._providers
    
    @property
    def available_providers(self) -> List[FlightProvider]:
        """Get providers that are configured and available"""
        return [
            p for p in self._providers 
            if p.is_configured and p.is_available
        ]
    
    def get_provider(self, name: str) -> Optional[FlightProvider]:
        """Get a specific provider by name"""
        for provider in self._providers:
            if provider.name == name:
                return provider
        return None
    
    async def search(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        passengers: int = 1,
        cabin_class: str = "economy",
        strategy: str = "fallback",  # "fallback", "parallel", "best_price"
        max_providers: int = 3,
    ) -> List[FlightOffer]:
        """
        Search for flights across providers.
        
        Strategies:
        - fallback: Try providers in priority order until one succeeds
        - parallel: Search all providers simultaneously, aggregate results
        - best_price: Search all, return only the cheapest per route
        
        Args:
            origin: Origin airport code
            destination: Destination airport code
            departure_date: Departure date
            return_date: Return date (optional)
            passengers: Number of passengers
            cabin_class: Cabin class preference
            strategy: Search strategy
            max_providers: Maximum providers to use
        
        Returns:
            List of flight offers, sorted by price
        """
        available = self.available_providers[:max_providers]
        
        if not available:
            logger.warning("No flight providers available")
            return []
        
        if strategy == "fallback":
            return await self._search_with_fallback(
                available, origin, destination, departure_date, 
                return_date, passengers, cabin_class
            )
        elif strategy == "parallel":
            return await self._search_parallel(
                available, origin, destination, departure_date,
                return_date, passengers, cabin_class
            )
        elif strategy == "best_price":
            return await self._search_best_price(
                available, origin, destination, departure_date,
                return_date, passengers, cabin_class
            )
        else:
            return await self._search_with_fallback(
                available, origin, destination, departure_date,
                return_date, passengers, cabin_class
            )
    
    async def _search_with_fallback(
        self,
        providers: List[FlightProvider],
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date],
        passengers: int,
        cabin_class: str,
    ) -> List[FlightOffer]:
        """
        Search providers in priority order with automatic failover.
        
        Tries each provider until one succeeds, falls back to next on failure.
        """
        last_error: Optional[Exception] = None
        
        for provider in providers:
            try:
                logger.info(f"Searching with {provider.name} provider")
                
                import time
                start = time.time()
                
                offers = await provider.search(
                    origin, destination, departure_date,
                    return_date, passengers, cabin_class
                )
                
                response_time = (time.time() - start) * 1000
                self._update_stats(provider.name, True, len(offers), response_time)
                
                if offers:
                    logger.info(f"{provider.name} returned {len(offers)} offers in {response_time:.0f}ms")
                    return sorted(offers, key=lambda x: x.price)
                    
            except ProviderError as e:
                last_error = e
                logger.warning(f"{provider.name} failed: {e.message}")
                self._update_stats(provider.name, False, 0, 0)
                continue
            except Exception as e:
                last_error = e
                logger.error(f"{provider.name} unexpected error: {e}")
                self._update_stats(provider.name, False, 0, 0)
                continue
        
        logger.warning(f"All providers failed for {origin}->{destination}")
        return []
    
    async def _search_parallel(
        self,
        providers: List[FlightProvider],
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date],
        passengers: int,
        cabin_class: str,
    ) -> List[FlightOffer]:
        """
        Search all providers simultaneously and aggregate results.
        
        Useful when you want the widest selection of flights.
        """
        async def search_provider(provider: FlightProvider) -> ProviderResult:
            import time
            start = time.time()
            
            try:
                offers = await provider.search(
                    origin, destination, departure_date,
                    return_date, passengers, cabin_class
                )
                response_time = (time.time() - start) * 1000
                self._update_stats(provider.name, True, len(offers), response_time)
                
                return ProviderResult(
                    provider_name=provider.name,
                    offers=offers,
                    success=True,
                    response_time_ms=response_time,
                )
            except Exception as e:
                self._update_stats(provider.name, False, 0, 0)
                return ProviderResult(
                    provider_name=provider.name,
                    offers=[],
                    success=False,
                    error_message=str(e),
                )
        
        # Run all searches in parallel
        results = await asyncio.gather(
            *[search_provider(p) for p in providers],
            return_exceptions=True
        )
        
        # Aggregate offers from all successful providers
        all_offers = []
        for result in results:
            if isinstance(result, ProviderResult) and result.success:
                all_offers.extend(result.offers)
                logger.info(f"{result.provider_name}: {len(result.offers)} offers")
        
        # Deduplicate and sort
        unique_offers = self._deduplicate_offers(all_offers)
        return sorted(unique_offers, key=lambda x: x.price)
    
    async def _search_best_price(
        self,
        providers: List[FlightProvider],
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date],
        passengers: int,
        cabin_class: str,
    ) -> List[FlightOffer]:
        """
        Search all providers and return deduplicated results with best prices.
        
        For flights that appear in multiple providers, keep only the cheapest.
        """
        all_offers = await self._search_parallel(
            providers, origin, destination, departure_date,
            return_date, passengers, cabin_class
        )
        
        # Group by flight signature (airline + times) and keep cheapest
        best_offers: Dict[str, FlightOffer] = {}
        
        for offer in all_offers:
            signature = self._get_flight_signature(offer)
            
            if signature not in best_offers or offer.price < best_offers[signature].price:
                best_offers[signature] = offer
        
        return sorted(best_offers.values(), key=lambda x: x.price)
    
    def _deduplicate_offers(self, offers: List[FlightOffer]) -> List[FlightOffer]:
        """Remove duplicate offers based on flight signature"""
        seen = set()
        unique = []
        
        for offer in offers:
            signature = self._get_flight_signature(offer)
            if signature not in seen:
                seen.add(signature)
                unique.append(offer)
        
        return unique
    
    def _get_flight_signature(self, offer: FlightOffer) -> str:
        """
        Generate a unique signature for a flight based on:
        - Airline
        - Flight numbers
        - Departure/arrival times
        """
        parts = [offer.airline]
        
        for seg in offer.outbound_segments:
            parts.append(f"{seg.flight_number}-{seg.departure_time.isoformat()}")
        
        if offer.return_segments:
            for seg in offer.return_segments:
                parts.append(f"{seg.flight_number}-{seg.departure_time.isoformat()}")
        
        return "|".join(parts)
    
    def _update_stats(
        self, 
        provider_name: str, 
        success: bool, 
        result_count: int, 
        response_time_ms: float
    ):
        """Update provider statistics"""
        stats = self._search_stats[provider_name]
        stats["total_searches"] += 1
        
        if success:
            stats["successful_searches"] += 1
            stats["total_results"] += result_count
            
            # Rolling average response time
            n = stats["successful_searches"]
            old_avg = stats["avg_response_time_ms"]
            stats["avg_response_time_ms"] = old_avg + (response_time_ms - old_avg) / n
    
    def get_provider_stats(self) -> Dict[str, Dict]:
        """Get statistics for all providers"""
        result = {}
        
        for provider in self._providers:
            stats = self._search_stats[provider.name].copy()
            stats["status"] = provider.status.value
            stats["is_configured"] = provider.is_configured
            stats["is_available"] = provider.is_available
            stats["priority"] = provider.priority
            
            if stats["total_searches"] > 0:
                stats["success_rate"] = (
                    stats["successful_searches"] / stats["total_searches"] * 100
                )
            else:
                stats["success_rate"] = 0.0
            
            result[provider.name] = stats
        
        return result
    
    async def get_price_calendar(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
    ) -> List[dict]:
        """
        Get cheapest prices for each day of a month.
        
        Tries providers in order until one returns data.
        """
        for provider in self.available_providers:
            try:
                prices = await provider.get_price_calendar(origin, destination, year, month)
                if prices:
                    return prices
            except Exception as e:
                logger.warning(f"{provider.name} price calendar failed: {e}")
                continue
        
        return []
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of all providers"""
        results = {}
        
        for provider in self._providers:
            try:
                results[provider.name] = await provider.health_check()
            except Exception:
                results[provider.name] = False
        
        return results
    
    def reset_provider(self, provider_name: str):
        """Reset a provider's status (e.g., after fixing an issue)"""
        provider = self.get_provider(provider_name)
        if provider:
            provider.reset_status()
            logger.info(f"Reset {provider_name} provider status")


# Singleton instance for the application
provider_manager = ProviderManager()
