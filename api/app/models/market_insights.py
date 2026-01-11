"""
Market Insights Models - Stores travel trends and analytics from Amadeus
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Boolean, JSON, Index, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from datetime import datetime
import uuid

from app.utils.database import Base


class TraveledDestination(Base):
    """
    Most traveled destinations by traffic volume.
    Source: Amadeus Flight Most Traveled Destinations API
    """
    __tablename__ = "traveled_destinations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Origin city/airport this data is for
    origin_code = Column(String(3), nullable=False, index=True)
    
    # Destination details
    destination_code = Column(String(3), nullable=False)
    destination_city = Column(String(255))
    destination_country = Column(String(255))
    destination_country_code = Column(String(2))
    
    # Traffic metrics
    travelers_count = Column(Integer)  # Number of travelers
    flights_count = Column(Integer)  # Number of flights
    analytics_score = Column(Float)  # Amadeus analytics score
    
    # Ranking
    rank = Column(Integer)
    
    # Time period this data covers
    period_type = Column(String(20), default="YEARLY")  # MONTHLY, QUARTERLY, YEARLY
    period_year = Column(Integer)
    period_month = Column(Integer, nullable=True)
    period_quarter = Column(Integer, nullable=True)
    
    # Metadata
    raw_data = Column(JSON)  # Store full API response
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint('origin_code', 'destination_code', 'period_type', 'period_year', 'period_month', 
                         name='uq_traveled_dest_period'),
        Index('ix_traveled_dest_origin_rank', 'origin_code', 'rank'),
    )


class BookedDestination(Base):
    """
    Most booked destinations by booking volume.
    Source: Amadeus Flight Most Booked Destinations API
    """
    __tablename__ = "booked_destinations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Origin city/airport this data is for
    origin_code = Column(String(3), nullable=False, index=True)
    
    # Destination details
    destination_code = Column(String(3), nullable=False)
    destination_city = Column(String(255))
    destination_country = Column(String(255))
    destination_country_code = Column(String(2))
    
    # Booking metrics
    bookings_count = Column(Integer)  # Number of bookings
    analytics_score = Column(Float)  # Amadeus analytics score
    
    # Ranking
    rank = Column(Integer)
    
    # Time period
    period_type = Column(String(20), default="YEARLY")
    period_year = Column(Integer)
    period_month = Column(Integer, nullable=True)
    period_quarter = Column(Integer, nullable=True)
    
    # Metadata
    raw_data = Column(JSON)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint('origin_code', 'destination_code', 'period_type', 'period_year', 'period_month',
                         name='uq_booked_dest_period'),
        Index('ix_booked_dest_origin_rank', 'origin_code', 'rank'),
    )


class BusiestTravelPeriod(Base):
    """
    Busiest traveling periods for a destination.
    Source: Amadeus Flight Busiest Traveling Period API
    """
    __tablename__ = "busiest_travel_periods"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Origin city/airport
    origin_code = Column(String(3), nullable=False, index=True)
    
    # Destination (optional - can be for overall from origin)
    destination_code = Column(String(3), nullable=True)
    
    # Period information
    period_month = Column(Integer, nullable=False)  # 1-12
    period_year = Column(Integer, nullable=False)
    
    # Traffic data
    travelers_count = Column(Integer)
    flights_count = Column(Integer)
    analytics_score = Column(Float)
    
    # Indicates if this is departure or arrival busiest period
    direction = Column(String(20), default="DEPARTING")  # DEPARTING, ARRIVING
    
    # Ranking (1 = busiest)
    rank = Column(Integer)
    
    # Metadata
    raw_data = Column(JSON)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint('origin_code', 'destination_code', 'period_year', 'period_month', 'direction',
                         name='uq_busiest_period'),
        Index('ix_busiest_origin_direction', 'origin_code', 'direction'),
    )


class TrendingDestination(Base):
    """
    Aggregated trending destinations combining multiple signals.
    Updated weekly based on traveled, booked, and search data.
    """
    __tablename__ = "trending_destinations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Origin (can be global with 'GLOBAL' code)
    origin_code = Column(String(10), nullable=False, index=True)
    
    # Destination
    destination_code = Column(String(3), nullable=False)
    destination_city = Column(String(255))
    destination_country = Column(String(255))
    destination_country_code = Column(String(2))
    
    # Composite trending score (0-100)
    trending_score = Column(Float, default=0)
    
    # Component scores
    travel_score = Column(Float, default=0)  # From most traveled
    booking_score = Column(Float, default=0)  # From most booked
    search_score = Column(Float, default=0)  # From internal search analytics
    social_score = Column(Float, default=0)  # From social media mentions
    
    # Week-over-week change
    score_change = Column(Float, default=0)  # Positive = trending up
    
    # Overall rank
    rank = Column(Integer)
    
    # Metadata
    image_url = Column(String(500))
    tags = Column(JSON, default=list)  # ["beach", "city-break", "adventure"]
    
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    valid_until = Column(DateTime(timezone=True))  # When this data expires
    is_active = Column(Boolean, default=True)
    
    __table_args__ = (
        UniqueConstraint('origin_code', 'destination_code', name='uq_trending_dest'),
        Index('ix_trending_rank', 'origin_code', 'rank'),
        Index('ix_trending_score', 'origin_code', 'trending_score'),
    )


class MarketInsightsSyncLog(Base):
    """
    Track sync operations for market insights data.
    """
    __tablename__ = "market_insights_sync_log"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    sync_type = Column(String(50), nullable=False)  # TRAVELED, BOOKED, BUSIEST, TRENDING
    origin_code = Column(String(10), nullable=True)  # Which origin was synced (null = all)
    
    status = Column(String(20), nullable=False)  # STARTED, SUCCESS, FAILED, PARTIAL
    
    records_fetched = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    
    error_message = Column(String(1000))
    
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    duration_seconds = Column(Float)
    
    extra_data = Column(JSON)  # Extra info about the sync
