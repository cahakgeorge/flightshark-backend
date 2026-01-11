"""
Flight Search Service - Aggregates results from multiple providers
"""
from typing import List, Optional
from datetime import date, datetime
import httpx
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.schemas.flight import FlightOffer, FlightSegment

logger = logging.getLogger(__name__)


class FlightService:
    """
    Service for searching flights across multiple providers
    """
    
    def __init__(self):
        self.amadeus_token: Optional[str] = None
        self.amadeus_token_expiry: Optional[datetime] = None
    
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date] = None,
        passengers: int = 1,
        cabin_class: str = "economy",
        direct_only: bool = False,
    ) -> List[FlightOffer]:
        """
        Search for flights across all configured providers
        """
        all_offers = []
        
        # Try Amadeus first
        if settings.AMADEUS_API_KEY:
            try:
                amadeus_offers = await self._search_amadeus(
                    origin, destination, departure_date, return_date, passengers, cabin_class
                )
                all_offers.extend(amadeus_offers)
                logger.info(f"Amadeus returned {len(amadeus_offers)} offers")
            except Exception as e:
                logger.error(f"Amadeus search failed: {e}")
        
        # If no real API keys, return mock data
        if not all_offers:
            logger.info("Using mock flight data")
            all_offers = self._generate_mock_offers(
                origin, destination, departure_date, return_date, passengers
            )
        
        # Filter direct flights if requested
        if direct_only:
            all_offers = [o for o in all_offers if o.is_direct]
        
        # Sort by price
        all_offers.sort(key=lambda x: x.price)
        
        return all_offers
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get_amadeus_token(self) -> str:
        """Get Amadeus API access token"""
        if self.amadeus_token and self.amadeus_token_expiry and datetime.utcnow() < self.amadeus_token_expiry:
            return self.amadeus_token
        
        # Use the same base URL (test vs production) for auth
        auth_url = settings.AMADEUS_BASE_URL.replace("/v2", "/v1/security/oauth2/token")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                auth_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.AMADEUS_API_KEY,
                    "client_secret": settings.AMADEUS_API_SECRET,
                }
            )
            response.raise_for_status()
            data = response.json()
            
            self.amadeus_token = data["access_token"]
            # Token expires in `expires_in` seconds, refresh 60s early
            from datetime import timedelta
            self.amadeus_token_expiry = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            
            return self.amadeus_token
    
    async def _search_amadeus(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date],
        passengers: int,
        cabin_class: str,
    ) -> List[FlightOffer]:
        """Search flights using Amadeus API"""
        token = await self._get_amadeus_token()
        
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
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
                f"{settings.AMADEUS_BASE_URL}/shopping/flight-offers",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
        
        return self._parse_amadeus_response(data)
    
    def _parse_amadeus_response(self, data: dict) -> List[FlightOffer]:
        """Parse Amadeus API response into FlightOffer objects"""
        offers = []
        
        for offer_data in data.get("data", []):
            try:
                itineraries = offer_data.get("itineraries", [])
                if not itineraries:
                    continue
                
                # Parse outbound
                outbound_segments = self._parse_segments(itineraries[0].get("segments", []))
                
                # Parse return if exists
                return_segments = None
                if len(itineraries) > 1:
                    return_segments = self._parse_segments(itineraries[1].get("segments", []))
                
                # Calculate total duration
                total_duration = sum(s.duration_minutes for s in outbound_segments)
                if return_segments:
                    total_duration += sum(s.duration_minutes for s in return_segments)
                
                price = float(offer_data["price"]["total"])
                
                offer = FlightOffer(
                    id=offer_data["id"],
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
            # Parse ISO duration (PT2H30M)
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
        import re
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', duration_str)
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            return hours * 60 + minutes
        return 0
    
    def _generate_mock_offers(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: Optional[date],
        passengers: int,
    ) -> List[FlightOffer]:
        """Generate mock flight offers for development"""
        import random
        
        airlines = [
            ("RY", "Ryanair"),
            ("FR", "Ryanair"),
            ("EI", "Aer Lingus"),
            ("BA", "British Airways"),
            ("LH", "Lufthansa"),
            ("IB", "Iberia"),
            ("VY", "Vueling"),
        ]
        
        offers = []
        base_prices = [49, 79, 99, 129, 159, 199, 249]
        
        for i, price in enumerate(base_prices):
            airline_code, airline_name = random.choice(airlines)
            is_direct = random.random() > 0.3
            
            dep_hour = random.randint(6, 20)
            duration = random.randint(90, 240) if not is_direct else random.randint(90, 180)
            
            outbound = [FlightSegment(
                departure_airport=origin,
                arrival_airport=destination,
                departure_time=datetime.combine(departure_date, datetime.min.time().replace(hour=dep_hour)),
                arrival_time=datetime.combine(departure_date, datetime.min.time().replace(hour=(dep_hour + duration // 60) % 24)),
                flight_number=f"{airline_code}{random.randint(100, 999)}",
                airline=airline_code,
                duration_minutes=duration,
            )]
            
            if not is_direct:
                # Add connection
                stopover = random.choice(["LHR", "CDG", "AMS", "FRA", "MAD"])
                outbound = [
                    FlightSegment(
                        departure_airport=origin,
                        arrival_airport=stopover,
                        departure_time=datetime.combine(departure_date, datetime.min.time().replace(hour=dep_hour)),
                        arrival_time=datetime.combine(departure_date, datetime.min.time().replace(hour=(dep_hour + 2) % 24)),
                        flight_number=f"{airline_code}{random.randint(100, 999)}",
                        airline=airline_code,
                        duration_minutes=120,
                    ),
                    FlightSegment(
                        departure_airport=stopover,
                        arrival_airport=destination,
                        departure_time=datetime.combine(departure_date, datetime.min.time().replace(hour=(dep_hour + 4) % 24)),
                        arrival_time=datetime.combine(departure_date, datetime.min.time().replace(hour=(dep_hour + 6) % 24)),
                        flight_number=f"{airline_code}{random.randint(100, 999)}",
                        airline=airline_code,
                        duration_minutes=120,
                    ),
                ]
            
            offers.append(FlightOffer(
                id=f"mock-{i}",
                price=float(price * passengers),
                currency="EUR",
                cabin_class="economy",
                airline=airline_name,
                outbound_segments=outbound,
                return_segments=None,
                total_duration_minutes=sum(s.duration_minutes for s in outbound),
                stops=len(outbound) - 1,
                is_direct=len(outbound) == 1,
                source="mock",
            ))
        
        return offers
    
    async def get_cheapest_dates(
        self,
        origin: str,
        destination: str,
        year: int,
        month: int,
    ) -> List[dict]:
        """Get cheapest dates for a month"""
        import calendar
        from datetime import timedelta
        
        # Generate mock data for each day of the month
        _, num_days = calendar.monthrange(year, month)
        
        dates = []
        for day in range(1, num_days + 1):
            d = date(year, month, day)
            if d < date.today():
                continue
            
            # Generate realistic-ish prices
            import random
            base_price = 80
            
            # Weekends more expensive
            if d.weekday() >= 5:
                base_price += 30
            
            # Add some randomness
            price = base_price + random.randint(-20, 50)
            
            dates.append({
                "date": d.isoformat(),
                "price": price,
                "currency": "EUR",
            })
        
        return dates

