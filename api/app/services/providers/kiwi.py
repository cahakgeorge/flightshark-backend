"""
Kiwi.com Flight Provider - Multi-city and virtual interlining specialist
https://docs.kiwi.com/
"""
from typing import List, Optional
from datetime import date, datetime
import httpx
import logging

from app.config import settings
from app.schemas.flight import FlightOffer, FlightSegment
from .base import FlightProvider, ProviderError

logger = logging.getLogger(__name__)


class KiwiProvider(FlightProvider):
    """
    Kiwi.com (formerly Skypicker) flight search provider.
    
    Specializes in:
    - Multi-city itineraries
    - Virtual interlining (connecting flights on different airlines)
    - Flexible date searches
    - Nomad mode (multi-destination trips)
    
    Free tier: 1000 requests/day
    https://tequila.kiwi.com/portal/developers
    """
    
    name = "kiwi"
    priority = 3  # Tertiary provider / backup
    requests_per_minute = 100
    requests_per_day = 1000
    
    BASE_URL = "https://api.tequila.kiwi.com/v2"
    
    def __init__(self):
        super().__init__()
        self._currency = "EUR"
        self._locale = "en"
    
    @property
    def is_configured(self) -> bool:
        """Check if Kiwi API key is configured"""
        return bool(getattr(settings, 'KIWI_API_KEY', None))
    
    async def search(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        passengers: int = 1,
        cabin_class: str = "economy",
    ) -> List[FlightOffer]:
        """Search flights using Kiwi Tequila API"""
        if not self.is_configured:
            raise ProviderError(self.name, "Kiwi API key not configured")
        
        try:
            cabin_map = {
                "economy": "M",
                "premium_economy": "W",
                "business": "C",
                "first": "F",
            }
            
            headers = {
                "apikey": settings.KIWI_API_KEY,
                "Accept": "application/json",
            }
            
            params = {
                "fly_from": origin.upper(),
                "fly_to": destination.upper(),
                "date_from": departure_date.strftime("%d/%m/%Y"),
                "date_to": departure_date.strftime("%d/%m/%Y"),
                "adults": passengers,
                "curr": self._currency,
                "locale": self._locale,
                "selected_cabins": cabin_map.get(cabin_class, "M"),
                "limit": 50,
                "sort": "price",
            }
            
            if return_date:
                params["return_from"] = return_date.strftime("%d/%m/%Y")
                params["return_to"] = return_date.strftime("%d/%m/%Y")
                params["flight_type"] = "round"
            else:
                params["flight_type"] = "oneway"
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/search",
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
            
            offers = self._parse_response(data, return_date is not None)
            self.record_success()
            logger.info(f"Kiwi returned {len(offers)} offers for {origin}->{destination}")
            return offers
            
        except httpx.HTTPStatusError as e:
            self.record_failure(e)
            raise ProviderError(self.name, f"HTTP {e.response.status_code}", e)
        except Exception as e:
            self.record_failure(e)
            raise ProviderError(self.name, str(e), e)
    
    def _parse_response(self, data: dict, is_round_trip: bool) -> List[FlightOffer]:
        """Parse Kiwi API response"""
        offers = []
        
        for flight in data.get("data", []):
            try:
                price = float(flight.get("price", 0))
                
                # Parse all segments
                route = flight.get("route", [])
                
                if is_round_trip:
                    # Split segments into outbound and return
                    outbound_segments = []
                    return_segments = []
                    
                    for seg in route:
                        parsed_seg = self._parse_segment(seg)
                        if seg.get("return") == 0:
                            outbound_segments.append(parsed_seg)
                        else:
                            return_segments.append(parsed_seg)
                else:
                    outbound_segments = [self._parse_segment(seg) for seg in route]
                    return_segments = None
                
                # Get primary airline
                airlines = flight.get("airlines", [])
                airline = airlines[0] if airlines else "XX"
                
                # Duration
                duration_seconds = flight.get("duration", {})
                if isinstance(duration_seconds, dict):
                    total_duration = (duration_seconds.get("departure", 0) + duration_seconds.get("return", 0)) // 60
                else:
                    total_duration = duration_seconds // 60
                
                offers.append(FlightOffer(
                    id=f"kiwi-{flight.get('id', '')}",
                    price=price,
                    currency=self._currency,
                    cabin_class="economy",  # Kiwi doesn't always return cabin class
                    airline=airline,
                    outbound_segments=outbound_segments,
                    return_segments=return_segments,
                    total_duration_minutes=total_duration,
                    stops=len(outbound_segments) - 1 if outbound_segments else 0,
                    is_direct=len(outbound_segments) == 1 if outbound_segments else False,
                    source="kiwi",
                    # Kiwi-specific extras
                    booking_url=flight.get("deep_link"),
                    virtual_interlining=flight.get("virtual_interlining", False),
                ))
                
            except Exception as e:
                logger.warning(f"Failed to parse Kiwi flight: {e}")
                continue
        
        return offers
    
    def _parse_segment(self, seg: dict) -> FlightSegment:
        """Parse a single flight segment"""
        try:
            departure_time = datetime.fromtimestamp(seg.get("dTimeUTC", 0))
            arrival_time = datetime.fromtimestamp(seg.get("aTimeUTC", 0))
        except:
            departure_time = datetime.now()
            arrival_time = datetime.now()
        
        return FlightSegment(
            departure_airport=seg.get("flyFrom", "XXX"),
            arrival_airport=seg.get("flyTo", "XXX"),
            departure_time=departure_time,
            arrival_time=arrival_time,
            flight_number=f"{seg.get('airline', 'XX')}{seg.get('flight_no', '000')}",
            airline=seg.get("airline", "XX"),
            duration_minutes=(seg.get("aTimeUTC", 0) - seg.get("dTimeUTC", 0)) // 60,
            aircraft=seg.get("equipment"),
        )
    
    async def search_multi_city(
        self,
        routes: List[dict],  # [{"from": "DUB", "to": "BCN", "date": "2024-02-15"}, ...]
        passengers: int = 1,
    ) -> List[FlightOffer]:
        """
        Search multi-city itineraries (Kiwi specialty).
        
        Kiwi excels at finding complex itineraries with virtual interlining.
        """
        if not self.is_configured:
            raise ProviderError(self.name, "Kiwi API key not configured")
        
        try:
            headers = {
                "apikey": settings.KIWI_API_KEY,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
            
            # Build multi-city request
            requests = []
            for route in routes:
                requests.append({
                    "fly_from": route["from"],
                    "fly_to": route["to"],
                    "date_from": route["date"],
                    "date_to": route["date"],
                })
            
            body = {
                "requests": requests,
                "adults": passengers,
                "curr": self._currency,
                "limit": 30,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.BASE_URL}/flights_multi",
                    headers=headers,
                    json=body,
                    timeout=45.0,
                )
                response.raise_for_status()
                data = response.json()
            
            return self._parse_response(data, False)
            
        except Exception as e:
            self.record_failure(e)
            raise ProviderError(self.name, str(e), e)
    
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
        Search flights with flexible dates (Kiwi specialty).
        
        Returns best price combinations within a date range.
        """
        if not self.is_configured:
            raise ProviderError(self.name, "Kiwi API key not configured")
        
        try:
            headers = {
                "apikey": settings.KIWI_API_KEY,
                "Accept": "application/json",
            }
            
            params = {
                "fly_from": origin.upper(),
                "fly_to": destination.upper(),
                "date_from": date_from.strftime("%d/%m/%Y"),
                "date_to": date_to.strftime("%d/%m/%Y"),
                "nights_in_dst_from": nights_from,
                "nights_in_dst_to": nights_to,
                "adults": passengers,
                "curr": self._currency,
                "limit": 50,
                "sort": "price",
                "flight_type": "round",
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/search",
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
            
            return self._parse_response(data, True)
            
        except Exception as e:
            self.record_failure(e)
            raise ProviderError(self.name, str(e), e)
    
    async def get_price_calendar(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
    ) -> List[dict]:
        """Get cheapest prices using Kiwi aggregation"""
        if not self.is_configured:
            return []
        
        try:
            from calendar import monthrange
            _, num_days = monthrange(year, month)
            
            headers = {
                "apikey": settings.KIWI_API_KEY,
            }
            
            params = {
                "fly_from": origin.upper(),
                "fly_to": destination.upper(),
                "date_from": f"01/{month:02d}/{year}",
                "date_to": f"{num_days}/{month:02d}/{year}",
                "one_for_city": 0,
                "curr": self._currency,
                "limit": num_days,
                "sort": "price",
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/search",
                    headers=headers,
                    params=params,
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Group by date and find cheapest
                    prices_by_date = {}
                    for flight in data.get("data", []):
                        dep_date = datetime.fromtimestamp(flight["dTimeUTC"]).date().isoformat()
                        price = flight.get("price", 0)
                        
                        if dep_date not in prices_by_date or price < prices_by_date[dep_date]:
                            prices_by_date[dep_date] = price
                    
                    return [
                        {"date": d, "price": p, "currency": self._currency}
                        for d, p in sorted(prices_by_date.items())
                    ]
        except Exception as e:
            logger.warning(f"Kiwi price calendar failed: {e}")
        
        return []
    
    async def health_check(self) -> bool:
        """Check Kiwi API connectivity"""
        if not self.is_configured:
            return False
        
        try:
            headers = {"apikey": settings.KIWI_API_KEY}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/locations/query",
                    headers=headers,
                    params={"term": "DUB"},
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception:
            return False
