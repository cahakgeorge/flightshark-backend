"""
Airport Model - Reference data for all airports
"""
from sqlalchemy import Column, String, Text, Float, Boolean, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.utils.database import Base


class Airport(Base):
    """
    Airport reference table - maps IATA codes to full airport/city information.
    This is seeded with data from OpenFlights or similar sources.
    """
    __tablename__ = "airports"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Codes
    iata_code = Column(String(3), unique=True, nullable=False, index=True)  # DUB, BCN, JFK
    icao_code = Column(String(4), unique=True, nullable=True)  # EIDW, LEBL, KJFK
    
    # Names
    name = Column(String(255), nullable=False)  # Dublin Airport
    city = Column(String(255), nullable=False)  # Dublin
    country = Column(String(255), nullable=False)  # Ireland
    country_code = Column(String(2), nullable=False, index=True)  # IE, ES, US
    
    # Location
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String(50), nullable=True)  # Europe/Dublin
    
    # Metadata
    altitude_ft = Column(Integer, nullable=True)
    airport_type = Column(String(50), default='airport')  # airport, heliport, seaplane_base
    
    # Status
    is_active = Column(Boolean, default=True)
    is_major = Column(Boolean, default=False)  # Major international airports
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Airport {self.iata_code} - {self.city}>"
    
    @property
    def display_name(self):
        """Return formatted display name: City (CODE)"""
        return f"{self.city} ({self.iata_code})"
    
    @property
    def full_name(self):
        """Return full name: City Airport Name (CODE)"""
        return f"{self.city} - {self.name} ({self.iata_code})"


class City(Base):
    """
    City reference table - for cities with multiple airports
    """
    __tablename__ = "cities"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    name = Column(String(255), nullable=False)
    country = Column(String(255), nullable=False)
    country_code = Column(String(2), nullable=False, index=True)
    
    # Location
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    timezone = Column(String(50), nullable=True)
    
    # For cities with multiple airports (e.g., London: LHR, LGW, STN, LTN, LCY)
    main_airport_code = Column(String(3), nullable=True)  # Primary airport
    all_airport_codes = Column(String(50), nullable=True)  # Comma-separated: "LHR,LGW,STN"
    
    # Metadata
    population = Column(Integer, nullable=True)
    is_capital = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<City {self.name}, {self.country_code}>"

