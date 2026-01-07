"""
Airline & Flight Reference Models
"""
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, Float, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
import uuid

from app.utils.database import Base


class Airline(Base):
    """
    Airline reference table - maps IATA codes to full airline information.
    """
    __tablename__ = "airlines"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Codes
    iata_code = Column(String(2), unique=True, nullable=False, index=True)  # FR, EI, BA
    icao_code = Column(String(3), unique=True, nullable=True)  # RYR, EIN, BAW
    
    # Names
    name = Column(String(255), nullable=False)  # Ryanair
    full_name = Column(String(255), nullable=True)  # Ryanair DAC
    country = Column(String(255), nullable=True)
    country_code = Column(String(2), nullable=True)
    
    # Branding
    logo_url = Column(Text, nullable=True)  # URL to airline logo
    primary_color = Column(String(7), nullable=True)  # Hex color #003366
    
    # Type
    airline_type = Column(String(50), default='scheduled')  # scheduled, charter, cargo, low_cost
    alliance = Column(String(50), nullable=True)  # Star Alliance, Oneworld, SkyTeam
    
    # Contact
    website = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    
    # Operational info
    hub_airports = Column(ARRAY(String), default=list)  # ["DUB", "STN", "BGY"]
    fleet_size = Column(Integer, nullable=True)
    
    # Status
    is_active = Column(Boolean, default=True)
    is_low_cost = Column(Boolean, default=False)
    
    # Ratings (optional - from user reviews or external sources)
    rating = Column(Float, nullable=True)  # 1-5 scale
    on_time_performance = Column(Float, nullable=True)  # Percentage
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Airline {self.iata_code} - {self.name}>"
    
    @property
    def display_name(self):
        return f"{self.name} ({self.iata_code})"


class Route(Base):
    """
    Known flight routes between airports.
    Used for suggesting routes, calculating typical prices, etc.
    """
    __tablename__ = "routes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Route
    origin_code = Column(String(3), nullable=False, index=True)
    destination_code = Column(String(3), nullable=False, index=True)
    
    # Airlines operating this route
    airline_code = Column(String(2), ForeignKey('airlines.iata_code'), nullable=True)
    
    # Route info
    is_direct = Column(Boolean, default=True)
    typical_duration_minutes = Column(Integer, nullable=True)
    distance_km = Column(Integer, nullable=True)
    
    # Frequency
    flights_per_week = Column(Integer, nullable=True)
    operates_days = Column(ARRAY(Integer), nullable=True)  # [1,2,3,4,5] for Mon-Fri
    
    # Pricing
    typical_price_low = Column(Float, nullable=True)  # Economy low season
    typical_price_high = Column(Float, nullable=True)  # Economy high season
    
    # Status
    is_active = Column(Boolean, default=True)
    seasonal = Column(Boolean, default=False)  # Only operates certain months
    season_start = Column(Integer, nullable=True)  # Month 1-12
    season_end = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    airline = relationship("Airline", backref="routes")
    
    def __repr__(self):
        return f"<Route {self.origin_code}-{self.destination_code} ({self.airline_code})>"
    
    @property
    def route_code(self):
        return f"{self.origin_code}-{self.destination_code}"


class Aircraft(Base):
    """
    Aircraft types reference table.
    Optional - useful for flight details display.
    """
    __tablename__ = "aircraft"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Codes
    iata_code = Column(String(3), unique=True, nullable=False)  # 738, 320, 77W
    icao_code = Column(String(4), nullable=True)  # B738, A320, B77W
    
    # Names
    name = Column(String(255), nullable=False)  # Boeing 737-800
    manufacturer = Column(String(100), nullable=True)  # Boeing, Airbus
    model = Column(String(100), nullable=True)  # 737-800
    
    # Specs
    typical_seats = Column(Integer, nullable=True)
    range_km = Column(Integer, nullable=True)
    cruise_speed_kmh = Column(Integer, nullable=True)
    
    # Type
    aircraft_type = Column(String(50), default='narrow_body')  # narrow_body, wide_body, regional
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<Aircraft {self.iata_code} - {self.name}>"

