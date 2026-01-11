"""
Destination Schemas
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class SocialContentResponse(BaseModel):
    """Schema for social media content"""
    platform: str  # tiktok, twitter, instagram
    url: str
    thumbnail_url: Optional[str] = None
    caption: Optional[str] = None
    creator: Optional[str] = None
    engagement: Dict[str, Any] = {}


class DestinationBase(BaseModel):
    """Base destination schema"""
    city: str
    country: str
    airport_code: str
    description: Optional[str] = None
    tags: List[str] = []
    highlights: List[str] = []
    best_time_to_visit: Optional[str] = None
    average_price: Optional[float] = None
    image_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class DestinationResponse(DestinationBase):
    """Schema for destination response with social content"""
    id: str
    social_content: List[SocialContentResponse] = []
    
    class Config:
        from_attributes = True


class DestinationListResponse(BaseModel):
    """Schema for paginated destination list"""
    destinations: List[DestinationBase]
    total: int
    limit: int
    offset: int

