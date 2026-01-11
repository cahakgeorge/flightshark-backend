"""
Skyscanner Flight Provider - Price comparison meta-search
https://developers.skyscanner.net/
"""
from typing import List, Optional
from datetime import date, datetime
import httpx
import logging

from app.config import settings
from app.schemas.flight import FlightOffer, FlightSegment
from .base import FlightProvider, ProviderError

logger = logging.getLogger(__name__)


class SkyscannerProvider(FlightProvider):
    """
    Skyscanner flight search provider.
    
    Meta-search provider that aggregates results from multiple airlines and OTAs.
    Good for price comparison.
    
    Requires RapidAPI subscription or direct Skyscanner partnership.
    """
    
    name = "skyscanner"
    priority = 2  # Secondary provider
    requests_per_minute = 50
    requests_per_day = 500
    
    # Skyscanner API endpoints (via RapidAPI)
    RAPIDAPI_HOST = "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com"
    BASE_URL = f"https://{RAPIDAPI_HOST}/apiservices"
    
    def __init__(self):
        super().__init__()
        self._market = "IE"  # Default market
        self._currency = "EUR"
        self._locale = "en-US"
    
    @property
    def is_configured(self) -> bool:
        """Check if Skyscanner API key is configured"""
        return bool(getattr(settings, 'SKYSCANNER_API_KEY', None))
    
    async def search(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        passengers: int = 1,
        cabin_class: str = "economy",
    ) -> List[FlightOffer]:
        """Search flights using Skyscanner API"""
        if not self.is_configured:
            raise ProviderError(self.name, "Skyscanner API key not configured")
        
        try:
            # Step 1: Create search session
            session_key = await self._create_session(
                origin, destination, departure_date, return_date, passengers, cabin_class
            )
            
            # Step 2: Poll results
            offers = await self._poll_results(session_key)
            
            self.record_success()
            logger.info(f"Skyscanner returned {len(offers)} offers for {origin}->{destination}")
            return offers
            
        except httpx.HTTPStatusError as e:
            self.record_failure(e)
            raise ProviderError(self.name, f"HTTP {e.response.status_code}", e)
        except Exception as e:
            self.record_failure(e)
            raise ProviderError(self.name, str(e), e)
    
    async def _create_session(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date],
        passengers: int,
        cabin_class: str,
    ) -> str:
        """Create a pricing session and return session key"""
        cabin_map = {
            "economy": "economy",
            "premium_economy": "premiumeconomy",
            "business": "business",
            "first": "first",
        }
        
        headers = {
            "X-RapidAPI-Key": settings.SKYSCANNER_API_KEY,
            "X-RapidAPI-Host": self.RAPIDAPI_HOST,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        
        data = {
            "country": self._market,
            "currency": self._currency,
            "locale": self._locale,
            "originPlace": f"{origin}-sky",
            "destinationPlace": f"{destination}-sky",
            "outboundDate": departure_date.isoformat(),
            "adults": passengers,
            "cabinClass": cabin_map.get(cabin_class, "economy"),
        }
        
        if return_date:
            data["inboundDate"] = return_date.isoformat()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.BASE_URL}/pricing/v1.0",
                headers=headers,
                data=data,
                timeout=30.0,
            )
            
            # Session created - key is in Location header
            if response.status_code == 201:
                location = response.headers.get("Location", "")
                return location.split("/")[-1] if location else ""
            
            response.raise_for_status()
            return ""
    
    async def _poll_results(self, session_key: str, max_attempts: int = 5) -> List[FlightOffer]:
        """Poll session for results"""
        if not session_key:
            return []
        
        headers = {
            "X-RapidAPI-Key": settings.SKYSCANNER_API_KEY,
            "X-RapidAPI-Host": self.RAPIDAPI_HOST,
        }
        
        import asyncio
        
        for attempt in range(max_attempts):
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/pricing/uk2/v1.0/{session_key}",
                    headers=headers,
                    params={"sortType": "price", "sortOrder": "asc", "pageIndex": 0, "pageSize": 50},
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check if search is complete
                    if data.get("Status") == "UpdatesComplete":
                        return self._parse_response(data)
                    
                    # Still updating, wait and retry
                    await asyncio.sleep(1)
                else:
                    break
        
        return []
    
    def _parse_response(self, data: dict) -> List[FlightOffer]:
        """Parse Skyscanner API response"""
        offers = []
        
        # Build lookup dictionaries
        legs = {leg["Id"]: leg for leg in data.get("Legs", [])}
        segments = {seg["Id"]: seg for seg in data.get("Segments", [])}
        carriers = {c["Id"]: c for c in data.get("Carriers", [])}
        places = {p["Id"]: p for p in data.get("Places", [])}
        
        for itinerary in data.get("Itineraries", [])[:50]:
            try:
                pricing = itinerary.get("PricingOptions", [{}])[0]
                price = pricing.get("Price", 0)
                
                outbound_leg_id = itinerary.get("OutboundLegId")
                outbound_leg = legs.get(outbound_leg_id, {})
                
                # Parse outbound segments
                outbound_segments = self._parse_leg_segments(
                    outbound_leg, segments, carriers, places
                )
                
                # Parse inbound if round trip
                return_segments = None
                inbound_leg_id = itinerary.get("InboundLegId")
                if inbound_leg_id:
                    inbound_leg = legs.get(inbound_leg_id, {})
                    return_segments = self._parse_leg_segments(
                        inbound_leg, segments, carriers, places
                    )
                
                # Calculate duration
                duration = outbound_leg.get("Duration", 0)
                if return_segments:
                    inbound_leg = legs.get(inbound_leg_id, {})
                    duration += inbound_leg.get("Duration", 0)
                
                # Get carrier info
                carrier_ids = outbound_leg.get("Carriers", [])
                airline = carriers.get(carrier_ids[0], {}).get("Code", "XX") if carrier_ids else "XX"
                
                offers.append(FlightOffer(
                    id=f"skyscanner-{itinerary.get('Id', '')}",
                    price=float(price),
                    currency=self._currency,
                    cabin_class="economy",
                    airline=airline,
                    outbound_segments=outbound_segments,
                    return_segments=return_segments,
                    total_duration_minutes=duration,
                    stops=len(outbound_segments) - 1 if outbound_segments else 0,
                    is_direct=len(outbound_segments) == 1 if outbound_segments else False,
                    source="skyscanner",
                ))
                
            except Exception as e:
                logger.warning(f"Failed to parse Skyscanner itinerary: {e}")
                continue
        
        return offers
    
    def _parse_leg_segments(
        self, 
        leg: dict, 
        segments: dict, 
        carriers: dict, 
        places: dict
    ) -> List[FlightSegment]:
        """Parse leg segments"""
        parsed_segments = []
        
        for seg_id in leg.get("SegmentIds", []):
            seg = segments.get(seg_id, {})
            
            origin_place = places.get(seg.get("OriginStation"), {})
            dest_place = places.get(seg.get("DestinationStation"), {})
            carrier = carriers.get(seg.get("Carrier"), {})
            
            try:
                departure_time = datetime.fromisoformat(
                    seg.get("DepartureDateTime", "").replace("Z", "+00:00")
                )
                arrival_time = datetime.fromisoformat(
                    seg.get("ArrivalDateTime", "").replace("Z", "+00:00")
                )
            except:
                departure_time = datetime.now()
                arrival_time = datetime.now()
            
            parsed_segments.append(FlightSegment(
                departure_airport=origin_place.get("Code", "XXX"),
                arrival_airport=dest_place.get("Code", "XXX"),
                departure_time=departure_time,
                arrival_time=arrival_time,
                flight_number=f"{carrier.get('Code', 'XX')}{seg.get('FlightNumber', '000')}",
                airline=carrier.get("Code", "XX"),
                duration_minutes=seg.get("Duration", 0),
            ))
        
        return parsed_segments
    
    async def get_price_calendar(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
    ) -> List[dict]:
        """Get cheapest prices using Skyscanner Browse Quotes"""
        if not self.is_configured:
            return []
        
        try:
            headers = {
                "X-RapidAPI-Key": settings.SKYSCANNER_API_KEY,
                "X-RapidAPI-Host": self.RAPIDAPI_HOST,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/browsedates/v1.0/{self._market}/{self._currency}/{self._locale}/{origin}/{destination}/{year}-{month:02d}",
                    headers=headers,
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return [
                        {
                            "date": quote.get("OutboundLeg", {}).get("DepartureDate", "").split("T")[0],
                            "price": float(quote.get("MinPrice", 0)),
                            "currency": self._currency,
                        }
                        for quote in data.get("Quotes", [])
                    ]
        except Exception as e:
            logger.warning(f"Skyscanner price calendar failed: {e}")
        
        return []
    
    async def health_check(self) -> bool:
        """Check Skyscanner API connectivity"""
        if not self.is_configured:
            return False
        
        try:
            headers = {
                "X-RapidAPI-Key": settings.SKYSCANNER_API_KEY,
                "X-RapidAPI-Host": self.RAPIDAPI_HOST,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.BASE_URL}/reference/v1.0/currencies",
                    headers=headers,
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception:
            return False
