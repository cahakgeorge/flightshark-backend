"""
Market Insights API Endpoints
Travel trends, popular destinations, busiest periods
"""
from fastapi import APIRouter, Depends, Query, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List
from datetime import datetime
import logging

from app.utils.database import get_db
from app.utils.redis import get_redis
from app.services.market_insights_service import MarketInsightsService

router = APIRouter()
logger = logging.getLogger(__name__)


# =========================================================================
# PUBLIC ENDPOINTS - Read cached/stored data
# =========================================================================

@router.get("/traveled/{origin}")
async def get_most_traveled(
    origin: str,
    limit: int = Query(20, ge=1, le=100, description="Number of results"),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Get most traveled destinations from an origin city.
    
    Returns destinations ranked by traveler traffic volume.
    Data is refreshed weekly from Amadeus Market Insights API.
    
    **Use cases:**
    - "Most popular destinations from Dublin"
    - Discover page sections
    - Homepage featured destinations
    """
    service = MarketInsightsService(db, cache)
    
    data = await service.get_most_traveled(origin.upper(), limit)
    
    if not data:
        # Return empty list with message, not 404
        return {
            "origin": origin.upper(),
            "period": "yearly",
            "destinations": [],
            "message": "No data available for this origin. Data syncs weekly.",
            "last_updated": None,
        }
    
    return {
        "origin": origin.upper(),
        "period": "yearly",
        "destinations": data,
        "total": len(data),
    }


@router.get("/booked/{origin}")
async def get_most_booked(
    origin: str,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Get most booked destinations from an origin city.
    
    Returns destinations ranked by booking volume (actual purchases).
    This differs from traveled as it shows booking intent, not just traffic.
    
    **Use cases:**
    - "Hottest destinations being booked"
    - Price alert suggestions
    - Deal recommendations
    """
    service = MarketInsightsService(db, cache)
    
    data = await service.get_most_booked(origin.upper(), limit)
    
    return {
        "origin": origin.upper(),
        "period": "yearly",
        "destinations": data,
        "total": len(data),
    }


@router.get("/busiest-periods/{origin}")
async def get_busiest_periods(
    origin: str,
    direction: str = Query("DEPARTING", description="DEPARTING or ARRIVING"),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Get busiest traveling periods for a city.
    
    Shows which months have the highest travel traffic.
    Useful for planning trips during off-peak times.
    
    **Parameters:**
    - `direction`: DEPARTING = people leaving the city, ARRIVING = people coming
    
    **Use cases:**
    - "Best time to avoid crowds"
    - Peak season warnings
    - Price prediction hints
    """
    if direction not in ["DEPARTING", "ARRIVING"]:
        raise HTTPException(400, "Direction must be DEPARTING or ARRIVING")
    
    service = MarketInsightsService(db, cache)
    
    data = await service.get_busiest_periods(origin.upper(), direction)
    
    # Add month names for convenience
    month_names = [
        "", "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December"
    ]
    
    for period in data:
        period["month_name"] = month_names[period["month"]]
    
    return {
        "origin": origin.upper(),
        "direction": direction,
        "periods": data,
        "busiest_month": data[0]["month_name"] if data else None,
        "quietest_month": data[-1]["month_name"] if data else None,
    }


@router.get("/trending")
async def get_trending_destinations(
    origin: str = Query("GLOBAL", description="Origin city code or GLOBAL for worldwide"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Get trending destinations based on combined travel and booking signals.
    
    This is an aggregated view combining:
    - Most traveled destinations (60% weight)
    - Most booked destinations (40% weight)
    
    The `score_change` field shows week-over-week trending direction.
    
    **Use cases:**
    - Homepage "Trending Now" section
    - Discover page featured destinations
    - Recommendation engine input
    """
    service = MarketInsightsService(db, cache)
    
    data = await service.get_trending(origin.upper(), limit)
    
    # Categorize trending direction
    for dest in data:
        if dest["score_change"] > 5:
            dest["trend"] = "hot"
        elif dest["score_change"] > 0:
            dest["trend"] = "rising"
        elif dest["score_change"] < -5:
            dest["trend"] = "cooling"
        else:
            dest["trend"] = "stable"
    
    return {
        "origin": origin.upper(),
        "destinations": data,
        "total": len(data),
        "updated_at": datetime.utcnow().isoformat(),
    }


@router.get("/popular-routes")
async def get_popular_routes(
    origin: str = Query(None, description="Filter by origin"),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Get globally popular routes combining multiple origins.
    
    Aggregates data across all tracked origins to show
    the most popular routes worldwide.
    """
    service = MarketInsightsService(db, cache)
    
    # If origin specified, get trending for that origin
    if origin:
        data = await service.get_trending(origin.upper(), limit)
    else:
        # Global aggregation
        data = await service.get_trending("GLOBAL", limit)
    
    return {
        "routes": [
            {
                "destination_code": d["destination_code"],
                "destination_city": d["destination_city"],
                "destination_country": d["destination_country"],
                "popularity_score": d["trending_score"],
                "trend": "rising" if d["score_change"] > 0 else "stable",
            }
            for d in data
        ],
        "total": len(data),
    }


# =========================================================================
# ADMIN ENDPOINTS - Trigger data syncs
# =========================================================================

@router.post("/sync/traveled")
async def sync_traveled_destinations(
    background_tasks: BackgroundTasks,
    origins: Optional[List[str]] = Query(None, description="Specific origins to sync"),
    period: str = Query(None, description="Period (YYYY or YYYY-MM)"),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    [Admin] Trigger sync of most traveled destinations from Amadeus.
    
    This fetches data from Amadeus Market Insights API and stores it.
    By default, syncs all major origins. Runs in background.
    """
    service = MarketInsightsService(db, cache)
    
    if not service.is_configured:
        raise HTTPException(503, "Amadeus API not configured")
    
    # Run sync in background
    background_tasks.add_task(service.sync_most_traveled, origins, period)
    
    return {
        "status": "started",
        "message": "Sync started in background",
        "origins": origins or service.MAJOR_ORIGINS,
        "period": period or str(datetime.now().year - 1),
    }


@router.post("/sync/booked")
async def sync_booked_destinations(
    background_tasks: BackgroundTasks,
    origins: Optional[List[str]] = Query(None),
    period: str = Query(None),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """[Admin] Trigger sync of most booked destinations."""
    service = MarketInsightsService(db, cache)
    
    if not service.is_configured:
        raise HTTPException(503, "Amadeus API not configured")
    
    background_tasks.add_task(service.sync_most_booked, origins, period)
    
    return {
        "status": "started",
        "message": "Sync started in background",
    }


@router.post("/sync/busiest")
async def sync_busiest_periods(
    background_tasks: BackgroundTasks,
    origins: Optional[List[str]] = Query(None),
    period: str = Query(None),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """[Admin] Trigger sync of busiest traveling periods."""
    service = MarketInsightsService(db, cache)
    
    if not service.is_configured:
        raise HTTPException(503, "Amadeus API not configured")
    
    background_tasks.add_task(service.sync_busiest_periods, origins, period)
    
    return {
        "status": "started",
        "message": "Sync started in background",
    }


@router.post("/sync/trending")
async def calculate_trending(
    background_tasks: BackgroundTasks,
    origin: str = Query("GLOBAL"),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    [Admin] Recalculate trending destinations.
    
    Aggregates traveled and booked data to compute trending scores.
    """
    service = MarketInsightsService(db, cache)
    
    background_tasks.add_task(service.calculate_trending, origin)
    
    return {
        "status": "started",
        "message": "Trending calculation started",
        "origin": origin,
    }


@router.post("/sync/all")
async def sync_all_insights(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    [Admin] Trigger full sync of all market insights.
    
    Syncs: traveled → booked → busiest → trending
    This is what the weekly scheduled task runs.
    """
    service = MarketInsightsService(db, cache)
    
    if not service.is_configured:
        raise HTTPException(503, "Amadeus API not configured")
    
    async def full_sync():
        logger.info("Starting full market insights sync")
        await service.sync_most_traveled()
        await service.sync_most_booked()
        await service.sync_busiest_periods()
        
        # Calculate trending for major origins + global
        await service.calculate_trending("GLOBAL")
        for origin in service.MAJOR_ORIGINS[:10]:  # Top 10 origins
            await service.calculate_trending(origin)
        
        logger.info("Full market insights sync complete")
    
    background_tasks.add_task(full_sync)
    
    return {
        "status": "started",
        "message": "Full sync started in background",
        "syncing": ["traveled", "booked", "busiest", "trending"],
    }


@router.get("/sync/status")
async def get_sync_status(
    limit: int = Query(10),
    db: AsyncSession = Depends(get_db),
):
    """
    Get recent sync operation logs.
    """
    from sqlalchemy import select
    from app.models.market_insights import MarketInsightsSyncLog
    
    result = await db.execute(
        select(MarketInsightsSyncLog)
        .order_by(MarketInsightsSyncLog.started_at.desc())
        .limit(limit)
    )
    logs = result.scalars().all()
    
    return {
        "syncs": [
            {
                "id": str(log.id),
                "sync_type": log.sync_type,
                "origin": log.origin_code,
                "status": log.status,
                "records_fetched": log.records_fetched,
                "records_created": log.records_created,
                "duration_seconds": log.duration_seconds,
                "error": log.error_message,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            }
            for log in logs
        ]
    }
