"""
Trip & Group Trip Planning Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import date
import logging

from app.utils.database import get_db
from app.routers.auth import get_current_user
from app.models.user import User
from app.models.trip import Trip, TripMember
from app.schemas.trip import (
    TripCreate, 
    TripResponse, 
    TripMemberAdd,
    TripMemberResponse,
    GroupTripSearchRequest,
    GroupTripSearchResponse
)
from app.services.flight_service import FlightService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create_trip(
    trip_data: TripCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new trip
    """
    trip = Trip(
        owner_id=current_user.id,
        name=trip_data.name,
        destination_code=trip_data.destination_code.upper(),
        departure_date=trip_data.departure_date,
        return_date=trip_data.return_date,
    )
    
    # Add owner as first member
    owner_member = TripMember(
        trip=trip,
        user_id=current_user.id,
        origin_city=current_user.home_city,
        origin_airport_code=current_user.home_airport_code,
        role="owner",
        status="confirmed",
    )
    
    db.add(trip)
    db.add(owner_member)
    await db.commit()
    await db.refresh(trip)
    
    logger.info(f"Trip created: {trip.id} by user {current_user.id}")
    
    return trip


@router.get("", response_model=List[TripResponse])
async def list_trips(
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all trips for current user (owned or member of)
    """
    query = (
        select(Trip)
        .join(TripMember)
        .where(TripMember.user_id == current_user.id)
        .options(selectinload(Trip.members))
    )
    
    if status:
        query = query.where(Trip.status == status)
    
    result = await db.execute(query)
    trips = result.scalars().unique().all()
    
    return trips


@router.get("/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get trip details
    """
    query = (
        select(Trip)
        .where(Trip.id == trip_id)
        .options(selectinload(Trip.members))
    )
    
    result = await db.execute(query)
    trip = result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trip not found"
        )
    
    # Check if user is member
    is_member = any(m.user_id == current_user.id for m in trip.members)
    if not is_member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this trip"
        )
    
    return trip


@router.post("/{trip_id}/members", response_model=TripMemberResponse)
async def add_trip_member(
    trip_id: str,
    member_data: TripMemberAdd,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Add a member to a trip (invite by email or add origin city)
    """
    # Get trip
    result = await db.execute(select(Trip).where(Trip.id == trip_id))
    trip = result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Only owner can add members
    if trip.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only trip owner can add members")
    
    # Check max members (5)
    result = await db.execute(
        select(TripMember).where(TripMember.trip_id == trip_id)
    )
    existing_members = result.scalars().all()
    
    if len(existing_members) >= 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 5 members per trip"
        )
    
    # Create member (either with user_id or just origin info for invites)
    member = TripMember(
        trip_id=trip_id,
        user_id=member_data.user_id,
        origin_city=member_data.origin_city,
        origin_airport_code=member_data.origin_airport_code.upper() if member_data.origin_airport_code else None,
        role="member",
        status="pending" if member_data.user_id else "placeholder",
    )
    
    db.add(member)
    await db.commit()
    await db.refresh(member)
    
    logger.info(f"Member added to trip {trip_id}")
    
    return member


@router.delete("/{trip_id}/members/{member_id}")
async def remove_trip_member(
    trip_id: str,
    member_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Remove a member from a trip
    """
    # Get trip
    result = await db.execute(select(Trip).where(Trip.id == trip_id))
    trip = result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Only owner can remove members
    if trip.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only trip owner can remove members")
    
    # Get member
    result = await db.execute(
        select(TripMember).where(
            TripMember.id == member_id,
            TripMember.trip_id == trip_id
        )
    )
    member = result.scalar_one_or_none()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Can't remove owner
    if member.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove trip owner")
    
    await db.delete(member)
    await db.commit()
    
    return {"message": "Member removed successfully"}


@router.post("/{trip_id}/search", response_model=GroupTripSearchResponse)
async def search_group_flights(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Search for the best flights for all group members.
    Finds dates/flights where the total cost is minimized.
    """
    # Get trip with members
    query = (
        select(Trip)
        .where(Trip.id == trip_id)
        .options(selectinload(Trip.members))
    )
    result = await db.execute(query)
    trip = result.scalar_one_or_none()
    
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    
    # Get all origin airports
    origins = [
        m.origin_airport_code 
        for m in trip.members 
        if m.origin_airport_code
    ]
    
    if not origins:
        raise HTTPException(
            status_code=400,
            detail="No origin airports set for trip members"
        )
    
    # Search flights for each origin to destination
    flight_service = FlightService()
    
    group_results = []
    total_min_price = 0
    
    for origin in origins:
        offers = await flight_service.search_flights(
            origin=origin,
            destination=trip.destination_code,
            departure_date=trip.departure_date,
            return_date=trip.return_date,
            passengers=1,
        )
        
        if offers:
            cheapest = min(offers, key=lambda x: x.price)
            group_results.append({
                "origin": origin,
                "destination": trip.destination_code,
                "cheapest_price": cheapest.price,
                "cheapest_flight": cheapest,
            })
            total_min_price += cheapest.price
        else:
            group_results.append({
                "origin": origin,
                "destination": trip.destination_code,
                "cheapest_price": None,
                "error": "No flights found"
            })
    
    return GroupTripSearchResponse(
        trip_id=trip_id,
        destination=trip.destination_code,
        departure_date=trip.departure_date,
        return_date=trip.return_date,
        member_flights=group_results,
        total_group_price=total_min_price,
        member_count=len(origins)
    )

