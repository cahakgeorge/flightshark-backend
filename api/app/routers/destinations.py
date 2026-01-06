"""
Destination Discovery & Information Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import logging

from app.utils.database import get_db
from app.utils.redis import get_redis
from app.utils.mongodb import get_mongodb, get_social_content_collection
from app.models.destination import Destination
from app.schemas.destination import (
    DestinationResponse,
    DestinationListResponse,
    SocialContentResponse
)
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=DestinationListResponse)
async def list_destinations(
    tags: Optional[List[str]] = Query(None, description="Filter by tags (e.g., sunny, adventure)"),
    search: Optional[str] = Query(None, description="Search by city or country name"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    List destinations with optional filtering by tags
    """
    # Build cache key
    cache_key = f"destinations:list:{tags}:{search}:{limit}:{offset}"
    
    # Check cache
    cached = await cache.get(cache_key)
    if cached:
        import json
        return DestinationListResponse(**json.loads(cached))
    
    # Build query
    query = select(Destination)
    
    if tags:
        # Filter by any matching tag
        query = query.where(Destination.tags.overlap(tags))
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (Destination.city.ilike(search_pattern)) |
            (Destination.country.ilike(search_pattern))
        )
    
    # Execute with pagination
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    destinations = result.scalars().all()
    
    # Get total count
    count_query = select(Destination)
    if tags:
        count_query = count_query.where(Destination.tags.overlap(tags))
    if search:
        count_query = count_query.where(
            (Destination.city.ilike(f"%{search}%")) |
            (Destination.country.ilike(f"%{search}%"))
        )
    
    from sqlalchemy import func
    count_result = await db.execute(select(func.count()).select_from(count_query.subquery()))
    total = count_result.scalar()
    
    response = DestinationListResponse(
        destinations=destinations,
        total=total,
        limit=limit,
        offset=offset
    )
    
    # Cache for 1 hour
    import json
    await cache.setex(cache_key, settings.CACHE_TTL_DESTINATIONS, json.dumps(response.model_dump(), default=str))
    
    return response


@router.get("/{code}", response_model=DestinationResponse)
async def get_destination(
    code: str,
    db: AsyncSession = Depends(get_db),
    mongodb = Depends(get_mongodb),
    cache = Depends(get_redis),
):
    """
    Get detailed destination information including social content
    """
    code = code.upper()
    cache_key = f"destination:{code}"
    
    # Check cache
    cached = await cache.get(cache_key)
    if cached:
        import json
        return DestinationResponse(**json.loads(cached))
    
    # Get destination from PostgreSQL
    result = await db.execute(
        select(Destination).where(Destination.airport_code == code)
    )
    destination = result.scalar_one_or_none()
    
    if not destination:
        raise HTTPException(status_code=404, detail="Destination not found")
    
    # Get social content from MongoDB
    social_collection = get_social_content_collection()
    social_cursor = social_collection.find(
        {"destination_code": code}
    ).sort("scraped_at", -1).limit(10)
    
    social_content = await social_cursor.to_list(length=10)
    
    # Build response
    response_data = {
        "id": str(destination.id),
        "city": destination.city,
        "country": destination.country,
        "airport_code": destination.airport_code,
        "description": destination.description,
        "tags": destination.tags,
        "highlights": destination.highlights,
        "best_time_to_visit": destination.best_time_to_visit,
        "average_price": float(destination.average_price) if destination.average_price else None,
        "image_url": destination.image_url,
        "social_content": [
            SocialContentResponse(
                platform=s["platform"],
                url=s["url"],
                thumbnail_url=s.get("thumbnail_url"),
                caption=s.get("caption"),
                creator=s.get("creator"),
                engagement=s.get("engagement", {}),
            )
            for s in social_content
        ]
    }
    
    response = DestinationResponse(**response_data)
    
    # Cache for 1 hour
    import json
    await cache.setex(cache_key, settings.CACHE_TTL_DESTINATIONS, json.dumps(response.model_dump(), default=str))
    
    return response


@router.get("/{code}/social", response_model=List[SocialContentResponse])
async def get_destination_social_content(
    code: str,
    platform: Optional[str] = Query(None, description="Filter by platform: tiktok, twitter, instagram"),
    limit: int = Query(20, ge=1, le=50),
    mongodb = Depends(get_mongodb),
):
    """
    Get social media content for a destination
    """
    code = code.upper()
    social_collection = get_social_content_collection()
    
    query = {"destination_code": code}
    if platform:
        query["platform"] = platform.lower()
    
    cursor = social_collection.find(query).sort("scraped_at", -1).limit(limit)
    content = await cursor.to_list(length=limit)
    
    return [
        SocialContentResponse(
            platform=s["platform"],
            url=s["url"],
            thumbnail_url=s.get("thumbnail_url"),
            caption=s.get("caption"),
            creator=s.get("creator"),
            engagement=s.get("engagement", {}),
        )
        for s in content
    ]


@router.get("/trending/")
async def get_trending_destinations(
    limit: int = Query(10, ge=1, le=20),
    mongodb = Depends(get_mongodb),
    db: AsyncSession = Depends(get_db),
    cache = Depends(get_redis),
):
    """
    Get trending destinations based on social media activity and searches
    """
    cache_key = f"trending:destinations:{limit}"
    
    cached = await cache.get(cache_key)
    if cached:
        import json
        return json.loads(cached)
    
    # Get from MongoDB insights
    insights_collection = mongodb["destination_insights"]
    cursor = insights_collection.find().sort("trending_score", -1).limit(limit)
    insights = await cursor.to_list(length=limit)
    
    # Enrich with destination data
    trending = []
    for insight in insights:
        result = await db.execute(
            select(Destination).where(Destination.airport_code == insight["destination_code"])
        )
        dest = result.scalar_one_or_none()
        
        if dest:
            trending.append({
                "code": dest.airport_code,
                "city": dest.city,
                "country": dest.country,
                "image_url": dest.image_url,
                "trending_score": insight.get("trending_score", 0),
                "top_topics": insight.get("top_topics", []),
            })
    
    # Cache for 30 minutes
    import json
    await cache.setex(cache_key, 1800, json.dumps(trending))
    
    return trending

