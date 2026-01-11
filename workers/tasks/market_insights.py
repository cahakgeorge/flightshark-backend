"""
Market Insights Celery Tasks
Weekly data sync from Amadeus Market Insights API
"""
import asyncio
from datetime import datetime
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


def run_async(coro):
    """Helper to run async code in sync Celery task"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(
    name="market_insights.sync_traveled",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def sync_traveled_destinations(self, origins=None, period=None):
    """
    Sync most traveled destinations from Amadeus.
    
    Schedule: Weekly (Sunday 2 AM)
    """
    logger.info(f"Starting traveled destinations sync. Origins: {origins or 'ALL'}")
    
    async def _sync():
        from app.utils.database import async_session_factory
        from app.utils.redis import redis_client
        from app.services.market_insights_service import MarketInsightsService
        
        async with async_session_factory() as db:
            service = MarketInsightsService(db, redis_client)
            return await service.sync_most_traveled(origins, period)
    
    try:
        stats = run_async(_sync())
        logger.info(f"Traveled sync complete: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Traveled sync failed: {e}")
        raise


@shared_task(
    name="market_insights.sync_booked",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def sync_booked_destinations(self, origins=None, period=None):
    """
    Sync most booked destinations from Amadeus.
    
    Schedule: Weekly (Sunday 2:30 AM)
    """
    logger.info(f"Starting booked destinations sync")
    
    async def _sync():
        from app.utils.database import async_session_factory
        from app.utils.redis import redis_client
        from app.services.market_insights_service import MarketInsightsService
        
        async with async_session_factory() as db:
            service = MarketInsightsService(db, redis_client)
            return await service.sync_most_booked(origins, period)
    
    try:
        stats = run_async(_sync())
        logger.info(f"Booked sync complete: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Booked sync failed: {e}")
        raise


@shared_task(
    name="market_insights.sync_busiest",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
)
def sync_busiest_periods(self, origins=None, period=None):
    """
    Sync busiest traveling periods from Amadeus.
    
    Schedule: Weekly (Sunday 3 AM)
    """
    logger.info(f"Starting busiest periods sync")
    
    async def _sync():
        from app.utils.database import async_session_factory
        from app.utils.redis import redis_client
        from app.services.market_insights_service import MarketInsightsService
        
        async with async_session_factory() as db:
            service = MarketInsightsService(db, redis_client)
            return await service.sync_busiest_periods(origins, period)
    
    try:
        stats = run_async(_sync())
        logger.info(f"Busiest sync complete: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Busiest sync failed: {e}")
        raise


@shared_task(
    name="market_insights.calculate_trending",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def calculate_trending_destinations(self, origin="GLOBAL"):
    """
    Calculate trending destinations from synced data.
    
    Schedule: Weekly (Sunday 4 AM, after data syncs)
    """
    logger.info(f"Calculating trending destinations for {origin}")
    
    async def _calc():
        from app.utils.database import async_session_factory
        from app.utils.redis import redis_client
        from app.services.market_insights_service import MarketInsightsService
        
        async with async_session_factory() as db:
            service = MarketInsightsService(db, redis_client)
            return await service.calculate_trending(origin)
    
    try:
        stats = run_async(_calc())
        logger.info(f"Trending calculation complete: {stats}")
        return stats
    except Exception as e:
        logger.error(f"Trending calculation failed: {e}")
        raise


@shared_task(
    name="market_insights.full_weekly_sync",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def full_weekly_sync(self):
    """
    Full weekly market insights sync.
    
    This is the main scheduled task that:
    1. Syncs most traveled destinations
    2. Syncs most booked destinations
    3. Syncs busiest periods
    4. Calculates trending for global and major origins
    
    Schedule: Every Sunday at 2:00 AM UTC
    """
    logger.info("=" * 50)
    logger.info("Starting FULL weekly market insights sync")
    logger.info(f"Started at: {datetime.utcnow().isoformat()}")
    logger.info("=" * 50)
    
    results = {}
    
    async def _full_sync():
        from app.utils.database import async_session_factory
        from app.utils.redis import redis_client
        from app.services.market_insights_service import MarketInsightsService
        
        async with async_session_factory() as db:
            service = MarketInsightsService(db, redis_client)
            
            # 1. Sync traveled
            logger.info("[1/4] Syncing traveled destinations...")
            results["traveled"] = await service.sync_most_traveled()
            
            # 2. Sync booked
            logger.info("[2/4] Syncing booked destinations...")
            results["booked"] = await service.sync_most_booked()
            
            # 3. Sync busiest periods
            logger.info("[3/4] Syncing busiest periods...")
            results["busiest"] = await service.sync_busiest_periods()
            
            # 4. Calculate trending
            logger.info("[4/4] Calculating trending destinations...")
            
            # Global trending
            results["trending_global"] = await service.calculate_trending("GLOBAL")
            
            # Per-origin trending for major airports
            major_origins = ["DUB", "LHR", "CDG", "AMS", "JFK", "LAX", "SIN", "HKG", "DXB", "SYD"]
            for origin in major_origins:
                try:
                    await service.calculate_trending(origin)
                except Exception as e:
                    logger.warning(f"Failed to calculate trending for {origin}: {e}")
            
            return results
    
    try:
        results = run_async(_full_sync())
        
        logger.info("=" * 50)
        logger.info("Weekly sync COMPLETE")
        logger.info(f"Results: {results}")
        logger.info(f"Completed at: {datetime.utcnow().isoformat()}")
        logger.info("=" * 50)
        
        return {
            "status": "success",
            "results": results,
            "completed_at": datetime.utcnow().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Weekly sync FAILED: {e}")
        raise


@shared_task(name="market_insights.invalidate_cache")
def invalidate_insights_cache(insight_type=None):
    """
    Invalidate cached market insights data.
    
    Use this after manual data updates or to force refresh.
    """
    logger.info(f"Invalidating cache for: {insight_type or 'all'}")
    
    async def _invalidate():
        from app.utils.redis import redis_client
        
        if insight_type:
            pattern = f"insights:{insight_type}:*"
        else:
            pattern = "insights:*"
        
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
            return len(keys)
        return 0
    
    try:
        deleted = run_async(_invalidate())
        logger.info(f"Invalidated {deleted} cache keys")
        return {"deleted_keys": deleted}
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        raise
