"""
Flight Price Update Tasks
"""
from celery import shared_task
import httpx
import logging
from datetime import datetime, timedelta
from typing import List

logger = logging.getLogger(__name__)

# Popular routes to track
POPULAR_ROUTES = [
    ("DUB", "BCN"),  # Dublin -> Barcelona
    ("DUB", "LHR"),  # Dublin -> London
    ("DUB", "CDG"),  # Dublin -> Paris
    ("DUB", "AMS"),  # Dublin -> Amsterdam
    ("DUB", "FCO"),  # Dublin -> Rome
    ("LHR", "BCN"),  # London -> Barcelona
    ("LHR", "CDG"),  # London -> Paris
    ("LHR", "AMS"),  # London -> Amsterdam
]


@shared_task(bind=True, max_retries=3)
def update_popular_routes(self):
    """
    Update prices for popular routes.
    Runs every 15 minutes.
    """
    logger.info("Starting popular routes price update...")
    
    updated = 0
    errors = 0
    
    for origin, destination in POPULAR_ROUTES:
        try:
            update_route_prices.delay(origin, destination)
            updated += 1
        except Exception as e:
            logger.error(f"Failed to queue update for {origin}->{destination}: {e}")
            errors += 1
    
    logger.info(f"Queued {updated} route updates, {errors} errors")
    return {"updated": updated, "errors": errors}


@shared_task(bind=True, max_retries=3, rate_limit="10/m")
def update_route_prices(self, origin: str, destination: str):
    """
    Fetch and store current prices for a specific route.
    """
    import os
    import psycopg2
    
    logger.info(f"Updating prices for {origin} -> {destination}")
    
    try:
        # This would call actual flight API
        # For now, generate mock prices
        prices = _fetch_prices(origin, destination)
        
        # Store in TimescaleDB
        db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
        
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                for price_data in prices:
                    cur.execute(
                        """
                        INSERT INTO price_history 
                        (time, origin_code, destination_code, airline, price, source)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            datetime.utcnow(),
                            origin,
                            destination,
                            price_data["airline"],
                            price_data["price"],
                            price_data.get("source", "api"),
                        )
                    )
                conn.commit()
        
        logger.info(f"Stored {len(prices)} prices for {origin} -> {destination}")
        return {"route": f"{origin}-{destination}", "prices_stored": len(prices)}
        
    except Exception as e:
        logger.error(f"Failed to update prices for {origin} -> {destination}: {e}")
        raise self.retry(exc=e, countdown=60)


def _fetch_prices(origin: str, destination: str) -> List[dict]:
    """
    Fetch prices from flight APIs (mock implementation)
    """
    import random
    
    airlines = ["Ryanair", "Aer Lingus", "Vueling", "EasyJet"]
    prices = []
    
    for airline in airlines:
        base_price = random.randint(30, 150)
        prices.append({
            "airline": airline,
            "price": base_price + random.randint(-10, 30),
            "source": "mock",
        })
    
    return prices


@shared_task
def check_for_price_drops():
    """
    Check if any tracked routes have significant price drops.
    Triggers alerts if prices dropped significantly.
    """
    import os
    import psycopg2
    
    logger.info("Checking for price drops...")
    
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    drops_found = []
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Find routes where current price is 20% lower than 7-day average
            cur.execute("""
                WITH current_prices AS (
                    SELECT DISTINCT ON (origin_code, destination_code)
                        origin_code,
                        destination_code,
                        price as current_price
                    FROM price_history
                    WHERE time > NOW() - INTERVAL '1 hour'
                    ORDER BY origin_code, destination_code, time DESC
                ),
                avg_prices AS (
                    SELECT 
                        origin_code,
                        destination_code,
                        AVG(price) as avg_price
                    FROM price_history
                    WHERE time > NOW() - INTERVAL '7 days'
                    GROUP BY origin_code, destination_code
                )
                SELECT 
                    c.origin_code,
                    c.destination_code,
                    c.current_price,
                    a.avg_price,
                    ((a.avg_price - c.current_price) / a.avg_price * 100) as drop_percent
                FROM current_prices c
                JOIN avg_prices a USING (origin_code, destination_code)
                WHERE c.current_price < a.avg_price * 0.8
            """)
            
            for row in cur.fetchall():
                drops_found.append({
                    "origin": row[0],
                    "destination": row[1],
                    "current_price": float(row[2]),
                    "avg_price": float(row[3]),
                    "drop_percent": float(row[4]),
                })
    
    # Trigger notifications for significant drops
    for drop in drops_found:
        from tasks.notifications import notify_price_drop
        notify_price_drop.delay(
            drop["origin"],
            drop["destination"],
            drop["current_price"],
            drop["drop_percent"]
        )
    
    logger.info(f"Found {len(drops_found)} significant price drops")
    return {"drops_found": len(drops_found), "drops": drops_found}

