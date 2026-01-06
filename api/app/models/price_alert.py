"""
Price Alert Model
"""
from sqlalchemy import Column, String, DateTime, Numeric, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid

from app.utils.database import Base


class PriceAlert(Base):
    __tablename__ = "price_alerts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    origin_code = Column(String(10), nullable=False, index=True)
    destination_code = Column(String(10), nullable=False, index=True)
    target_price = Column(Numeric(10, 2), nullable=False)
    
    is_active = Column(Boolean, default=True)
    last_notified_at = Column(DateTime(timezone=True))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="price_alerts")
    
    def __repr__(self):
        return f"<PriceAlert {self.origin_code}->{self.destination_code} @ €{self.target_price}>"

