"""
Flight Search & Price Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import date, datetime
import logging

from app.config import settings
from app.utils.database import get_db
from app.utils.redis import get_redis, cached
from app.schemas.flight import (
    FlightSearchRequest, 
    FlightSearchResponse, 
    FlightOffer,
    PriceHistoryResponse,
    PricePoint
)
from app.services.flight_service import FlightService
from app.routers.auth import get_current_user, oauth2_scheme
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/search", response_model=FlightSearchResponse)
async def search_flights(
    origin: str = Query(..., min_length=3, max_length=3, description="Origin airport code (IATA)"),
    destination: str = Query(..., min_length=3, max_length=3, description="Destination airport code (IATA)"),
    departure_date: date = Query(..., description="Departure date (YYYY-MM-DD)"),
    return_date: Optional[date] = Query(None, description="Return date for round trip"),
    passengers: int = Query(1, ge=1, le=9, description="Number of passengers"),
    cabin_class: str = Query("economy", description="Cabin class: economy, premium_economy, business, first"),
    direct_only: bool = Query(False, description="Only show direct flights"),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Search for flights between two airports.
    Results are cached for 5 minutes.
    """
    # Validate dates
    if departure_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Departure date cannot be in the past"
        )
    
    if return_date and return_date < departure_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Return date must be after departure date"
        )
    
    # Create cache key
    cache_key = f"flights:{origin}:{destination}:{departure_date}:{return_date}:{passengers}:{cabin_class}:{direct_only}"
    
    # Check cache
    cached_result = await cache.get(cache_key)
    if cached_result:
        logger.info(f"Cache HIT for flight search: {origin} -> {destination}")
        import json
        return FlightSearchResponse(**json.loads(cached_result))
    
    # Search flights
    logger.info(f"Cache MISS - searching flights: {origin} -> {destination}")
    
    flight_service = FlightService()
    offers = await flight_service.search_flights(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        return_date=return_date,
        passengers=passengers,
        cabin_class=cabin_class,
        direct_only=direct_only,
    )
    
    response = FlightSearchResponse(
        origin=origin.upper(),
        destination=destination.upper(),
        departure_date=departure_date,
        return_date=return_date,
        passengers=passengers,
        offers=offers,
        total_results=len(offers),
        cached=False,
        searched_at=datetime.utcnow(),
    )
    
    # Cache result
    import json
    await cache.setex(
        cache_key,
        settings.CACHE_TTL_FLIGHTS,
        json.dumps(response.model_dump(), default=str)
    )
    
    return response


@router.get("/prices/{origin}/{destination}", response_model=PriceHistoryResponse)
async def get_price_history(
    origin: str,
    destination: str,
    days: int = Query(30, ge=7, le=180, description="Number of days of history"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical price data for a route.
    Useful for showing price trends and best booking times.
    """
    from sqlalchemy import text
    
    query = text("""
        SELECT 
            time_bucket('1 day', time) AS day,
            AVG(price) as avg_price,
            MIN(price) as min_price,
            MAX(price) as max_price,
            COUNT(*) as sample_count
        FROM price_history
        WHERE origin_code = :origin
        AND destination_code = :destination
        AND time > NOW() - INTERVAL ':days days'
        GROUP BY day
        ORDER BY day DESC
    """)
    
    result = await db.execute(
        query, 
        {"origin": origin.upper(), "destination": destination.upper(), "days": days}
    )
    rows = result.fetchall()
    
    price_points = [
        PricePoint(
            date=row.day,
            avg_price=float(row.avg_price),
            min_price=float(row.min_price),
            max_price=float(row.max_price),
            sample_count=row.sample_count
        )
        for row in rows
    ]
    
    return PriceHistoryResponse(
        origin=origin.upper(),
        destination=destination.upper(),
        days=days,
        prices=price_points
    )


@router.get("/cheapest-dates")
async def get_cheapest_dates(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    month: int = Query(..., ge=1, le=12, description="Month to search (1-12)"),
    year: int = Query(..., ge=2024, le=2026),
    cache = Depends(get_redis),
):
    """
    Find the cheapest dates to fly in a given month.
    Great for flexible travelers.
    """
    cache_key = f"cheapest:{origin}:{destination}:{year}-{month:02d}"
    
    # Check cache
    cached_result = await cache.get(cache_key)
    if cached_result:
        import json
        return json.loads(cached_result)
    
    # This would call flight APIs to get prices for the month
    # For now, return mock data structure
    flight_service = FlightService()
    cheapest_dates = await flight_service.get_cheapest_dates(
        origin=origin.upper(),
        destination=destination.upper(),
        year=year,
        month=month
    )
    
    result = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "month": f"{year}-{month:02d}",
        "dates": cheapest_dates,
        "cheapest_date": min(cheapest_dates, key=lambda x: x["price"]) if cheapest_dates else None
    }
    
    # Cache for 1 hour
    import json
    await cache.setex(cache_key, 3600, json.dumps(result))
    
    return result


@router.post("/alerts")
async def create_price_alert(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    target_price: float = Query(..., gt=0, description="Target price in EUR"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a price alert for a route.
    User will be notified when prices drop below target.
    """
    from app.models.price_alert import PriceAlert
    
    alert = PriceAlert(
        user_id=current_user.id,
        origin_code=origin.upper(),
        destination_code=destination.upper(),
        target_price=target_price,
    )
    
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    
    logger.info(f"Price alert created: {origin} -> {destination} @ €{target_price} for user {current_user.id}")
    
    return {
        "id": str(alert.id),
        "origin": alert.origin_code,
        "destination": alert.destination_code,
        "target_price": float(alert.target_price),
        "is_active": alert.is_active,
        "message": "Price alert created successfully"
    }

