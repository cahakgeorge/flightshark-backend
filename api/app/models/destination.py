"""
Destination Model
"""
from sqlalchemy import Column, String, Text, DateTime, Numeric, ARRAY, JSON, func
from sqlalchemy.dialects.postgresql import UUID
import uuid

from app.utils.database import Base


class Destination(Base):
    __tablename__ = "destinations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    city = Column(String(255), nullable=False)
    country = Column(String(255), nullable=False)
    airport_code = Column(String(10), unique=True, nullable=False, index=True)
    
    description = Column(Text)
    tags = Column(ARRAY(String), default=list)  # ["sunny", "adventure", "party", etc.]
    highlights = Column(ARRAY(String), default=list)  # Key attractions
    best_time_to_visit = Column(String(100))
    average_price = Column(Numeric(10, 2))  # Average flight price from major hubs
    
    image_url = Column(Text)
    extra_data = Column(JSON, default=dict)  # Flexible additional data (metadata is reserved)
    
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<Destination {self.city} ({self.airport_code})>"

