"""
Base Flight Provider - Abstract interface for all flight search providers
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import date
from dataclasses import dataclass
from enum import Enum
import logging

from app.schemas.flight import FlightOffer

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Provider health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass
class ProviderResult:
    """Result from a provider search"""
    provider_name: str
    offers: List[FlightOffer]
    success: bool
    error_message: Optional[str] = None
    response_time_ms: Optional[float] = None
    cached: bool = False


class FlightProvider(ABC):
    """
    Abstract base class for flight search providers.
    
    All flight data providers (Amadeus, Skyscanner, Kiwi, etc.) must implement this interface.
    """
    
    # Provider identification
    name: str = "base"
    priority: int = 0  # Lower number = higher priority
    
    # Rate limiting
    requests_per_minute: int = 60
    requests_per_day: int = 1000
    
    # Current state
    _status: ProviderStatus = ProviderStatus.HEALTHY
    _consecutive_failures: int = 0
    _max_failures_before_degraded: int = 3
    _max_failures_before_unavailable: int = 10
    
    def __init__(self):
        self._request_count = 0
        self._last_request_time = None
    
    @property
    def status(self) -> ProviderStatus:
        """Get current provider status"""
        return self._status
    
    @property
    def is_available(self) -> bool:
        """Check if provider is available for requests"""
        return self._status != ProviderStatus.UNAVAILABLE
    
    @property
    def is_configured(self) -> bool:
        """Check if provider has required configuration (API keys, etc.)"""
        return True  # Override in subclasses
    
    def record_success(self):
        """Record a successful request"""
        self._consecutive_failures = 0
        self._status = ProviderStatus.HEALTHY
    
    def record_failure(self, error: Exception):
        """Record a failed request"""
        self._consecutive_failures += 1
        logger.warning(f"{self.name} provider failure #{self._consecutive_failures}: {error}")
        
        if self._consecutive_failures >= self._max_failures_before_unavailable:
            self._status = ProviderStatus.UNAVAILABLE
            logger.error(f"{self.name} provider marked as UNAVAILABLE after {self._consecutive_failures} failures")
        elif self._consecutive_failures >= self._max_failures_before_degraded:
            self._status = ProviderStatus.DEGRADED
            logger.warning(f"{self.name} provider marked as DEGRADED after {self._consecutive_failures} failures")
    
    def reset_status(self):
        """Reset provider status (e.g., after manual recovery)"""
        self._consecutive_failures = 0
        self._status = ProviderStatus.HEALTHY
    
    @abstractmethod
    async def search(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        passengers: int = 1,
        cabin_class: str = "economy",
    ) -> List[FlightOffer]:
        """
        Search for flights.
        
        Args:
            origin: Origin airport IATA code (e.g., "DUB")
            destination: Destination airport IATA code (e.g., "BCN")
            departure_date: Departure date
            return_date: Return date (optional for one-way)
            passengers: Number of passengers
            cabin_class: Cabin class (economy, premium_economy, business, first)
        
        Returns:
            List of flight offers
        
        Raises:
            ProviderError: If the search fails
        """
        pass
    
    async def get_price_calendar(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
    ) -> List[dict]:
        """
        Get cheapest prices for each day of a month.
        
        Default implementation returns empty list.
        Override in providers that support this feature.
        """
        return []
    
    async def health_check(self) -> bool:
        """
        Check if the provider is healthy and responsive.
        
        Default implementation returns True.
        Override for actual health checks.
        """
        return self.is_configured


class ProviderError(Exception):
    """Exception raised when a provider fails"""
    def __init__(self, provider_name: str, message: str, original_error: Optional[Exception] = None):
        self.provider_name = provider_name
        self.message = message
        self.original_error = original_error
        super().__init__(f"{provider_name}: {message}")
