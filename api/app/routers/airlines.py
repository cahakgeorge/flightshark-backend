"""
Airlines API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import logging

from app.utils.database import get_db
from app.utils.redis import get_redis
from app.models.airline import Airline, Route
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class AirlineResponse(BaseModel):
    """Airline response schema"""
    iata_code: str
    name: str
    country: Optional[str] = None
    country_code: Optional[str] = None
    logo_url: Optional[str] = None
    alliance: Optional[str] = None
    is_low_cost: bool = False
    rating: Optional[float] = None
    
    class Config:
        from_attributes = True


class RouteResponse(BaseModel):
    """Route response schema"""
    origin_code: str
    destination_code: str
    airline_code: Optional[str] = None
    is_direct: bool = True
    typical_duration_minutes: Optional[int] = None
    distance_km: Optional[int] = None
    typical_price_low: Optional[float] = None
    typical_price_high: Optional[float] = None
    
    class Config:
        from_attributes = True


@router.get("/", response_model=List[AirlineResponse])
async def list_airlines(
    country_code: Optional[str] = None,
    low_cost_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    List all airlines, optionally filtered by country or type.
    """
    stmt = select(Airline).where(Airline.is_active == True)
    
    if country_code:
        stmt = stmt.where(Airline.country_code == country_code.upper())
    
    if low_cost_only:
        stmt = stmt.where(Airline.is_low_cost == True)
    
    stmt = stmt.order_by(Airline.name).limit(limit)
    
    result = await db.execute(stmt)
    airlines = result.scalars().all()
    
    return [AirlineResponse.model_validate(a) for a in airlines]


@router.get("/{code}", response_model=AirlineResponse)
async def get_airline(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get airline details by IATA code.
    """
    stmt = select(Airline).where(Airline.iata_code == code.upper())
    result = await db.execute(stmt)
    airline = result.scalar_one_or_none()
    
    if not airline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Airline with code '{code}' not found"
        )
    
    return AirlineResponse.model_validate(airline)


@router.get("/{code}/routes", response_model=List[RouteResponse])
async def get_airline_routes(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all routes operated by an airline.
    """
    stmt = (
        select(Route)
        .where(
            Route.airline_code == code.upper(),
            Route.is_active == True
        )
        .order_by(Route.origin_code, Route.destination_code)
    )
    
    result = await db.execute(stmt)
    routes = result.scalars().all()
    
    return [RouteResponse.model_validate(r) for r in routes]


@router.get("/routes/search")
async def search_routes(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all airlines operating a specific route.
    """
    stmt = (
        select(Route)
        .where(
            Route.origin_code == origin.upper(),
            Route.destination_code == destination.upper(),
            Route.is_active == True
        )
    )
    
    result = await db.execute(stmt)
    routes = result.scalars().all()
    
    return {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "routes": [RouteResponse.model_validate(r) for r in routes],
        "airlines_count": len(routes)
    }

