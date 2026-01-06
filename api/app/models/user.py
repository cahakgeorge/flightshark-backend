"""
User Model
"""
from sqlalchemy import Column, String, DateTime, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.utils.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255))
    home_city = Column(String(100))
    home_airport_code = Column(String(10))
    preferences = Column(JSON, default=dict)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    trips = relationship("Trip", back_populates="owner", foreign_keys="Trip.owner_id")
    trip_memberships = relationship("TripMember", back_populates="user")
    price_alerts = relationship("PriceAlert", back_populates="user")
    
    def __repr__(self):
        return f"<User {self.email}>"

