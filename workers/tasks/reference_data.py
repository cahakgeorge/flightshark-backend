"""
Reference Data Tasks - Scheduled updates for airport destinations and routes
"""
import asyncio
import logging
from datetime import datetime
from celery import shared_task
import httpx

logger = logging.getLogger(__name__)

# API base URL for triggering seeding
API_BASE_URL = "http://api:8000"


@shared_task(name="tasks.reference_data.seed_airport_destinations")
def seed_airport_destinations(airport_code: str):
    """
    Celery task to seed destinations for a specific airport
    Triggers the API endpoint which handles the actual work
    """
    logger.info(f"Starting seed task for airport: {airport_code}")
    
    try:
        response = httpx.post(
            f"{API_BASE_URL}/admin/data/seed/airport-destinations/{airport_code}",
            timeout=60.0
        )
        response.raise_for_status()
        result = response.json()
        logger.info(f"Seed task started for {airport_code}: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to seed airport {airport_code}: {e}")
        raise


@shared_task(name="tasks.reference_data.seed_all_major_airports")
def seed_all_major_airports():
    """
    Celery task to seed destinations for all major airports
    Run this periodically (e.g., weekly) to keep data fresh
    """
    logger.info("Starting seed task for all major airports")
    
    try:
        response = httpx.post(
            f"{API_BASE_URL}/admin/data/seed/all-major-airports",
            timeout=60.0
        )
        response.raise_for_status()
        result = response.json()
        logger.info(f"Seed all major airports task started: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to seed all major airports: {e}")
        raise


@shared_task(name="tasks.reference_data.update_popular_routes")
def update_popular_routes(
    origins: list = None,
    destinations: list = None
):
    """
    Celery task to update popular routes with fresh pricing
    Run this daily to keep prices current
    """
    origins = origins or ["DUB", "LHR", "CDG", "AMS", "BCN", "FCO", "BER", "MAD"]
    destinations = destinations or ["BCN", "LIS", "AMS", "FCO", "PRG", "CDG", "BER", "VIE", "ATH", "DUB"]
    
    logger.info(f"Starting popular routes update: {len(origins)} origins x {len(destinations)} destinations")
    
    try:
        response = httpx.post(
            f"{API_BASE_URL}/admin/data/seed/popular-routes",
            params={
                "origins": origins,
                "destinations": destinations
            },
            timeout=60.0
        )
        response.raise_for_status()
        result = response.json()
        logger.info(f"Popular routes update started: {result}")
        return result
    except Exception as e:
        logger.error(f"Failed to update popular routes: {e}")
        raise


@shared_task(name="tasks.reference_data.refresh_stale_routes")
def refresh_stale_routes(max_age_days: int = 7):
    """
    Find and refresh routes that haven't been updated recently
    """
    logger.info(f"Finding routes older than {max_age_days} days to refresh")
    
    # This would query the database for stale routes and trigger updates
    # For now, just log and return
    
    # TODO: Implement database query to find stale routes
    # and trigger seed_popular_route for each
    
    return {"status": "not_implemented_yet"}


# ==================
# SCHEDULED TASKS
# ==================
# These are registered in celery_app.py beat_schedule

"""
Example schedule configuration in celery_app.py:

app.conf.beat_schedule = {
    # Update popular routes daily at 3 AM
    'update-popular-routes-daily': {
        'task': 'tasks.reference_data.update_popular_routes',
        'schedule': crontab(hour=3, minute=0),
    },
    
    # Refresh all major airport destinations weekly (Sunday 2 AM)
    'seed-major-airports-weekly': {
        'task': 'tasks.reference_data.seed_all_major_airports',
        'schedule': crontab(hour=2, minute=0, day_of_week=0),
    },
    
    # Refresh stale routes daily at 4 AM
    'refresh-stale-routes': {
        'task': 'tasks.reference_data.refresh_stale_routes',
        'schedule': crontab(hour=4, minute=0),
    },
}
"""
