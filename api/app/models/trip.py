"""
Trip & TripMember Models
"""
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.utils.database import Base


class Trip(Base):
    __tablename__ = "trips"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    destination_code = Column(String(10), nullable=False, index=True)
    status = Column(String(50), default="planning")  # planning, confirmed, completed, cancelled
    departure_date = Column(Date)
    return_date = Column(Date)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="trips", foreign_keys=[owner_id])
    members = relationship("TripMember", back_populates="trip", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Trip {self.name} to {self.destination_code}>"


class TripMember(Base):
    __tablename__ = "trip_members"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id = Column(UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # Null for placeholder members
    
    origin_city = Column(String(100))
    origin_airport_code = Column(String(10))
    role = Column(String(50), default="member")  # owner, member
    status = Column(String(50), default="pending")  # pending, confirmed, declined, placeholder
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    trip = relationship("Trip", back_populates="members")
    user = relationship("User", back_populates="trip_memberships")
    
    def __repr__(self):
        return f"<TripMember {self.origin_airport_code} -> {self.trip.destination_code if self.trip else 'N/A'}>"

