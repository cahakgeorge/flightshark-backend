"""
Airport Search & Autocomplete Endpoints

Performance: Airports are preloaded into Redis cache at startup.
Search operates entirely in-memory - no database queries needed.
"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List, Optional
import logging

from app.utils.database import get_db
from app.utils.redis import get_redis
from app.models.airport import Airport, City
from app.services.airport_cache import AirportCacheService
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class AirportResponse(BaseModel):
    """Airport response schema"""
    iata_code: str
    name: str
    city: str
    country: str
    country_code: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_major: bool = False
    
    class Config:
        from_attributes = True


class AirportSearchResponse(BaseModel):
    """Search results response (flat list)"""
    query: str
    results: List[AirportResponse]
    total: int


class CityGroup(BaseModel):
    """City with multiple airports"""
    type: str = "city"
    city: str
    country: str
    country_code: str
    airport_count: int
    airports: List[AirportResponse]
    codes: List[str]
    display: str


class GroupedAirportSearchResponse(BaseModel):
    """Search results grouped by city"""
    query: str
    results: List[dict]  # Mix of CityGroup and AirportResponse
    total: int


@router.get("/search", response_model=AirportSearchResponse)
async def search_airports(
    q: str = Query(..., min_length=2, max_length=50, description="Search query (city, airport name, or code)"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Search airports by city name, airport name, or IATA code.
    Used for autocomplete in the search form.
    
    Performance: Searches preloaded in-memory cache (~1-5ms response time).
    Falls back to database if cache is not available.
    """
    # Try cache first (fast path - should be instant)
    cache_loaded = await AirportCacheService.is_cache_loaded()
    
    if cache_loaded:
        # Search from cache - instant!
        results = await AirportCacheService.search_airports(q, limit, group_by_city=False)
        return AirportSearchResponse(
            query=q,
            results=[AirportResponse(**r) for r in results],
            total=len(results)
        )
    
    # Fallback to database (slow path - only if cache not loaded)
    logger.warning("Airport cache not loaded, falling back to database query")
    return await _search_airports_from_db(q, limit, db)


