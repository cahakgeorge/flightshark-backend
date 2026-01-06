"""
User Schemas
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class UserCreate(BaseModel):
    """Schema for user registration"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = Field(None, max_length=255)
    home_city: Optional[str] = Field(None, max_length=100)
    home_airport_code: Optional[str] = Field(None, min_length=3, max_length=3)


class UserUpdate(BaseModel):
    """Schema for updating user profile"""
    full_name: Optional[str] = Field(None, max_length=255)
    home_city: Optional[str] = Field(None, max_length=100)
    home_airport_code: Optional[str] = Field(None, min_length=3, max_length=3)
    preferences: Optional[Dict[str, Any]] = None


class UserResponse(BaseModel):
    """Schema for user response"""
    id: UUID
    email: EmailStr
    full_name: Optional[str]
    home_city: Optional[str]
    home_airport_code: Optional[str]
    preferences: Optional[Dict[str, Any]]
    created_at: datetime
    
    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """Schema for authentication token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class PriceAlertResponse(BaseModel):
    """Schema for price alert response"""
    id: UUID
    origin_code: str
    destination_code: str
    target_price: float
    is_active: bool
    last_notified_at: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True

