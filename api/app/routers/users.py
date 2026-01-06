"""
User Profile & Preferences Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from app.utils.database import get_db
from app.routers.auth import get_current_user
from app.models.user import User
from app.models.price_alert import PriceAlert
from app.schemas.user import UserResponse, UserUpdate, PriceAlertResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/me", response_model=UserResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    """
    Get current user profile
    """
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_profile(
    updates: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update current user profile
    """
    update_data = updates.model_dump(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(current_user, field, value)
    
    await db.commit()
    await db.refresh(current_user)
    
    logger.info(f"User profile updated: {current_user.id}")
    
    return current_user


@router.get("/me/alerts", response_model=List[PriceAlertResponse])
async def get_price_alerts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get user's price alerts
    """
    result = await db.execute(
        select(PriceAlert)
        .where(PriceAlert.user_id == current_user.id)
        .order_by(PriceAlert.created_at.desc())
    )
    alerts = result.scalars().all()
    
    return alerts


@router.delete("/me/alerts/{alert_id}")
async def delete_price_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a price alert
    """
    result = await db.execute(
        select(PriceAlert).where(
            PriceAlert.id == alert_id,
            PriceAlert.user_id == current_user.id
        )
    )
    alert = result.scalar_one_or_none()
    
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    await db.delete(alert)
    await db.commit()
    
    return {"message": "Alert deleted successfully"}


@router.get("/me/recommendations")
async def get_recommendations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get personalized destination recommendations based on user preferences
    """
    from app.models.destination import Destination
    
    # Get user preferences
    preferences = current_user.preferences or {}
    preferred_tags = preferences.get("tags", [])
    
    # Build query
    query = select(Destination)
    
    if preferred_tags:
        query = query.where(Destination.tags.overlap(preferred_tags))
    
    # Order by average price (cheapest first from user's home)
    query = query.order_by(Destination.average_price.asc()).limit(10)
    
    result = await db.execute(query)
    destinations = result.scalars().all()
    
    return {
        "user_home": current_user.home_city,
        "recommendations": [
            {
                "code": d.airport_code,
                "city": d.city,
                "country": d.country,
                "tags": d.tags,
                "average_price": float(d.average_price) if d.average_price else None,
                "image_url": d.image_url,
                "reason": f"Great for {', '.join(set(d.tags) & set(preferred_tags))}" if preferred_tags else "Popular destination"
            }
            for d in destinations
        ]
    }

