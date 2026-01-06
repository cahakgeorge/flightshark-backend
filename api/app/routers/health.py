"""
Health Check Endpoints
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import redis.asyncio as redis

from app.utils.database import get_db
from app.utils.redis import get_redis
from app.utils.mongodb import get_mongodb

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "service": "flightshark-api"}


@router.get("/health/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    cache: redis.Redis = Depends(get_redis),
    mongodb = Depends(get_mongodb),
):
    """
    Readiness check - verifies all dependencies are available
    """
    checks = {
        "postgres": False,
        "redis": False,
        "mongodb": False,
    }
    
    # Check PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception as e:
        checks["postgres_error"] = str(e)
    
    # Check Redis
    try:
        await cache.ping()
        checks["redis"] = True
    except Exception as e:
        checks["redis_error"] = str(e)
    
    # Check MongoDB
    try:
        await mongodb.command("ping")
        checks["mongodb"] = True
    except Exception as e:
        checks["mongodb_error"] = str(e)
    
    # Overall status
    all_healthy = all([checks["postgres"], checks["redis"], checks["mongodb"]])
    
    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks
    }


@router.get("/health/live")
async def liveness_check():
    """Liveness check - is the service running"""
    return {"status": "alive"}

