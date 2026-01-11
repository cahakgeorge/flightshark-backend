"""SQLAlchemy Models"""
from app.models.user import User
from app.models.trip import Trip, TripMember
from app.models.destination import Destination
from app.models.price_alert import PriceAlert
from app.models.airport import Airport, City
from app.models.airline import Airline, Route, Aircraft
from app.models.market_insights import (
    TraveledDestination,
    BookedDestination,
    BusiestTravelPeriod,
    TrendingDestination,
    MarketInsightsSyncLog,
)

__all__ = [
    "User", "Trip", "TripMember", "Destination", "PriceAlert", 
    "Airport", "City", "Airline", "Route", "Aircraft",
    "TraveledDestination", "BookedDestination", "BusiestTravelPeriod",
    "TrendingDestination", "MarketInsightsSyncLog",
]

