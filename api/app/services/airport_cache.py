"""
Airport Cache Service - Preloads airports into Redis for instant search
"""
import json
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.airport import Airport
from app.utils.redis import get_redis

logger = logging.getLogger(__name__)

# Cache keys
AIRPORTS_ALL_KEY = "airports:all"  # Hash of all airports by code
AIRPORTS_INDEX_KEY = "airports:search_index"  # Pre-built search index
AIRPORTS_LOADED_KEY = "airports:loaded"  # Flag indicating cache is loaded
AIRPORTS_VERSION_KEY = "airports:version"  # Version for cache invalidation


class AirportCacheService:
    """
    Service for managing airport data in Redis cache.
    Airports are preloaded at startup for instant search.
    """
    
    @staticmethod
    def _airport_to_dict(airport: Airport) -> Dict[str, Any]:
        """Convert Airport model to dictionary for caching"""
        return {
            "iata_code": airport.iata_code,
            "icao_code": airport.icao_code,
            "name": airport.name,
            "city": airport.city,
            "country": airport.country,
            "country_code": airport.country_code,
            "latitude": airport.latitude,
            "longitude": airport.longitude,
            "is_major": airport.is_major,
            "is_active": airport.is_active,
        }
    
    @staticmethod
    async def load_airports_to_cache(db: AsyncSession) -> int:
        """
        Load all active airports from database into Redis cache.
        Called during application startup.
        
        Returns the number of airports loaded.
        """
        logger.info("Loading airports into cache...")
        
        try:
            cache = await get_redis()
            
            # Fetch all active airports from database
            stmt = select(Airport).where(Airport.is_active == True).order_by(Airport.city)
            result = await db.execute(stmt)
            airports = result.scalars().all()
            
            if not airports:
                logger.warning("No airports found in database")
                return 0
            
            # Build the cache data structures
            airports_hash = {}  # code -> airport data
            search_entries = []  # For building search index
            
            for airport in airports:
                airport_data = AirportCacheService._airport_to_dict(airport)
                airports_hash[airport.iata_code] = json.dumps(airport_data)
                
                # Build search index entries
                # We'll index by: code, city (lowercase), name words
                code = airport.iata_code.upper()
                city_lower = airport.city.lower()
                name_lower = airport.name.lower()
                
                # Create search entry with all searchable terms
                search_entry = {
                    "code": code,
                    "city": city_lower,
                    "name": name_lower,
                    "country": airport.country.lower(),
                    "is_major": airport.is_major,
                    "data": airport_data,
                }
                search_entries.append(search_entry)
            
            # Store in Redis using pipeline for efficiency
            pipe = cache.pipeline()
            
            # Clear existing data
            pipe.delete(AIRPORTS_ALL_KEY)
            pipe.delete(AIRPORTS_INDEX_KEY)
            
            # Store all airports hash
            if airports_hash:
                pipe.hset(AIRPORTS_ALL_KEY, mapping=airports_hash)
            
            # Store search index as JSON list (for in-memory search)
            pipe.set(AIRPORTS_INDEX_KEY, json.dumps(search_entries))
            
            # Set loaded flag with TTL (refresh daily)
            pipe.setex(AIRPORTS_LOADED_KEY, 86400, "1")  # 24 hours
            pipe.set(AIRPORTS_VERSION_KEY, str(len(airports)))
            
            await pipe.execute()
            
            logger.info(f"Successfully loaded {len(airports)} airports into cache")
            return len(airports)
            
        except Exception as e:
            logger.error(f"Failed to load airports into cache: {e}", exc_info=True)
            return 0
    
    @staticmethod
    async def is_cache_loaded() -> bool:
        """Check if airports are loaded in cache"""
        try:
            cache = await get_redis()
            return await cache.exists(AIRPORTS_LOADED_KEY) > 0
        except Exception:
            return False
    
    @staticmethod
    async def get_airport_by_code(code: str) -> Optional[Dict[str, Any]]:
        """Get a single airport by IATA code from cache"""
        try:
            cache = await get_redis()
            data = await cache.hget(AIRPORTS_ALL_KEY, code.upper())
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Cache error getting airport {code}: {e}")
            return None
    
    @staticmethod
    async def search_airports(
        query: str,
        limit: int = 10,
        group_by_city: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Search airports from cached data.
        This is the main search function - searches in-memory cached data.
        
        Search priority:
        1. Exact IATA code match
        2. Code starts with query
        3. City starts with query
        4. City/name contains query
        
        If group_by_city=True, returns results grouped by city for multi-airport cities.
        """
        query = query.strip()
        if len(query) < 2:
            return []
        
        query_upper = query.upper()
        query_lower = query.lower()
        
        try:
            cache = await get_redis()
            
            # Get the search index
            index_data = await cache.get(AIRPORTS_INDEX_KEY)
            if not index_data:
                logger.warning("Airport search index not found in cache")
                return []
            
            search_entries = json.loads(index_data)
            
            # Search results with scoring
            results = []
            seen_codes = set()
            
            for entry in search_entries:
                code = entry["code"]
                if code in seen_codes:
                    continue
                
                score = 0
                
                # Exact code match (highest priority)
                if code == query_upper:
                    score = 1000
                # Code starts with query
                elif code.startswith(query_upper):
                    score = 500
                # City starts with query
                elif entry["city"].startswith(query_lower):
                    score = 300
                # City contains query
                elif query_lower in entry["city"]:
                    score = 100
                # Name contains query
                elif query_lower in entry["name"]:
                    score = 50
                # Country contains query
                elif query_lower in entry["country"]:
                    score = 25
                
                if score > 0:
                    # Boost major airports
                    if entry["is_major"]:
                        score += 50
                    
                    results.append((score, entry["data"]))
                    seen_codes.add(code)
            
            # Sort by score (descending)
            results.sort(key=lambda x: x[0], reverse=True)
            
            if not group_by_city:
                return [r[1] for r in results[:limit]]
            
            # Group by city for multi-airport cities
            return AirportCacheService._group_airports_by_city(
                [r[1] for r in results], 
                limit
            )
            
        except Exception as e:
            logger.error(f"Airport search error: {e}", exc_info=True)
            return []
    
    @staticmethod
    def _group_airports_by_city(
        airports: List[Dict[str, Any]], 
        limit: int
    ) -> List[Dict[str, Any]]:
        """
        Group airports by city for multi-airport cities.
        
        Returns a mix of:
        - City groups (for cities with 2+ airports): { type: "city", city: "London", airports: [...] }
        - Individual airports (for cities with 1 airport): { type: "airport", ... }
        """
        from collections import defaultdict
        
        # Group airports by city+country (to handle same city names in different countries)
        city_airports = defaultdict(list)
        for airport in airports:
            city_key = f"{airport['city'].lower()}|{airport['country_code']}"
            city_airports[city_key].append(airport)
        
        results = []
        seen_cities = set()
        
        for airport in airports:
            if len(results) >= limit:
                break
                
            city_key = f"{airport['city'].lower()}|{airport['country_code']}"
            
            if city_key in seen_cities:
                continue
            
            city_group = city_airports[city_key]
            
            if len(city_group) >= 2:
                # Multi-airport city - create a city group
                # Sort airports in group by is_major (main airport first), then name
                sorted_airports = sorted(
                    city_group, 
                    key=lambda a: (not a.get('is_major', False), a['name'])
                )
                
                results.append({
                    "type": "city",
                    "city": airport['city'],
                    "country": airport['country'],
                    "country_code": airport['country_code'],
                    "airport_count": len(sorted_airports),
                    "airports": sorted_airports,
                    # Provide all airport codes for multi-origin search
                    "codes": [a['iata_code'] for a in sorted_airports],
                    # Display value
                    "display": f"{airport['city']} (All {len(sorted_airports)} airports)",
                })
            else:
                # Single airport city
                results.append({
                    "type": "airport",
                    **airport
                })
            
            seen_cities.add(city_key)
        
        return results
    
    @staticmethod
    async def get_popular_airports(
        country_code: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get popular (major) airports from cache"""
        try:
            cache = await get_redis()
            
            index_data = await cache.get(AIRPORTS_INDEX_KEY)
            if not index_data:
                return []
            
            search_entries = json.loads(index_data)
            
            # Filter major airports
            results = []
            for entry in search_entries:
                if entry["is_major"]:
                    if country_code is None or entry["data"]["country_code"] == country_code.upper():
                        results.append(entry["data"])
            
            # Sort by city name
            results.sort(key=lambda x: x["city"])
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error getting popular airports: {e}")
            return []
    
    @staticmethod
    async def invalidate_cache():
        """Invalidate the airport cache (force reload on next startup)"""
        try:
            cache = await get_redis()
            await cache.delete(AIRPORTS_LOADED_KEY)
            logger.info("Airport cache invalidated")
        except Exception as e:
            logger.warning(f"Failed to invalidate airport cache: {e}")


# Singleton instance for easy access
airport_cache = AirportCacheService()
