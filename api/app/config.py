"""
Application Configuration - Environment Variables & Settings
"""
from pydantic_settings import BaseSettings
from pydantic import Field, computed_field
from typing import List
from functools import lru_cache


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables
    """
    # Application
    DEBUG: bool = Field(default=False)
    SECRET_KEY: str = Field(default="change-me-in-production")
    API_V1_PREFIX: str = "/api/v1"
    
    # Database - PostgreSQL
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://flightshark:flightshark_dev@localhost:5432/flightshark"
    )
    DB_POOL_SIZE: int = Field(default=20)
    DB_MAX_OVERFLOW: int = Field(default=10)
    
    # Database - MongoDB
    MONGODB_URL: str = Field(default="mongodb://localhost:27017/flightshark")
    MONGODB_DATABASE: str = Field(default="flightshark")
    
    # Cache - Redis
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CACHE_TTL_DEFAULT: int = Field(default=300)  # 5 minutes
    CACHE_TTL_FLIGHTS: int = Field(default=300)  # 5 minutes
    CACHE_TTL_DESTINATIONS: int = Field(default=3600)  # 1 hour
    CACHE_TTL_PRICES: int = Field(default=900)  # 15 minutes
    
    # Message Queue
    RABBITMQ_URL: str = Field(default="amqp://guest:guest@localhost:5672/")
    
    # JWT Authentication
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7)
    
    # CORS - stored as comma-separated string
    ALLOWED_ORIGINS_STR: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://localhost:3001",
        alias="ALLOWED_ORIGINS"
    )
    
    @computed_field
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Parse comma-separated origins into list"""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_STR.split(',') if origin.strip()]
    
    # Flight APIs - Primary: Amadeus
    AMADEUS_API_KEY: str = Field(default="")
    AMADEUS_API_SECRET: str = Field(default="")
    # Use True for sandbox/test API, False for production API
    AMADEUS_USE_TEST_API: bool = Field(default=True)
    
    @computed_field
    @property
    def AMADEUS_BASE_URL(self) -> str:
        """Get Amadeus API base URL based on environment"""
        if self.AMADEUS_USE_TEST_API:
            return "https://test.api.amadeus.com/v2"
        return "https://api.amadeus.com/v2"
    
    # Flight APIs - Secondary: Skyscanner (via RapidAPI)
    SKYSCANNER_API_KEY: str = Field(default="")
    
    # Flight APIs - Tertiary: Kiwi.com (Tequila API)
    KIWI_API_KEY: str = Field(default="")
    
    # Flight search strategy: "fallback", "parallel", "best_price"
    FLIGHT_SEARCH_STRATEGY: str = Field(default="fallback")
    
    # Social Media
    TWITTER_BEARER_TOKEN: str = Field(default="")
    
    # Notifications
    SENDGRID_API_KEY: str = Field(default="")
    FROM_EMAIL: str = Field(default="noreply@flightshark.com")
    TWILIO_ACCOUNT_SID: str = Field(default="")
    TWILIO_AUTH_TOKEN: str = Field(default="")
    TWILIO_PHONE_NUMBER: str = Field(default="")
    
    # Monitoring
    SENTRY_DSN: str = Field(default="")
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = Field(default=100)
    RATE_LIMIT_WINDOW: int = Field(default=60)  # seconds
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance
    """
    return Settings()


# Global settings instance
settings = get_settings()

