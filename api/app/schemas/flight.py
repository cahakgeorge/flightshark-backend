"""
Flight Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


class FlightSegment(BaseModel):
    """A single flight segment"""
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    flight_number: str
    airline: str
    airline_logo: Optional[str] = None
    duration_minutes: int
    aircraft: Optional[str] = None


class FlightOffer(BaseModel):
    """A complete flight offer"""
    id: str
    price: float
    currency: str = "EUR"
    cabin_class: str
    airline: str
    airline_logo: Optional[str] = None
    
    outbound_segments: List[FlightSegment]
    return_segments: Optional[List[FlightSegment]] = None
    
    total_duration_minutes: int
    stops: int
    is_direct: bool
    
    booking_url: Optional[str] = None
    source: str  # "amadeus", "skyscanner", "kiwi", etc.
    
    # Kiwi-specific: virtual interlining connects flights on different airlines
    virtual_interlining: bool = False
    
    class Config:
        from_attributes = True


class FlightSearchRequest(BaseModel):
    """Flight search request"""
    origin: str = Field(..., min_length=3, max_length=3)
    destination: str = Field(..., min_length=3, max_length=3)
    departure_date: date
    return_date: Optional[date] = None
    passengers: int = Field(1, ge=1, le=9)
    cabin_class: str = "economy"
    direct_only: bool = False


class FlightSearchResponse(BaseModel):
    """Flight search response"""
    origin: str
    destination: str
    departure_date: date
    return_date: Optional[date]
    passengers: int
    
    offers: List[FlightOffer]
    total_results: int
    
    cached: bool = False
    searched_at: datetime


class PricePoint(BaseModel):
    """A single price data point"""
    date: datetime
    avg_price: float
    min_price: float
    max_price: float
    sample_count: int


class PriceHistoryResponse(BaseModel):
    """Price history for a route"""
    origin: str
    destination: str
    days: int
    prices: List[PricePoint]

