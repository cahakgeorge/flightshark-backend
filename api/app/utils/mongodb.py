"""
MongoDB Connection for Scraped Content & Flexible Data
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# MongoDB client instance
mongo_client: Optional[AsyncIOMotorClient] = None
mongo_db: Optional[AsyncIOMotorDatabase] = None


async def init_mongodb():
    """Initialize MongoDB connection"""
    global mongo_client, mongo_db
    logger.info("Initializing MongoDB connection...")
    
    mongo_client = AsyncIOMotorClient(settings.MONGODB_URL)
    mongo_db = mongo_client[settings.MONGODB_DATABASE]
    
    # Test connection
    await mongo_client.admin.command('ping')
    
    # Create indexes
    await create_indexes()
    
    logger.info("MongoDB connection established")


async def close_mongodb():
    """Close MongoDB connection"""
    global mongo_client
    if mongo_client:
        logger.info("Closing MongoDB connection...")
        mongo_client.close()
        logger.info("MongoDB connection closed")


async def get_mongodb() -> AsyncIOMotorDatabase:
    """
    Dependency that provides MongoDB database
    Usage: db: AsyncIOMotorDatabase = Depends(get_mongodb)
    """
    if mongo_db is None:
        raise RuntimeError("MongoDB client not initialized")
    return mongo_db


async def create_indexes():
    """Create MongoDB indexes for better query performance"""
    
    # Social content collection indexes
    social_content = mongo_db["social_content"]
    await social_content.create_index("destination_code")
    await social_content.create_index("platform")
    await social_content.create_index([("destination_code", 1), ("platform", 1)])
    await social_content.create_index("scraped_at")
    await social_content.create_index(
        "expires_at", 
        expireAfterSeconds=0  # TTL index - auto-delete expired documents
    )
    
    # Flight cache collection indexes
    flight_cache = mongo_db["flight_cache"]
    await flight_cache.create_index("cache_key", unique=True)
    await flight_cache.create_index(
        "expires_at",
        expireAfterSeconds=0
    )
    
    # Destination insights collection indexes
    destination_insights = mongo_db["destination_insights"]
    await destination_insights.create_index("destination_code", unique=True)
    await destination_insights.create_index("trending_score")
    
    logger.info("MongoDB indexes created")


# Collection helpers
def get_social_content_collection():
    """Get social_content collection"""
    return mongo_db["social_content"]


def get_flight_cache_collection():
    """Get flight_cache collection"""
    return mongo_db["flight_cache"]


def get_destination_insights_collection():
    """Get destination_insights collection"""
    return mongo_db["destination_insights"]

