"""
Market Insights Service - Fetches and manages travel trends from Amadeus
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import httpx
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from sqlalchemy.dialects.postgresql import insert

from app.config import settings
from app.models.market_insights import (
    TraveledDestination, 
    BookedDestination, 
    BusiestTravelPeriod,
    TrendingDestination,
    MarketInsightsSyncLog
)
from app.models.airport import Airport

logger = logging.getLogger(__name__)


class MarketInsightsService:
    """
    Service for fetching and managing market insights from Amadeus APIs.
    
    APIs Used:
    - Flight Most Traveled Destinations
    - Flight Most Booked Destinations  
    - Flight Busiest Traveling Period
    
    All data is stored in PostgreSQL and cached in Redis.
    """
    
    # Major airports to fetch insights for
    MAJOR_ORIGINS = [
        "DUB", "LHR", "CDG", "AMS", "FRA", "MAD", "BCN", "FCO", "MUC", "ZRH",
        "JFK", "LAX", "ORD", "MIA", "SFO", "BOS", "ATL", "DFW", "DEN", "SEA",
        "SIN", "HKG", "NRT", "ICN", "BKK", "DXB", "DOH", "SYD", "MEL"
    ]
    
    def __init__(self, db: AsyncSession, cache=None):
        self.db = db
        self.cache = cache
        self._token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    @property
    def is_configured(self) -> bool:
        """Check if Amadeus API is configured"""
        return bool(settings.AMADEUS_API_KEY and settings.AMADEUS_API_SECRET)
    
    @property
    def base_url(self) -> str:
        """Get Amadeus API base URL"""
        return settings.AMADEUS_BASE_URL.replace("/v2", "")
    
    async def _get_token(self) -> str:
        """Get or refresh OAuth token"""
        if self._token and self._token_expiry and datetime.utcnow() < self._token_expiry:
            return self._token
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/v1/security/oauth2/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.AMADEUS_API_KEY,
                    "client_secret": settings.AMADEUS_API_SECRET,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            
            self._token = data["access_token"]
            self._token_expiry = datetime.utcnow() + timedelta(seconds=data["expires_in"] - 60)
            
            return self._token
    
    async def _get_airport_info(self, code: str) -> Dict[str, str]:
        """Get airport city/country info from database"""
        result = await self.db.execute(
            select(Airport).where(Airport.iata_code == code)
        )
        airport = result.scalar_one_or_none()
        
        if airport:
            return {
                "city": airport.city,
                "country": airport.country,
                "country_code": airport.country_code
            }
        return {"city": None, "country": None, "country_code": None}
    
    # =========================================================================
    # MOST TRAVELED DESTINATIONS
    # =========================================================================
    
    async def fetch_most_traveled(
        self,
        origin: str,
        period: str = "2023",  # Year or YYYY-MM
        max_results: int = 50,
    ) -> List[Dict]:
        """
        Fetch most traveled destinations from an origin.
        
        Amadeus API: GET /v1/travel/analytics/air-traffic/traveled
        """
        if not self.is_configured:
            logger.warning("Amadeus API not configured")
            return []
        
        try:
            token = await self._get_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v1/travel/analytics/air-traffic/traveled",
                    params={
                        "originCityCode": origin,
                        "period": period,
                        "max": max_results,
                        "sort": "analytics.travelers.score",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    return response.json().get("data", [])
                else:
                    logger.warning(f"Amadeus most traveled API returned {response.status_code}: {response.text}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching most traveled for {origin}: {e}")
            return []
    
    async def sync_most_traveled(
        self,
        origins: Optional[List[str]] = None,
        period: str = None,
    ) -> Dict[str, Any]:
        """
        Sync most traveled destinations for specified origins.
        """
        origins = origins or self.MAJOR_ORIGINS
        period = period or str(datetime.now().year - 1)  # Previous year
        
        # Parse period
        period_year = int(period[:4])
        period_month = int(period[5:7]) if len(period) > 4 else None
        period_type = "MONTHLY" if period_month else "YEARLY"
        
        # Create sync log
        sync_log = MarketInsightsSyncLog(
            sync_type="TRAVELED",
            status="STARTED",
            started_at=datetime.utcnow(),
            metadata={"origins": origins, "period": period}
        )
        self.db.add(sync_log)
        await self.db.commit()
        
        stats = {"fetched": 0, "created": 0, "updated": 0, "failed": 0}
        
        try:
            for origin in origins:
                try:
                    data = await self.fetch_most_traveled(origin, period)
                    stats["fetched"] += len(data)
                    
                    for rank, item in enumerate(data, 1):
                        dest_code = item.get("destination")
                        if not dest_code:
                            continue
                        
                        # Get destination info
                        dest_info = await self._get_airport_info(dest_code)
                        
                        # Upsert record
                        travelers = item.get("analytics", {}).get("travelers", {})
                        
                        stmt = insert(TraveledDestination).values(
                            origin_code=origin,
                            destination_code=dest_code,
                            destination_city=dest_info["city"],
                            destination_country=dest_info["country"],
                            destination_country_code=dest_info["country_code"],
                            travelers_count=travelers.get("count"),
                            analytics_score=travelers.get("score"),
                            rank=rank,
                            period_type=period_type,
                            period_year=period_year,
                            period_month=period_month,
                            raw_data=item,
                            fetched_at=datetime.utcnow(),
                        ).on_conflict_do_update(
                            constraint="uq_traveled_dest_period",
                            set_={
                                "destination_city": dest_info["city"],
                                "destination_country": dest_info["country"],
                                "travelers_count": travelers.get("count"),
                                "analytics_score": travelers.get("score"),
                                "rank": rank,
                                "raw_data": item,
                                "updated_at": datetime.utcnow(),
                            }
                        )
                        await self.db.execute(stmt)
                        stats["created"] += 1
                    
                    await self.db.commit()
                    logger.info(f"Synced {len(data)} traveled destinations from {origin}")
                    
                except Exception as e:
                    logger.error(f"Error syncing traveled for {origin}: {e}")
                    stats["failed"] += 1
                    continue
            
            sync_log.status = "SUCCESS" if stats["failed"] == 0 else "PARTIAL"
            
        except Exception as e:
            logger.error(f"Error in sync_most_traveled: {e}")
            sync_log.status = "FAILED"
            sync_log.error_message = str(e)
        
        sync_log.records_fetched = stats["fetched"]
        sync_log.records_created = stats["created"]
        sync_log.records_failed = stats["failed"]
        sync_log.completed_at = datetime.utcnow()
        sync_log.duration_seconds = (sync_log.completed_at - sync_log.started_at).total_seconds()
        
        await self.db.commit()
        
        # Invalidate cache
        if self.cache:
            await self._invalidate_insights_cache("traveled")
        
        return stats
    
    # =========================================================================
    # MOST BOOKED DESTINATIONS
    # =========================================================================
    
    async def fetch_most_booked(
        self,
        origin: str,
        period: str = "2023",
        max_results: int = 50,
    ) -> List[Dict]:
        """
        Fetch most booked destinations from an origin.
        
        Amadeus API: GET /v1/travel/analytics/air-traffic/booked
        """
        if not self.is_configured:
            return []
        
        try:
            token = await self._get_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v1/travel/analytics/air-traffic/booked",
                    params={
                        "originCityCode": origin,
                        "period": period,
                        "max": max_results,
                        "sort": "analytics.travelers.score",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    return response.json().get("data", [])
                else:
                    logger.warning(f"Amadeus most booked API returned {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching most booked for {origin}: {e}")
            return []
    
    async def sync_most_booked(
        self,
        origins: Optional[List[str]] = None,
        period: str = None,
    ) -> Dict[str, Any]:
        """Sync most booked destinations."""
        origins = origins or self.MAJOR_ORIGINS
        period = period or str(datetime.now().year - 1)
        
        period_year = int(period[:4])
        period_month = int(period[5:7]) if len(period) > 4 else None
        period_type = "MONTHLY" if period_month else "YEARLY"
        
        sync_log = MarketInsightsSyncLog(
            sync_type="BOOKED",
            status="STARTED",
            started_at=datetime.utcnow(),
            metadata={"origins": origins, "period": period}
        )
        self.db.add(sync_log)
        await self.db.commit()
        
        stats = {"fetched": 0, "created": 0, "updated": 0, "failed": 0}
        
        try:
            for origin in origins:
                try:
                    data = await self.fetch_most_booked(origin, period)
                    stats["fetched"] += len(data)
                    
                    for rank, item in enumerate(data, 1):
                        dest_code = item.get("destination")
                        if not dest_code:
                            continue
                        
                        dest_info = await self._get_airport_info(dest_code)
                        analytics = item.get("analytics", {}).get("travelers", {})
                        
                        stmt = insert(BookedDestination).values(
                            origin_code=origin,
                            destination_code=dest_code,
                            destination_city=dest_info["city"],
                            destination_country=dest_info["country"],
                            destination_country_code=dest_info["country_code"],
                            bookings_count=analytics.get("count"),
                            analytics_score=analytics.get("score"),
                            rank=rank,
                            period_type=period_type,
                            period_year=period_year,
                            period_month=period_month,
                            raw_data=item,
                            fetched_at=datetime.utcnow(),
                        ).on_conflict_do_update(
                            constraint="uq_booked_dest_period",
                            set_={
                                "destination_city": dest_info["city"],
                                "bookings_count": analytics.get("count"),
                                "analytics_score": analytics.get("score"),
                                "rank": rank,
                                "raw_data": item,
                                "updated_at": datetime.utcnow(),
                            }
                        )
                        await self.db.execute(stmt)
                        stats["created"] += 1
                    
                    await self.db.commit()
                    logger.info(f"Synced {len(data)} booked destinations from {origin}")
                    
                except Exception as e:
                    logger.error(f"Error syncing booked for {origin}: {e}")
                    stats["failed"] += 1
            
            sync_log.status = "SUCCESS" if stats["failed"] == 0 else "PARTIAL"
            
        except Exception as e:
            sync_log.status = "FAILED"
            sync_log.error_message = str(e)
        
        sync_log.records_fetched = stats["fetched"]
        sync_log.records_created = stats["created"]
        sync_log.completed_at = datetime.utcnow()
        sync_log.duration_seconds = (sync_log.completed_at - sync_log.started_at).total_seconds()
        
        await self.db.commit()
        
        if self.cache:
            await self._invalidate_insights_cache("booked")
        
        return stats
    
    # =========================================================================
    # BUSIEST TRAVELING PERIODS
    # =========================================================================
    
    async def fetch_busiest_period(
        self,
        origin: str,
        direction: str = "DEPARTING",
        period: str = "2023",
    ) -> List[Dict]:
        """
        Fetch busiest traveling periods from an origin.
        
        Amadeus API: GET /v1/travel/analytics/air-traffic/busiest-period
        """
        if not self.is_configured:
            return []
        
        try:
            token = await self._get_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v1/travel/analytics/air-traffic/busiest-period",
                    params={
                        "cityCode": origin,
                        "period": period,
                        "direction": direction,
                    },
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30.0,
                )
                
                if response.status_code == 200:
                    return response.json().get("data", [])
                else:
                    logger.warning(f"Amadeus busiest period API returned {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching busiest period for {origin}: {e}")
            return []
    
    async def sync_busiest_periods(
        self,
        origins: Optional[List[str]] = None,
        period: str = None,
    ) -> Dict[str, Any]:
        """Sync busiest traveling periods."""
        origins = origins or self.MAJOR_ORIGINS
        period = period or str(datetime.now().year - 1)
        period_year = int(period[:4])
        
        sync_log = MarketInsightsSyncLog(
            sync_type="BUSIEST",
            status="STARTED",
            started_at=datetime.utcnow(),
            metadata={"origins": origins, "period": period}
        )
        self.db.add(sync_log)
        await self.db.commit()
        
        stats = {"fetched": 0, "created": 0, "failed": 0}
        
        try:
            for origin in origins:
                for direction in ["DEPARTING", "ARRIVING"]:
                    try:
                        data = await self.fetch_busiest_period(origin, direction, period)
                        stats["fetched"] += len(data)
                        
                        for rank, item in enumerate(data, 1):
                            period_str = item.get("period", "")
                            if len(period_str) >= 7:
                                month = int(period_str[5:7])
                            else:
                                continue
                            
                            analytics = item.get("analytics", {}).get("travelers", {})
                            
                            stmt = insert(BusiestTravelPeriod).values(
                                origin_code=origin,
                                period_year=period_year,
                                period_month=month,
                                direction=direction,
                                travelers_count=analytics.get("count"),
                                analytics_score=analytics.get("score"),
                                rank=rank,
                                raw_data=item,
                                fetched_at=datetime.utcnow(),
                            ).on_conflict_do_update(
                                constraint="uq_busiest_period",
                                set_={
                                    "travelers_count": analytics.get("count"),
                                    "analytics_score": analytics.get("score"),
                                    "rank": rank,
                                    "raw_data": item,
                                    "updated_at": datetime.utcnow(),
                                }
                            )
                            await self.db.execute(stmt)
                            stats["created"] += 1
                        
                        await self.db.commit()
                        
                    except Exception as e:
                        logger.error(f"Error syncing busiest for {origin}/{direction}: {e}")
                        stats["failed"] += 1
            
            sync_log.status = "SUCCESS" if stats["failed"] == 0 else "PARTIAL"
            
        except Exception as e:
            sync_log.status = "FAILED"
            sync_log.error_message = str(e)
        
        sync_log.records_fetched = stats["fetched"]
        sync_log.records_created = stats["created"]
        sync_log.completed_at = datetime.utcnow()
        sync_log.duration_seconds = (sync_log.completed_at - sync_log.started_at).total_seconds()
        
        await self.db.commit()
        
        if self.cache:
            await self._invalidate_insights_cache("busiest")
        
        return stats
    
    # =========================================================================
    # TRENDING DESTINATIONS (AGGREGATED)
    # =========================================================================
    
    async def calculate_trending(
        self,
        origin: str = "GLOBAL",
        top_n: int = 50,
    ) -> Dict[str, Any]:
        """
        Calculate trending destinations by combining traveled and booked data.
        """
        sync_log = MarketInsightsSyncLog(
            sync_type="TRENDING",
            origin_code=origin,
            status="STARTED",
            started_at=datetime.utcnow(),
        )
        self.db.add(sync_log)
        await self.db.commit()
        
        stats = {"created": 0, "updated": 0}
        
        try:
            # Aggregate scores from traveled and booked destinations
            if origin == "GLOBAL":
                # Aggregate across all origins
                traveled_query = """
                    SELECT destination_code, 
                           AVG(analytics_score) as travel_score,
                           MAX(destination_city) as city,
                           MAX(destination_country) as country,
                           MAX(destination_country_code) as country_code
                    FROM traveled_destinations 
                    WHERE is_active = TRUE
                    GROUP BY destination_code
                    ORDER BY travel_score DESC
                    LIMIT :limit
                """
                booked_query = """
                    SELECT destination_code, AVG(analytics_score) as book_score
                    FROM booked_destinations
                    WHERE is_active = TRUE
                    GROUP BY destination_code
                """
            else:
                traveled_query = """
                    SELECT destination_code, analytics_score as travel_score,
                           destination_city as city, destination_country as country,
                           destination_country_code as country_code
                    FROM traveled_destinations
                    WHERE origin_code = :origin AND is_active = TRUE
                    ORDER BY analytics_score DESC
                    LIMIT :limit
                """
                booked_query = """
                    SELECT destination_code, analytics_score as book_score
                    FROM booked_destinations
                    WHERE origin_code = :origin AND is_active = TRUE
                """
            
            from sqlalchemy import text
            
            traveled_result = await self.db.execute(
                text(traveled_query), {"origin": origin, "limit": top_n * 2}
            )
            traveled_rows = traveled_result.fetchall()
            
            booked_result = await self.db.execute(
                text(booked_query), {"origin": origin}
            )
            booked_scores = {row[0]: row[1] for row in booked_result.fetchall()}
            
            # Calculate composite scores
            destinations = []
            for row in traveled_rows:
                dest_code = row[0]
                travel_score = row[1] or 0
                book_score = booked_scores.get(dest_code, 0) or 0
                
                # Composite: 60% travel, 40% booking
                composite_score = (travel_score * 0.6) + (book_score * 0.4)
                
                destinations.append({
                    "code": dest_code,
                    "city": row[2],
                    "country": row[3],
                    "country_code": row[4],
                    "travel_score": travel_score,
                    "book_score": book_score,
                    "composite": composite_score,
                })
            
            # Sort by composite score and take top N
            destinations.sort(key=lambda x: x["composite"], reverse=True)
            destinations = destinations[:top_n]
            
            # Get previous scores for change calculation
            prev_scores = {}
            prev_result = await self.db.execute(
                select(TrendingDestination.destination_code, TrendingDestination.trending_score)
                .where(TrendingDestination.origin_code == origin)
            )
            for row in prev_result.fetchall():
                prev_scores[row[0]] = row[1]
            
            # Upsert trending destinations
            valid_until = datetime.utcnow() + timedelta(days=7)
            
            for rank, dest in enumerate(destinations, 1):
                prev_score = prev_scores.get(dest["code"], dest["composite"])
                score_change = dest["composite"] - prev_score if prev_score else 0
                
                stmt = insert(TrendingDestination).values(
                    origin_code=origin,
                    destination_code=dest["code"],
                    destination_city=dest["city"],
                    destination_country=dest["country"],
                    destination_country_code=dest["country_code"],
                    trending_score=dest["composite"],
                    travel_score=dest["travel_score"],
                    booking_score=dest["book_score"],
                    score_change=score_change,
                    rank=rank,
                    valid_until=valid_until,
                    fetched_at=datetime.utcnow(),
                ).on_conflict_do_update(
                    constraint="uq_trending_dest",
                    set_={
                        "destination_city": dest["city"],
                        "trending_score": dest["composite"],
                        "travel_score": dest["travel_score"],
                        "booking_score": dest["book_score"],
                        "score_change": score_change,
                        "rank": rank,
                        "valid_until": valid_until,
                        "updated_at": datetime.utcnow(),
                    }
                )
                await self.db.execute(stmt)
                stats["created"] += 1
            
            await self.db.commit()
            sync_log.status = "SUCCESS"
            
        except Exception as e:
            logger.error(f"Error calculating trending: {e}")
            sync_log.status = "FAILED"
            sync_log.error_message = str(e)
        
        sync_log.records_created = stats["created"]
        sync_log.completed_at = datetime.utcnow()
        sync_log.duration_seconds = (sync_log.completed_at - sync_log.started_at).total_seconds()
        await self.db.commit()
        
        if self.cache:
            await self._invalidate_insights_cache("trending")
        
        return stats
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    async def get_most_traveled(
        self,
        origin: str,
        limit: int = 20,
    ) -> List[TraveledDestination]:
        """Get most traveled destinations from cache or database."""
        cache_key = f"insights:traveled:{origin}:{limit}"
        
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        
        result = await self.db.execute(
            select(TraveledDestination)
            .where(TraveledDestination.origin_code == origin, TraveledDestination.is_active == True)
            .order_by(TraveledDestination.rank)
            .limit(limit)
        )
        destinations = result.scalars().all()
        
        data = [
            {
                "destination_code": d.destination_code,
                "destination_city": d.destination_city,
                "destination_country": d.destination_country,
                "travelers_count": d.travelers_count,
                "analytics_score": d.analytics_score,
                "rank": d.rank,
            }
            for d in destinations
        ]
        
        if self.cache and data:
            import json
            await self.cache.setex(cache_key, 86400, json.dumps(data))  # 24h cache
        
        return data
    
    async def get_most_booked(
        self,
        origin: str,
        limit: int = 20,
    ) -> List[Dict]:
        """Get most booked destinations."""
        cache_key = f"insights:booked:{origin}:{limit}"
        
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        
        result = await self.db.execute(
            select(BookedDestination)
            .where(BookedDestination.origin_code == origin, BookedDestination.is_active == True)
            .order_by(BookedDestination.rank)
            .limit(limit)
        )
        destinations = result.scalars().all()
        
        data = [
            {
                "destination_code": d.destination_code,
                "destination_city": d.destination_city,
                "destination_country": d.destination_country,
                "bookings_count": d.bookings_count,
                "analytics_score": d.analytics_score,
                "rank": d.rank,
            }
            for d in destinations
        ]
        
        if self.cache and data:
            import json
            await self.cache.setex(cache_key, 86400, json.dumps(data))
        
        return data
    
    async def get_busiest_periods(
        self,
        origin: str,
        direction: str = "DEPARTING",
    ) -> List[Dict]:
        """Get busiest traveling periods."""
        cache_key = f"insights:busiest:{origin}:{direction}"
        
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        
        result = await self.db.execute(
            select(BusiestTravelPeriod)
            .where(
                BusiestTravelPeriod.origin_code == origin,
                BusiestTravelPeriod.direction == direction,
                BusiestTravelPeriod.is_active == True
            )
            .order_by(BusiestTravelPeriod.rank)
        )
        periods = result.scalars().all()
        
        data = [
            {
                "month": p.period_month,
                "year": p.period_year,
                "travelers_count": p.travelers_count,
                "analytics_score": p.analytics_score,
                "rank": p.rank,
            }
            for p in periods
        ]
        
        if self.cache and data:
            import json
            await self.cache.setex(cache_key, 86400, json.dumps(data))
        
        return data
    
    async def get_trending(
        self,
        origin: str = "GLOBAL",
        limit: int = 20,
    ) -> List[Dict]:
        """Get trending destinations."""
        cache_key = f"insights:trending:{origin}:{limit}"
        
        if self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                import json
                return json.loads(cached)
        
        result = await self.db.execute(
            select(TrendingDestination)
            .where(
                TrendingDestination.origin_code == origin,
                TrendingDestination.is_active == True
            )
            .order_by(TrendingDestination.rank)
            .limit(limit)
        )
        destinations = result.scalars().all()
        
        data = [
            {
                "destination_code": d.destination_code,
                "destination_city": d.destination_city,
                "destination_country": d.destination_country,
                "trending_score": d.trending_score,
                "travel_score": d.travel_score,
                "booking_score": d.booking_score,
                "score_change": d.score_change,
                "rank": d.rank,
                "tags": d.tags,
            }
            for d in destinations
        ]
        
        if self.cache and data:
            import json
            await self.cache.setex(cache_key, 3600, json.dumps(data))  # 1h cache for trending
        
        return data
    
    async def _invalidate_insights_cache(self, insight_type: str):
        """Invalidate cached insights data."""
        if not self.cache:
            return
        
        # Get all keys matching pattern
        pattern = f"insights:{insight_type}:*"
        keys = await self.cache.keys(pattern)
        
        if keys:
            await self.cache.delete(*keys)
            logger.info(f"Invalidated {len(keys)} cache keys for {insight_type}")