@router.get("/search/grouped", response_model=GroupedAirportSearchResponse)
async def search_airports_grouped(
    q: str = Query(..., min_length=2, max_length=50, description="Search query (city, airport name, or code)"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Search airports with results grouped by city.
    
    For cities with multiple airports (London, New York, Paris, etc.), 
    returns a city group that allows searching from all airports at once.
    
    Response types:
    - type: "city" - Multi-airport city with list of airports and all codes
    - type: "airport" - Single airport
    
    Example response for "london":
    ```json
    {
      "type": "city",
      "city": "London",
      "country": "United Kingdom",
      "airport_count": 5,
      "airports": [{"iata_code": "LHR", ...}, {"iata_code": "LGW", ...}, ...],
      "codes": ["LHR", "LGW", "STN", "LTN", "LCY"],
      "display": "London (All 5 airports)"
    }
    ```
    """
    cache_loaded = await AirportCacheService.is_cache_loaded()
    
    if cache_loaded:
        results = await AirportCacheService.search_airports(q, limit, group_by_city=True)
        return GroupedAirportSearchResponse(
            query=q,
            results=results,
            total=len(results)
        )
    
    # Fallback - just return ungrouped results
    logger.warning("Airport cache not loaded, returning ungrouped results")
    flat_results = await _search_airports_from_db(q, limit, db)
    return GroupedAirportSearchResponse(
        query=q,
        results=[{"type": "airport", **r.model_dump()} for r in flat_results.results],
        total=flat_results.total
    )


async def _search_airports_from_db(
    q: str, 
    limit: int, 
    db: AsyncSession
) -> AirportSearchResponse:
    """Fallback database search when cache is not available"""
    query_upper = q.upper().strip()
    
    airports = []
    existing_codes = set()
    
    # Exact code match
    if len(query_upper) <= 3 and query_upper.isalpha():
        exact_stmt = select(Airport).where(
            Airport.is_active == True,
            Airport.iata_code == query_upper
        )
        exact_result = await db.execute(exact_stmt)
        exact_match = exact_result.scalar_one_or_none()
        if exact_match:
            airports.append(exact_match)
            existing_codes.add(exact_match.iata_code)
    
    # Prefix/contains search
    if len(airports) < limit:
        stmt = (
            select(Airport)
            .where(
                Airport.is_active == True,
                or_(
                    Airport.iata_code.ilike(f"{query_upper}%"),
                    Airport.city.ilike(f"{q}%"),
                    Airport.name.ilike(f"%{q}%"),
                )
            )
            .order_by(Airport.is_major.desc(), Airport.city)
            .limit(limit + 10)
        )
        result = await db.execute(stmt)
        for airport in result.scalars().all():
            if airport.iata_code not in existing_codes and len(airports) < limit:
                airports.append(airport)
                existing_codes.add(airport.iata_code)
    
    return AirportSearchResponse(
        query=q,
        results=[AirportResponse.model_validate(a) for a in airports],
        total=len(airports)
    )


@router.get("/popular/", response_model=List[AirportResponse])
async def get_popular_airports(
    country_code: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get popular/major airports, optionally filtered by country.
    Uses cached data for instant response.
    """
    # Try cache first
    cache_loaded = await AirportCacheService.is_cache_loaded()
    
    if cache_loaded:
        results = await AirportCacheService.get_popular_airports(country_code, limit)
        return [AirportResponse(**r) for r in results]
    
    # Fallback to database
    stmt = (
        select(Airport)
        .where(
            Airport.is_active == True,
            Airport.is_major == True
        )
    )
    
    if country_code:
        stmt = stmt.where(Airport.country_code == country_code.upper())
    
    stmt = stmt.order_by(Airport.city).limit(limit)
    
    result = await db.execute(stmt)
    airports = result.scalars().all()
    
    return [AirportResponse.model_validate(a) for a in airports]


@router.get("/{code}", response_model=AirportResponse)
async def get_airport(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get airport details by IATA code.
    Uses cached data for instant response.
    """
    # Try cache first
    cached = await AirportCacheService.get_airport_by_code(code)
    if cached:
        return AirportResponse(**cached)
    
    # Fallback to database
    stmt = select(Airport).where(Airport.iata_code == code.upper())
    result = await db.execute(stmt)
    airport = result.scalar_one_or_none()
    
    if not airport:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Airport with code '{code}' not found"
        )
    
    return AirportResponse.model_validate(airport)


@router.get("/city/{city_name}", response_model=List[AirportResponse])
async def get_airports_by_city(
    city_name: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all airports in a city.
    Useful for cities with multiple airports (London, New York, etc.)
    """
    # Try cache search
    cache_loaded = await AirportCacheService.is_cache_loaded()
    
    if cache_loaded:
        results = await AirportCacheService.search_airports(city_name, limit=20)
        # Filter to only exact city matches
        city_lower = city_name.lower()
        filtered = [r for r in results if city_lower in r["city"].lower()]
        return [AirportResponse(**r) for r in filtered]
    
    # Fallback to database
    stmt = (
        select(Airport)
        .where(
            Airport.is_active == True,
            Airport.city.ilike(f"%{city_name}%")
        )
        .order_by(Airport.is_major.desc(), Airport.name)
    )
    
    result = await db.execute(stmt)
    airports = result.scalars().all()
    
    return [AirportResponse.model_validate(a) for a in airports]


@router.post("/cache/reload")
async def reload_airport_cache(
    db: AsyncSession = Depends(get_db),
):
    """
    Admin endpoint to reload the airport cache from database.
    Useful after adding new airports or making changes.
    """
    count = await AirportCacheService.load_airports_to_cache(db)
    return {
        "status": "success",
        "message": f"Loaded {count} airports into cache",
        "airports_loaded": count
    }

