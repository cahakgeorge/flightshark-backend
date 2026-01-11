"""
Airport Search & Autocomplete Endpoints
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List, Optional
import logging

from app.utils.database import get_db
from app.utils.redis import get_redis
from app.models.airport import Airport, City
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
    """Search results response"""
    query: str
    results: List[AirportResponse]
    total: int


@router.get("/search", response_model=AirportSearchResponse)
async def search_airports(
    q: str = Query(..., min_length=2, max_length=50, description="Search query (city, airport name, or code)"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Search airports by city name, airport name, or IATA code.
    Used for autocomplete in the search form.
    """
    query_upper = q.upper()
    query_lower = q.lower()
    
    # Check cache
    cache_key = f"airport_search:{query_lower}:{limit}"
    cached = await cache.get(cache_key)
    if cached:
        import json
        return AirportSearchResponse(**json.loads(cached))
    
    # Search in database
    stmt = (
        select(Airport)
        .where(
            Airport.is_active == True,
            or_(
                Airport.iata_code.ilike(f"{query_upper}%"),
                Airport.city.ilike(f"%{q}%"),
                Airport.name.ilike(f"%{q}%"),
                Airport.country.ilike(f"%{q}%"),
            )
        )
        .order_by(
            # Prioritize: 1) exact code match, 2) code starts with, 3) city starts with, 4) major airports
            (Airport.iata_code == query_upper).desc(),  # Exact code match first
            (Airport.iata_code.ilike(f"{query_upper}%")).desc(),  # Code starts with query
            (Airport.city.ilike(f"{q}%")).desc(),  # City starts with query
            Airport.is_major.desc(),
            Airport.city
        )
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    airports = result.scalars().all()
    
    response = AirportSearchResponse(
        query=q,
        results=[AirportResponse.model_validate(a) for a in airports],
        total=len(airports)
    )
    
    # Cache for 1 hour
    import json
    await cache.setex(cache_key, 3600, json.dumps(response.model_dump()))
    
    return response


@router.get("/{code}", response_model=AirportResponse)
async def get_airport(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get airport details by IATA code.
    """
    stmt = select(Airport).where(Airport.iata_code == code.upper())
    result = await db.execute(stmt)
    airport = result.scalar_one_or_none()
    
    if not airport:
        from fastapi import HTTPException, status
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


@router.get("/popular/", response_model=List[AirportResponse])
async def get_popular_airports(
    country_code: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get popular/major airports, optionally filtered by country.
    """
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

