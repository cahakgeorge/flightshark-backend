"""
Reference Data Service - Fetches and manages airport, airline, and route data
from Amadeus and other sources
"""
import httpx
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from tenacity import retry, stop_after_attempt, wait_exponential
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import asyncio

from app.config import settings

logger = logging.getLogger(__name__)


class AmadeusReferenceDataService:
    """
    Fetches reference data from Amadeus APIs:
    - Airport & City Search
    - Airline Code Lookup
    - Flight Routes (Direct Destinations)
    """
    
    def __init__(self):
        self.token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.base_url = settings.AMADEUS_BASE_URL.replace('/v2', '')
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def _get_token(self) -> str:
        """Get Amadeus API access token"""
        if self.token and self.token_expiry and datetime.utcnow() < self.token_expiry:
            return self.token
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/security/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.AMADEUS_API_KEY,
                    "client_secret": settings.AMADEUS_API_SECRET,
                }
            )
            response.raise_for_status()
            data = response.json()
            
            self.token = data["access_token"]
            self.token_expiry = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            
            return self.token
    
    async def _api_get(self, endpoint: str, params: dict = None) -> dict:
        """Make authenticated GET request to Amadeus API"""
        token = await self._get_token()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}{endpoint}",
                params=params,
                headers={"Authorization": f"Bearer {token}"}
            )
            response.raise_for_status()
            return response.json()
    
    # ==================
    # AIRPORT DATA
    # ==================
    
    async def fetch_airport_by_code(self, iata_code: str) -> Optional[Dict[str, Any]]:
        """Fetch airport details by IATA code"""
        try:
            data = await self._api_get(
                f"/v1/reference-data/locations/{iata_code}",
                {"view": "FULL"}
            )
            return self._parse_airport(data.get("data"))
        except Exception as e:
            logger.warning(f"Failed to fetch airport {iata_code}: {e}")
            return None
    
    async def search_airports(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search airports by keyword"""
        try:
            data = await self._api_get(
                "/v1/reference-data/locations",
                {
                    "keyword": keyword,
                    "subType": "AIRPORT",
                    "view": "FULL",
                    "page[limit]": limit
                }
            )
            return [self._parse_airport(a) for a in data.get("data", [])]
        except Exception as e:
            logger.error(f"Airport search failed: {e}")
            return []
    
    async def fetch_airports_by_city(self, city_code: str) -> List[Dict[str, Any]]:
        """Fetch all airports in a city"""
        try:
            data = await self._api_get(
                "/v1/reference-data/locations",
                {
                    "keyword": city_code,
                    "subType": "AIRPORT,CITY",
                    "view": "FULL"
                }
            )
            return [self._parse_airport(a) for a in data.get("data", []) if a.get("subType") == "AIRPORT"]
        except Exception as e:
            logger.error(f"Failed to fetch airports for city {city_code}: {e}")
            return []
    
    def _parse_airport(self, data: dict) -> Optional[Dict[str, Any]]:
        """Parse Amadeus airport data into our format"""
        if not data:
            return None
            
        geo = data.get("geoCode", {})
        address = data.get("address", {})
        
        return {
            "iata_code": data.get("iataCode"),
            "name": data.get("name"),
            "city": address.get("cityName"),
            "country": address.get("countryName"),
            "country_code": address.get("countryCode"),
            "latitude": geo.get("latitude"),
            "longitude": geo.get("longitude"),
            "timezone": data.get("timeZoneOffset"),
        }
    
    # ==================
    # AIRLINE DATA
    # ==================
    
    async def fetch_airline_by_code(self, iata_code: str) -> Optional[Dict[str, Any]]:
        """Fetch airline details by IATA code"""
        try:
            data = await self._api_get(
                f"/v1/reference-data/airlines",
                {"airlineCodes": iata_code}
            )
            airlines = data.get("data", [])
            if airlines:
                return self._parse_airline(airlines[0])
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch airline {iata_code}: {e}")
            return None
    
    async def fetch_airlines_batch(self, iata_codes: List[str]) -> List[Dict[str, Any]]:
        """Fetch multiple airlines in one request"""
        try:
            # Amadeus allows comma-separated codes
            codes = ",".join(iata_codes[:100])  # Max 100 at a time
            data = await self._api_get(
                "/v1/reference-data/airlines",
                {"airlineCodes": codes}
            )
            return [self._parse_airline(a) for a in data.get("data", [])]
        except Exception as e:
            logger.error(f"Batch airline fetch failed: {e}")
            return []
    
    def _parse_airline(self, data: dict) -> Dict[str, Any]:
        """Parse Amadeus airline data"""
        return {
            "iata_code": data.get("iataCode"),
            "icao_code": data.get("icaoCode"),
            "name": data.get("businessName") or data.get("commonName"),
            "logo_url": f"https://pics.avs.io/100/100/{data.get('iataCode')}.png"
        }
    
    # ==================
    # ROUTE DATA (Direct Destinations)
    # ==================
    
    async def fetch_direct_destinations(self, origin: str) -> List[Dict[str, Any]]:
        """
        Fetch all direct destinations from an airport
        Uses Amadeus Flight Destinations API
        """
        try:
            # Note: This endpoint requires production access in Amadeus
            # For test environment, we'll use a different approach
            data = await self._api_get(
                "/v1/airport/direct-destinations",
                {"departureAirportCode": origin}
            )
            
            destinations = []
            for item in data.get("data", []):
                dest = {
                    "origin_code": origin,
                    "destination_code": item.get("destination"),
                    "is_direct": True,
                }
                destinations.append(dest)
            
            return destinations
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"No direct destinations found for {origin}")
            else:
                logger.warning(f"Failed to fetch destinations for {origin}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching destinations for {origin}: {e}")
            return []
    
    async def fetch_flight_routes_from_search(
        self, 
        origin: str, 
        date_range_days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Alternative: Discover routes by searching flights
        This works with test API but is slower
        """
        from datetime import date, timedelta
        
        routes = []
        departure_date = date.today() + timedelta(days=14)
        
        # Common European destinations to check
        destinations_to_check = [
            "BCN", "AMS", "LIS", "CDG", "FCO", "LHR", "BER", "PRG",
            "VIE", "MAD", "MUC", "ZRH", "CPH", "OSL", "ARN", "HEL",
            "ATH", "IST", "DXB", "JFK", "LAX", "BKK", "SIN", "LGW",
            "STN", "EDI", "MAN", "BHX", "GLA", "ORK", "SNN"
        ]
        
        for dest in destinations_to_check:
            if dest == origin:
                continue
            
            try:
                logger.debug(f"Checking route {origin}-{dest}...")
                # Quick check if route exists using flight offers API
                data = await self._api_get(
                    "/v2/shopping/flight-offers",
                    {
                        "originLocationCode": origin,
                        "destinationLocationCode": dest,
                        "departureDate": departure_date.isoformat(),
                        "adults": 1,
                        "max": 1  # Just need to know if route exists
                    }
                )
                
                offers = data.get("data", [])
                if offers:
                    offer = offers[0]
                    itineraries = offer.get("itineraries", [])
                    segments = itineraries[0].get("segments", []) if itineraries else []
                    
                    routes.append({
                        "origin_code": origin,
                        "destination_code": dest,
                        "is_direct": len(segments) == 1,
                        "sample_price": float(offer["price"]["total"]),
                        "airlines": list(set(
                            seg["carrierCode"] 
                            for itin in itineraries
                            for seg in itin.get("segments", [])
                        ))
                    })
                    logger.info(f"Found route {origin}-{dest}")
                    
                # Rate limiting - be nice to API
                await asyncio.sleep(1.0)
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    logger.debug(f"No route {origin}-{dest}: Invalid request")
                elif e.response.status_code == 429:
                    logger.warning(f"Rate limited, waiting 5 seconds...")
                    await asyncio.sleep(5.0)
                else:
                    logger.debug(f"No route {origin}-{dest}: {e.response.status_code}")
                continue
            except Exception as e:
                logger.debug(f"No route {origin}-{dest}: {e}")
                continue
        
        return routes


class ReferenceDataSeeder:
    """
    Seeds and updates reference data in the database
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.amadeus = AmadeusReferenceDataService()
    
    async def seed_airport_destinations(self, airport_code: str) -> int:
        """
        Seed all destinations from a specific airport
        Returns count of destinations found
        """
        logger.info(f"Seeding destinations for {airport_code}...")
        
        # Try direct destinations API first
        routes = await self.amadeus.fetch_direct_destinations(airport_code)
        
        # If no results, use search method
        if not routes:
            routes = await self.amadeus.fetch_flight_routes_from_search(airport_code)
        
        if not routes:
            logger.warning(f"No routes found for {airport_code}")
            return 0
        
        success_count = 0
        
        # Insert/update destinations
        for route in routes:
            dest_code = route.get("destination_code")
            if not dest_code:
                logger.warning(f"Skipping route with no destination code: {route}")
                continue
            
            # Get destination airport info from our DB first, then API
            dest_result = await self.db.execute(
                text("SELECT city, country, country_code FROM airports WHERE iata_code = :code"),
                {"code": dest_code}
            )
            dest_row = dest_result.fetchone()
            
            if dest_row:
                city, country, country_code = dest_row
            else:
                # Try to fetch from API
                dest_info = await self.amadeus.fetch_airport_by_code(dest_code)
                city = dest_info.get("city") if dest_info else None
                country = dest_info.get("country") if dest_info else None
                country_code = dest_info.get("country_code") if dest_info else None
            
            try:
                await self.db.execute(text("""
                    INSERT INTO airport_destinations (
                        airport_code, destination_code, destination_city,
                        destination_country, destination_country_code,
                        airlines_serving, airline_count, is_direct,
                        price_low, price_avg
                    ) VALUES (
                        :origin, :dest, :city, :country, :country_code,
                        :airlines, :airline_count, :is_direct,
                        :price_low, :price_avg
                    )
                    ON CONFLICT (airport_code, destination_code) 
                    DO UPDATE SET
                        airlines_serving = EXCLUDED.airlines_serving,
                        airline_count = EXCLUDED.airline_count,
                        is_direct = EXCLUDED.is_direct,
                        price_low = COALESCE(EXCLUDED.price_low, airport_destinations.price_low),
                        price_avg = COALESCE(EXCLUDED.price_avg, airport_destinations.price_avg),
                        updated_at = NOW()
                """), {
                    "origin": airport_code,
                    "dest": dest_code,
                    "city": city,
                    "country": country,
                    "country_code": country_code,
                    "airlines": route.get("airlines", []),
                    "airline_count": len(route.get("airlines", [])),
                    "is_direct": route.get("is_direct", True),
                    "price_low": route.get("sample_price"),
                    "price_avg": route.get("sample_price")
                })
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to insert route {airport_code}-{dest_code}: {e}")
                continue
        
        await self.db.commit()
        
        logger.info(f"Seeded {success_count} destinations for {airport_code}")
        return success_count
    
    async def update_airport_stats(self, airport_code: str):
        """Update aggregated stats for an airport"""
        await self.db.execute(text("""
            INSERT INTO airport_stats (
                airport_code,
                direct_destinations_count,
                airlines_serving,
                airline_count,
                top_destinations
            )
            SELECT 
                :code,
                COUNT(*) FILTER (WHERE is_direct = TRUE),
                ARRAY_AGG(DISTINCT unnested_airline) FILTER (WHERE unnested_airline IS NOT NULL),
                COUNT(DISTINCT unnested_airline) FILTER (WHERE unnested_airline IS NOT NULL),
                (
                    SELECT jsonb_agg(row_to_json(t))
                    FROM (
                        SELECT destination_code as code, destination_city as city
                        FROM airport_destinations
                        WHERE airport_code = :code AND is_active = TRUE
                        ORDER BY popularity_score DESC NULLS LAST
                        LIMIT 10
                    ) t
                )
            FROM airport_destinations
            LEFT JOIN LATERAL unnest(airlines_serving) AS unnested_airline ON TRUE
            WHERE airport_code = :code AND is_active = TRUE
            GROUP BY airport_code
            ON CONFLICT (airport_code) DO UPDATE SET
                direct_destinations_count = EXCLUDED.direct_destinations_count,
                airlines_serving = EXCLUDED.airlines_serving,
                airline_count = EXCLUDED.airline_count,
                top_destinations = EXCLUDED.top_destinations,
                updated_at = NOW()
        """), {"code": airport_code})
        
        await self.db.commit()
    
    async def seed_popular_route(self, origin: str, destination: str):
        """Seed/update a popular route with aggregated data"""
        from app.services.flight_service import FlightService
        
        flight_service = FlightService()
        
        # Get sample pricing
        from datetime import date, timedelta
        departure = date.today() + timedelta(days=14)
        
        try:
            offers = await flight_service.search_flights(
                origin=origin,
                destination=destination,
                departure_date=departure,
                passengers=1
            )
            
            if not offers:
                return
            
            # Aggregate by airline
            airlines_data = {}
            for offer in offers:
                code = offer.airline
                if code not in airlines_data:
                    airlines_data[code] = {
                        "code": code,
                        "prices": [],
                        "durations": []
                    }
                airlines_data[code]["prices"].append(offer.price)
                airlines_data[code]["durations"].append(offer.total_duration_minutes)
            
            # Calculate stats
            all_prices = [o.price for o in offers]
            all_durations = [o.total_duration_minutes for o in offers]
            
            airlines_json = [
                {
                    "code": data["code"],
                    "price_avg": sum(data["prices"]) / len(data["prices"]),
                    "price_low": min(data["prices"])
                }
                for data in airlines_data.values()
            ]
            
            cheapest = min(offers, key=lambda x: x.price)
            
            # Get city names from airports table
            origin_info = await self.db.execute(
                text("SELECT city, country FROM airports WHERE iata_code = :code"),
                {"code": origin}
            )
            origin_row = origin_info.fetchone()
            
            dest_info = await self.db.execute(
                text("SELECT city, country FROM airports WHERE iata_code = :code"),
                {"code": destination}
            )
            dest_row = dest_info.fetchone()
            
            import json
            await self.db.execute(text("""
                INSERT INTO popular_routes (
                    origin_code, destination_code,
                    origin_city, origin_country,
                    destination_city, destination_country,
                    airlines, airline_count,
                    cheapest_airline, cheapest_price,
                    price_range_low, price_range_high, avg_price,
                    min_duration_minutes, max_duration_minutes, avg_duration_minutes,
                    has_direct_flights, last_price_check
                ) VALUES (
                    :origin, :dest,
                    :origin_city, :origin_country,
                    :dest_city, :dest_country,
                    :airlines::jsonb, :airline_count,
                    :cheapest_airline, :cheapest_price,
                    :price_low, :price_high, :price_avg,
                    :dur_min, :dur_max, :dur_avg,
                    :has_direct, NOW()
                )
                ON CONFLICT (origin_code, destination_code) DO UPDATE SET
                    airlines = EXCLUDED.airlines,
                    airline_count = EXCLUDED.airline_count,
                    cheapest_airline = EXCLUDED.cheapest_airline,
                    cheapest_price = EXCLUDED.cheapest_price,
                    price_range_low = EXCLUDED.price_range_low,
                    price_range_high = EXCLUDED.price_range_high,
                    avg_price = EXCLUDED.avg_price,
                    min_duration_minutes = EXCLUDED.min_duration_minutes,
                    max_duration_minutes = EXCLUDED.max_duration_minutes,
                    avg_duration_minutes = EXCLUDED.avg_duration_minutes,
                    has_direct_flights = EXCLUDED.has_direct_flights,
                    last_price_check = NOW(),
                    updated_at = NOW()
            """), {
                "origin": origin,
                "dest": destination,
                "origin_city": origin_row[0] if origin_row else None,
                "origin_country": origin_row[1] if origin_row else None,
                "dest_city": dest_row[0] if dest_row else None,
                "dest_country": dest_row[1] if dest_row else None,
                "airlines": json.dumps(airlines_json),
                "airline_count": len(airlines_data),
                "cheapest_airline": cheapest.airline,
                "cheapest_price": cheapest.price,
                "price_low": min(all_prices),
                "price_high": max(all_prices),
                "price_avg": sum(all_prices) / len(all_prices),
                "dur_min": min(all_durations),
                "dur_max": max(all_durations),
                "dur_avg": sum(all_durations) // len(all_durations),
                "has_direct": any(o.is_direct for o in offers)
            })
            
            await self.db.commit()
            logger.info(f"Seeded popular route {origin}-{destination}")
            
        except Exception as e:
            logger.error(f"Failed to seed route {origin}-{destination}: {e}")
    
    async def log_sync(
        self,
        data_type: str,
        source: str,
        status: str,
        records_fetched: int = 0,
        records_created: int = 0,
        records_updated: int = 0,
        error_message: str = None,
        started_at: datetime = None,
    ):
        """Log a data sync operation"""
        completed_at = datetime.utcnow()
        duration = (completed_at - started_at).total_seconds() if started_at else None
        
        await self.db.execute(text("""
            INSERT INTO data_sync_log (
                data_type, source, status,
                records_fetched, records_created, records_updated,
                error_message, started_at, completed_at, duration_seconds
            ) VALUES (
                :type, :source, :status,
                :fetched, :created, :updated,
                :error, :started, :completed, :duration
            )
        """), {
            "type": data_type,
            "source": source,
            "status": status,
            "fetched": records_fetched,
            "created": records_created,
            "updated": records_updated,
            "error": error_message,
            "started": started_at or completed_at,
            "completed": completed_at,
            "duration": duration
        })
        await self.db.commit()
