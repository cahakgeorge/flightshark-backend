"""
Trip Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import date, datetime
from uuid import UUID


class TripCreate(BaseModel):
    """Schema for creating a trip"""
    name: str = Field(..., min_length=1, max_length=255)
    destination_code: str = Field(..., min_length=3, max_length=3)
    departure_date: Optional[date] = None
    return_date: Optional[date] = None


class TripMemberAdd(BaseModel):
    """Schema for adding a trip member"""
    user_id: Optional[UUID] = None  # If inviting existing user
    origin_city: str = Field(..., max_length=100)
    origin_airport_code: Optional[str] = Field(None, min_length=3, max_length=3)


class TripMemberResponse(BaseModel):
    """Schema for trip member response"""
    id: UUID
    user_id: Optional[UUID]
    origin_city: Optional[str]
    origin_airport_code: Optional[str]
    role: str
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class TripResponse(BaseModel):
    """Schema for trip response"""
    id: UUID
    owner_id: UUID
    name: str
    destination_code: str
    status: str
    departure_date: Optional[date]
    return_date: Optional[date]
    created_at: datetime
    members: List[TripMemberResponse] = []
    
    class Config:
        from_attributes = True


class GroupTripSearchRequest(BaseModel):
    """Schema for group trip search"""
    trip_id: UUID


class MemberFlightResult(BaseModel):
    """Flight result for a single member"""
    origin: str
    destination: str
    cheapest_price: Optional[float]
    cheapest_flight: Optional[Any] = None
    error: Optional[str] = None


class GroupTripSearchResponse(BaseModel):
    """Schema for group trip search response"""
    trip_id: str
    destination: str
    departure_date: Optional[date]
    return_date: Optional[date]
    member_flights: List[MemberFlightResult]
    total_group_price: float
    member_count: int

