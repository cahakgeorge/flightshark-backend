"""
Admin Data Seeding Endpoints
For populating reference data from external APIs
"""
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from typing import List, Optional
from datetime import datetime
import logging

from app.utils.database import get_db
from app.services.reference_data_service import ReferenceDataSeeder, AmadeusReferenceDataService
from app.services.openflights_fetcher import OpenFlightsDataFetcher

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/seed/airport-destinations/{airport_code}")
async def seed_airport_destinations(
    airport_code: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Seed all destinations reachable from an airport.
    This fetches route data from Amadeus and stores it.
    """
    airport_code = airport_code.upper()
    
    # Verify airport exists
    result = await db.execute(
        text("SELECT iata_code, name, city FROM airports WHERE iata_code = :code"),
        {"code": airport_code}
    )
    airport = result.fetchone()
    
    if not airport:
        raise HTTPException(status_code=404, detail=f"Airport {airport_code} not found")
    
    # Run seeding in background
    async def seed_task():
        async with db.begin():
            seeder = ReferenceDataSeeder(db)
            started_at = datetime.utcnow()
            
            try:
                count = await seeder.seed_airport_destinations(airport_code)
                await seeder.update_airport_stats(airport_code)
                await seeder.log_sync(
                    data_type="airport_destinations",
                    source="amadeus",
                    status="success",
                    records_fetched=count,
                    records_created=count,
                    started_at=started_at
                )
            except Exception as e:
                await seeder.log_sync(
                    data_type="airport_destinations",
                    source="amadeus",
                    status="failed",
                    error_message=str(e),
                    started_at=started_at
                )
                raise
    
    background_tasks.add_task(seed_task)
    
    return {
        "status": "started",
        "airport": airport_code,
        "airport_name": airport[1],
        "city": airport[2],
        "message": f"Seeding destinations for {airport_code} in background"
    }


@router.post("/seed/popular-routes")
async def seed_popular_routes(
    origins: List[str] = Query(
        default=["DUB", "LHR", "CDG", "AMS", "BCN"],
        description="Origin airports to seed routes from"
    ),
    destinations: List[str] = Query(
        default=["BCN", "LIS", "AMS", "FCO", "PRG", "CDG", "BER", "VIE"],
        description="Destination airports to check"
    ),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Seed popular routes with pricing data.
    This searches flights and aggregates pricing info.
    """
    routes_to_seed = []
    for origin in origins:
        for dest in destinations:
            if origin.upper() != dest.upper():
                routes_to_seed.append((origin.upper(), dest.upper()))
    
    # Run in background
    async def seed_task():
        seeder = ReferenceDataSeeder(db)
        started_at = datetime.utcnow()
        success_count = 0
        
        for origin, dest in routes_to_seed:
            try:
                await seeder.seed_popular_route(origin, dest)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to seed {origin}-{dest}: {e}")
        
        await seeder.log_sync(
            data_type="popular_routes",
            source="amadeus",
            status="success" if success_count > 0 else "failed",
            records_fetched=len(routes_to_seed),
            records_created=success_count,
            started_at=started_at
        )
    
    if background_tasks:
        background_tasks.add_task(seed_task)
        return {
            "status": "started",
            "routes_count": len(routes_to_seed),
            "message": f"Seeding {len(routes_to_seed)} routes in background"
        }
    else:
        await seed_task()
        return {"status": "completed", "routes_count": len(routes_to_seed)}


@router.post("/seed/all-major-airports")
async def seed_all_major_airports(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Seed destinations for all major airports.
    This is a long-running operation.
    """
    # Get all major airports
    result = await db.execute(
        text("SELECT iata_code FROM airports WHERE is_major = TRUE AND is_active = TRUE")
    )
    airports = [row[0] for row in result.fetchall()]
    
    if not airports:
        raise HTTPException(status_code=404, detail="No major airports found")
    
    async def seed_task():
        seeder = ReferenceDataSeeder(db)
        started_at = datetime.utcnow()
        total_routes = 0
        
        for airport_code in airports:
            try:
                count = await seeder.seed_airport_destinations(airport_code)
                await seeder.update_airport_stats(airport_code)
                total_routes += count
                logger.info(f"Seeded {count} destinations for {airport_code}")
            except Exception as e:
                logger.error(f"Failed to seed {airport_code}: {e}")
        
        await seeder.log_sync(
            data_type="all_major_airports",
            source="amadeus",
            status="success",
            records_fetched=len(airports),
            records_created=total_routes,
            started_at=started_at
        )
    
    background_tasks.add_task(seed_task)
    
    return {
        "status": "started",
        "airports_count": len(airports),
        "airports": airports,
        "message": f"Seeding destinations for {len(airports)} major airports"
    }


@router.get("/sync-status")
async def get_sync_status(
    data_type: Optional[str] = None,
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get recent data sync operations"""
    query = """
        SELECT 
            id, data_type, source, status,
            records_fetched, records_created, records_updated,
            error_message, started_at, completed_at, duration_seconds
        FROM data_sync_log
    """
    params = {"limit": limit}
    
    if data_type:
        query += " WHERE data_type = :type"
        params["type"] = data_type
    
    query += " ORDER BY created_at DESC LIMIT :limit"
    
    result = await db.execute(text(query), params)
    rows = result.fetchall()
    
    return {
        "sync_operations": [
            {
                "id": str(row[0]),
                "data_type": row[1],
                "source": row[2],
                "status": row[3],
                "records_fetched": row[4],
                "records_created": row[5],
                "records_updated": row[6],
                "error_message": row[7],
                "started_at": row[8].isoformat() if row[8] else None,
                "completed_at": row[9].isoformat() if row[9] else None,
                "duration_seconds": row[10]
            }
            for row in rows
        ]
    }


@router.get("/airport-destinations/{airport_code}")
async def get_airport_destinations(
    airport_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all seeded destinations from an airport"""
    airport_code = airport_code.upper()
    
    result = await db.execute(text("""
        SELECT 
            destination_code, destination_city, destination_country,
            destination_country_code, airlines_serving, airline_count, is_direct,
            price_low, price_avg, flight_duration_minutes,
            popularity_score, updated_at
        FROM airport_destinations
        WHERE airport_code = :code AND is_active = TRUE
        ORDER BY popularity_score DESC NULLS LAST, destination_city
    """), {"code": airport_code})
    
    rows = result.fetchall()
    
    return {
        "airport": airport_code,
        "destinations_count": len(rows),
        "destinations": [
            {
                "code": row[0],
                "city": row[1],
                "country": row[2],
                "country_code": row[3] or "",
                "airlines": row[4] or [],
                "airline_count": row[5],
                "is_direct": row[6],
                "price_low": float(row[7]) if row[7] else None,
                "price_avg": float(row[8]) if row[8] else None,
                "duration_minutes": row[9],
                "popularity_score": row[10],
                "updated_at": row[11].isoformat() if row[11] else None
            }
            for row in rows
        ]
    }


@router.post("/seed/openflights")
async def seed_from_openflights(
    include_airports: bool = Query(True, description="Seed airports data"),
    include_airlines: bool = Query(True, description="Seed airlines data"),
    include_routes: bool = Query(True, description="Seed routes data"),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Seed airports, airlines, and routes from OpenFlights.org open data.
    This is the recommended way to bulk-seed reference data without API limits.
    
    OpenFlights provides:
    - ~7,000 airports worldwide
    - ~6,000 airlines
    - ~67,000 routes
    """
    async def seed_task():
        fetcher = OpenFlightsDataFetcher(db)
        started_at = datetime.utcnow()
        results = {}
        
        try:
            if include_airports:
                results["airports"] = await fetcher.fetch_and_seed_airports()
            
            if include_airlines:
                results["airlines"] = await fetcher.fetch_and_seed_airlines()
            
            if include_routes:
                results["routes"] = await fetcher.fetch_and_seed_routes()
                await fetcher.update_destination_cities()
            
            # Log sync
            seeder = ReferenceDataSeeder(db)
            total_created = sum(r.get("created", 0) for r in results.values())
            await seeder.log_sync(
                data_type="openflights_bulk",
                source="openflights",
                status="success",
                records_fetched=sum(r.get("fetched", 0) for r in results.values()),
                records_created=total_created,
                started_at=started_at
            )
            
            return results
            
        except Exception as e:
            logger.error(f"OpenFlights seeding failed: {e}")
            seeder = ReferenceDataSeeder(db)
            await seeder.log_sync(
                data_type="openflights_bulk",
                source="openflights",
                status="failed",
                error_message=str(e),
                started_at=started_at
            )
            raise
    
    if background_tasks:
        background_tasks.add_task(seed_task)
        return {
            "status": "started",
            "message": "OpenFlights data seeding started in background",
            "seeding": {
                "airports": include_airports,
                "airlines": include_airlines,
                "routes": include_routes
            }
        }
    else:
        results = await seed_task()
        return {
            "status": "completed",
            "results": results
        }


@router.get("/popular-routes")
async def get_popular_routes(
    origin: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Get seeded popular routes"""
    query = """
        SELECT 
            origin_code, destination_code,
            origin_city, destination_city,
            airlines, airline_count,
            cheapest_airline, cheapest_price,
            avg_price, has_direct_flights,
            avg_duration_minutes, last_price_check
        FROM popular_routes
        WHERE is_active = TRUE
    """
    params = {"limit": limit}
    
    if origin:
        query += " AND origin_code = :origin"
        params["origin"] = origin.upper()
    
    query += " ORDER BY cheapest_price ASC NULLS LAST LIMIT :limit"
    
    result = await db.execute(text(query), params)
    rows = result.fetchall()
    
    return {
        "routes_count": len(rows),
        "routes": [
            {
                "origin": row[0],
                "destination": row[1],
                "origin_city": row[2],
                "destination_city": row[3],
                "airlines": row[4],
                "airline_count": row[5],
                "cheapest_airline": row[6],
                "cheapest_price": float(row[7]) if row[7] else None,
                "avg_price": float(row[8]) if row[8] else None,
                "has_direct": row[9],
                "duration_minutes": row[10],
                "last_updated": row[11].isoformat() if row[11] else None
            }
            for row in rows
        ]
    }
