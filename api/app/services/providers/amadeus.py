"""
Amadeus Flight Provider - Primary flight data source
https://developers.amadeus.com/
"""
from typing import List, Optional
from datetime import date, datetime, timedelta
import httpx
import logging
import re
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.schemas.flight import FlightOffer, FlightSegment
from .base import FlightProvider, ProviderError

logger = logging.getLogger(__name__)


class AmadeusProvider(FlightProvider):
    """
    Amadeus flight search provider.
    
    Primary provider with comprehensive global coverage.
    Requires API key and secret from https://developers.amadeus.com/
    """
    
    name = "amadeus"
    priority = 1  # Primary provider
    requests_per_minute = 30  # Free tier limit
    requests_per_day = 2000   # Free tier: ~2000/month
    
    def __init__(self):
        super().__init__()
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    @property
    def is_configured(self) -> bool:
        """Check if Amadeus credentials are configured"""
        return bool(settings.AMADEUS_API_KEY and settings.AMADEUS_API_SECRET)
    
    @property
    def base_url(self) -> str:
        """Get API base URL (test or production)"""
        return settings.AMADEUS_BASE_URL
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get_token(self) -> str:
        """Get or refresh OAuth access token"""
        if self._token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return self._token
        
        auth_url = self.base_url.replace("/v2", "/v1/security/oauth2/token")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                auth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.AMADEUS_API_KEY,
                    "client_secret": settings.AMADEUS_API_SECRET,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            
            self._token = data["access_token"]
            self._token_expiry = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            
            return self._token
    
    async def search(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        passengers: int = 1,
        cabin_class: str = "economy",
    ) -> List[FlightOffer]:
        """Search flights using Amadeus Flight Offers Search API"""
        if not self.is_configured:
            raise ProviderError(self.name, "Amadeus API credentials not configured")
        
        try:
            token = await self._get_token()
            
            params = {
                "originLocationCode": origin.upper(),
                "destinationLocationCode": destination.upper(),
                "departureDate": departure_date.isoformat(),
                "adults": passengers,
                "currencyCode": "EUR",
                "max": 50,
            }
            
            if return_date:
                params["returnDate"] = return_date.isoformat()
            
            cabin_map = {
                "economy": "ECONOMY",
                "premium_economy": "PREMIUM_ECONOMY",
                "business": "BUSINESS",
                "first": "FIRST",
            }
            params["travelClass"] = cabin_map.get(cabin_class, "ECONOMY")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/shopping/flight-offers",
                    params=params,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
            
            offers = self._parse_response(data)
            self.record_success()
            logger.info(f"Amadeus returned {len(offers)} offers for {origin}->{destination}")
            return offers
            
        except httpx.HTTPStatusError as e:
            self.record_failure(e)
            raise ProviderError(self.name, f"HTTP {e.response.status_code}: {e.response.text}", e)
        except Exception as e:
            self.record_failure(e)
            raise ProviderError(self.name, str(e), e)
    
    def _parse_response(self, data: dict) -> List[FlightOffer]:
        """Parse Amadeus API response"""
        offers = []
        
        for offer_data in data.get("data", []):
            try:
                itineraries = offer_data.get("itineraries", [])
                if not itineraries:
                    continue
                
                # Parse outbound segments
                outbound_segments = self._parse_segments(itineraries[0].get("segments", []))
                
                # Parse return segments if exists
                return_segments = None
                if len(itineraries) > 1:
                    return_segments = self._parse_segments(itineraries[1].get("segments", []))
                
                # Calculate total duration
                total_duration = sum(s.duration_minutes for s in outbound_segments)
                if return_segments:
                    total_duration += sum(s.duration_minutes for s in return_segments)
                
                price = float(offer_data["price"]["total"])
                
                offer = FlightOffer(
                    id=f"amadeus-{offer_data['id']}",
                    price=price,
                    currency=offer_data["price"]["currency"],
                    cabin_class=offer_data["travelerPricings"][0]["fareDetailsBySegment"][0]["cabin"],
                    airline=outbound_segments[0].airline if outbound_segments else "Unknown",
                    outbound_segments=outbound_segments,
                    return_segments=return_segments,
                    total_duration_minutes=total_duration,
                    stops=len(outbound_segments) - 1,
                    is_direct=len(outbound_segments) == 1,
                    source="amadeus",
                )
                offers.append(offer)
                
            except Exception as e:
                logger.warning(f"Failed to parse Amadeus offer: {e}")
                continue
        
        return offers
    
    def _parse_segments(self, segments_data: list) -> List[FlightSegment]:
        """Parse flight segments"""
        segments = []
        for seg in segments_data:
            duration_str = seg.get("duration", "PT0H0M")
            duration_minutes = self._parse_duration(duration_str)
            
            segments.append(FlightSegment(
                departure_airport=seg["departure"]["iataCode"],
                arrival_airport=seg["arrival"]["iataCode"],
                departure_time=datetime.fromisoformat(seg["departure"]["at"].replace("Z", "+00:00")),
                arrival_time=datetime.fromisoformat(seg["arrival"]["at"].replace("Z", "+00:00")),
                flight_number=f"{seg['carrierCode']}{seg['number']}",
                airline=seg["carrierCode"],
                duration_minutes=duration_minutes,
                aircraft=seg.get("aircraft", {}).get("code"),
            ))
        return segments
    
    def _parse_duration(self, duration_str: str) -> int:
        """Parse ISO 8601 duration to minutes"""
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', duration_str)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            return hours * 60 + minutes
        return 0
    
    async def get_price_calendar(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
    ) -> List[dict]:
        """Get cheapest prices using Amadeus Flight Inspiration Search"""
        if not self.is_configured:
            return []
        
        try:
            token = await self._get_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/shopping/flight-destinations",
                    params={
                        "origin": origin.upper(),
                        "destination": destination.upper(),
                        "departureDate": f"{year}-{month:02d}-01",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return [
                        {
                            "date": item.get("departureDate"),
                            "price": float(item.get("price", {}).get("total", 0)),
                            "currency": item.get("price", {}).get("currency", "EUR"),
                        }
                        for item in data.get("data", [])
                    ]
        except Exception as e:
            logger.warning(f"Amadeus price calendar failed: {e}")
        
        return []
    
    async def health_check(self) -> bool:
        """Check Amadeus API connectivity"""
        if not self.is_configured:
            return False
        
        try:
            await self._get_token()
            return True
        except Exception:
            return False
