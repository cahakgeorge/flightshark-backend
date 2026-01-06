"""
Analytics & Data Processing Tasks
"""
from celery import shared_task
import logging
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


@shared_task
def generate_trending_insights():
    """
    Generate trending destination insights based on:
    - Social media engagement
    - Search volume
    - Price trends
    
    Runs daily at 3 AM.
    """
    from pymongo import MongoClient
    
    logger.info("Generating trending insights...")
    
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/flightshark")
    client = MongoClient(mongo_url)
    db = client.flightshark
    
    # Aggregate social content engagement by destination
    pipeline = [
        {
            "$match": {
                "scraped_at": {"$gte": datetime.utcnow() - timedelta(days=7)}
            }
        },
        {
            "$group": {
                "_id": "$destination_code",
                "total_engagement": {
                    "$sum": {
                        "$add": [
                            {"$ifNull": ["$engagement.views", 0]},
                            {"$multiply": [{"$ifNull": ["$engagement.likes", 0]}, 10]},
                            {"$multiply": [{"$ifNull": ["$engagement.comments", 0]}, 20]},
                        ]
                    }
                },
                "content_count": {"$sum": 1},
                "platforms": {"$addToSet": "$platform"},
                "top_tags": {"$push": "$tags"},
            }
        },
        {
            "$project": {
                "_id": 1,
                "total_engagement": 1,
                "content_count": 1,
                "platforms": 1,
                "trending_score": {
                    "$multiply": [
                        {"$log10": {"$add": ["$total_engagement", 1]}},
                        {"$add": ["$content_count", 1]}
                    ]
                }
            }
        },
        {"$sort": {"trending_score": -1}},
    ]
    
    results = list(db.social_content.aggregate(pipeline))
    
    # Store insights
    for result in results:
        db.destination_insights.update_one(
            {"destination_code": result["_id"]},
            {
                "$set": {
                    "destination_code": result["_id"],
                    "trending_score": result["trending_score"],
                    "total_engagement": result["total_engagement"],
                    "content_count": result["content_count"],
                    "platforms": result["platforms"],
                    "generated_at": datetime.utcnow(),
                }
            },
            upsert=True,
        )
    
    client.close()
    logger.info(f"Generated insights for {len(results)} destinations")
    return {"destinations_processed": len(results)}


@shared_task
def calculate_best_booking_times():
    """
    Analyze price history to determine best booking times for routes.
    """
    import psycopg2
    
    logger.info("Calculating best booking times...")
    
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Analyze which day of week has lowest prices
            cur.execute("""
                SELECT 
                    origin_code,
                    destination_code,
                    EXTRACT(DOW FROM time) as day_of_week,
                    AVG(price) as avg_price,
                    COUNT(*) as sample_count
                FROM price_history
                WHERE time > NOW() - INTERVAL '90 days'
                GROUP BY origin_code, destination_code, EXTRACT(DOW FROM time)
                HAVING COUNT(*) > 10
                ORDER BY origin_code, destination_code, avg_price
            """)
            
            results = cur.fetchall()
            
            # Process results
            routes = {}
            for origin, dest, dow, avg_price, count in results:
                route_key = f"{origin}-{dest}"
                if route_key not in routes:
                    routes[route_key] = {
                        "origin": origin,
                        "destination": dest,
                        "best_day": int(dow),
                        "best_day_price": float(avg_price),
                        "days_analyzed": [],
                    }
                routes[route_key]["days_analyzed"].append({
                    "day": int(dow),
                    "avg_price": float(avg_price),
                    "samples": count,
                })
    
    logger.info(f"Analyzed booking times for {len(routes)} routes")
    return {"routes_analyzed": len(routes)}


@shared_task
def cleanup_old_data():
    """
    Clean up old data from databases.
    Runs weekly on Sunday at 4 AM.
    """
    import psycopg2
    from pymongo import MongoClient
    
    logger.info("Starting data cleanup...")
    
    deleted_counts = {
        "social_content": 0,
        "flight_cache": 0,
    }
    
    # Clean up MongoDB
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/flightshark")
    client = MongoClient(mongo_url)
    db = client.flightshark
    
    # Remove old social content (TTL should handle this, but double-check)
    result = db.social_content.delete_many({
        "scraped_at": {"$lt": datetime.utcnow() - timedelta(days=14)}
    })
    deleted_counts["social_content"] = result.deleted_count
    
    # Remove old flight cache
    result = db.flight_cache.delete_many({
        "fetched_at": {"$lt": datetime.utcnow() - timedelta(days=1)}
    })
    deleted_counts["flight_cache"] = result.deleted_count
    
    client.close()
    
    # Clean up old price alerts that haven't been triggered in 6 months
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE price_alerts
                SET is_active = false
                WHERE is_active = true
                AND created_at < NOW() - INTERVAL '6 months'
                AND last_notified_at IS NULL
            """)
            deleted_counts["stale_alerts"] = cur.rowcount
            conn.commit()
    
    logger.info(f"Cleanup complete: {deleted_counts}")
    return deleted_counts


@shared_task
def generate_user_recommendations(user_id: str):
    """
    Generate personalized destination recommendations for a user.
    """
    import psycopg2
    from pymongo import MongoClient
    
    logger.info(f"Generating recommendations for user {user_id}")
    
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/flightshark")
    
    # Get user preferences
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT home_airport_code, preferences FROM users WHERE id = %s",
                (user_id,)
            )
            row = cur.fetchone()
            if not row:
                return {"error": "User not found"}
            
            home_airport, preferences = row
            preferences = preferences or {}
    
    # Get trending destinations
    client = MongoClient(mongo_url)
    db = client.flightshark
    
    trending = list(db.destination_insights.find().sort("trending_score", -1).limit(20))
    
    # Score destinations based on user preferences
    preferred_tags = preferences.get("tags", [])
    recommendations = []
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            for trend in trending:
                code = trend["destination_code"]
                
                # Get destination info
                cur.execute(
                    "SELECT city, country, tags, average_price FROM destinations WHERE airport_code = %s",
                    (code,)
                )
                dest_row = cur.fetchone()
                if not dest_row:
                    continue
                
                city, country, tags, avg_price = dest_row
                tags = tags or []
                
                # Calculate match score
                tag_match = len(set(tags) & set(preferred_tags)) if preferred_tags else 0
                score = trend["trending_score"] + (tag_match * 10)
                
                recommendations.append({
                    "code": code,
                    "city": city,
                    "country": country,
                    "score": score,
                    "trending_score": trend["trending_score"],
                    "tag_match": tag_match,
                    "average_price": float(avg_price) if avg_price else None,
                })
    
    client.close()
    
    # Sort by score and return top 10
    recommendations.sort(key=lambda x: x["score"], reverse=True)
    
    logger.info(f"Generated {len(recommendations[:10])} recommendations for user {user_id}")
    return {"user_id": user_id, "recommendations": recommendations[:10]}

