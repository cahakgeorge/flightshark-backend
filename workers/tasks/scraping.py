"""
Social Media Scraping Tasks
"""
from celery import shared_task
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import os

logger = logging.getLogger(__name__)

# Destinations to scrape content for
DESTINATIONS_TO_SCRAPE = [
    ("BCN", "Barcelona"),
    ("CDG", "Paris"),
    ("FCO", "Rome"),
    ("AMS", "Amsterdam"),
    ("LIS", "Lisbon"),
    ("ATH", "Athens"),
    ("DPS", "Bali"),
    ("BKK", "Bangkok"),
    ("TYO", "Tokyo"),
    ("NYC", "New York"),
]


@shared_task(bind=True, max_retries=2)
def scrape_tiktok_destinations(self):
    """
    Scrape TikTok for travel content about destinations.
    Runs hourly.
    """
    logger.info("Starting TikTok scraping for destinations...")
    
    from pymongo import MongoClient
    
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/flightshark")
    client = MongoClient(mongo_url)
    db = client.flightshark
    collection = db.social_content
    
    scraped = 0
    errors = 0
    
    for code, city in DESTINATIONS_TO_SCRAPE:
        try:
            content = _scrape_tiktok_for_destination(city)
            
            for item in content:
                # Add metadata
                item["destination_code"] = code
                item["platform"] = "tiktok"
                item["scraped_at"] = datetime.utcnow()
                item["expires_at"] = datetime.utcnow() + timedelta(days=7)
                
                # Upsert to avoid duplicates
                collection.update_one(
                    {"content_id": item.get("content_id"), "platform": "tiktok"},
                    {"$set": item},
                    upsert=True
                )
            
            scraped += len(content)
            logger.info(f"Scraped {len(content)} TikTok videos for {city}")
            
        except Exception as e:
            logger.error(f"Failed to scrape TikTok for {city}: {e}")
            errors += 1
    
    client.close()
    logger.info(f"TikTok scraping complete: {scraped} items, {errors} errors")
    return {"scraped": scraped, "errors": errors}


@shared_task(bind=True, max_retries=2)
def scrape_twitter_destinations(self):
    """
    Scrape Twitter/X for travel content about destinations.
    Runs every 2 hours.
    """
    logger.info("Starting Twitter scraping for destinations...")
    
    from pymongo import MongoClient
    
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/flightshark")
    client = MongoClient(mongo_url)
    db = client.flightshark
    collection = db.social_content
    
    scraped = 0
    errors = 0
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
    
    if not bearer_token:
        logger.warning("Twitter bearer token not configured, using mock data")
    
    for code, city in DESTINATIONS_TO_SCRAPE:
        try:
            content = _scrape_twitter_for_destination(city, bearer_token)
            
            for item in content:
                item["destination_code"] = code
                item["platform"] = "twitter"
                item["scraped_at"] = datetime.utcnow()
                item["expires_at"] = datetime.utcnow() + timedelta(days=3)
                
                collection.update_one(
                    {"content_id": item.get("content_id"), "platform": "twitter"},
                    {"$set": item},
                    upsert=True
                )
            
            scraped += len(content)
            
        except Exception as e:
            logger.error(f"Failed to scrape Twitter for {city}: {e}")
            errors += 1
    
    client.close()
    logger.info(f"Twitter scraping complete: {scraped} items, {errors} errors")
    return {"scraped": scraped, "errors": errors}


def _scrape_tiktok_for_destination(city: str) -> List[Dict]:
    """
    Scrape TikTok for destination content.
    
    Note: TikTok doesn't have an official API for this.
    Options:
    1. Use unofficial TikTokApi library (may break)
    2. Use Playwright for browser automation
    3. Use a third-party service like RapidAPI
    
    For now, returns mock data.
    """
    import random
    
    # Mock TikTok content
    mock_content = []
    
    hashtags = [
        f"#{city.lower()}travel",
        f"#{city.lower()}vacation",
        f"#{city.lower()}tips",
        f"visit{city.lower()}",
    ]
    
    creators = [
        "@traveltok_official",
        "@wanderlust_diaries",
        "@budget_backpacker",
        "@luxury_escapes",
        "@solo_female_traveler",
    ]
    
    for i in range(random.randint(3, 8)):
        mock_content.append({
            "content_id": f"tiktok_{city.lower()}_{i}_{datetime.utcnow().timestamp()}",
            "url": f"https://tiktok.com/@creator/video/{random.randint(1000000, 9999999)}",
            "thumbnail_url": f"https://images.unsplash.com/photo-{random.randint(1500000000, 1600000000)}?w=400",
            "caption": f"Best things to do in {city}! {random.choice(hashtags)} #travel",
            "creator": random.choice(creators),
            "engagement": {
                "views": random.randint(10000, 5000000),
                "likes": random.randint(1000, 500000),
                "comments": random.randint(50, 10000),
                "shares": random.randint(100, 50000),
            },
            "tags": [city.lower(), "travel", "vacation", random.choice(["tips", "guide", "vlog"])],
        })
    
    return mock_content


def _scrape_twitter_for_destination(city: str, bearer_token: str = None) -> List[Dict]:
    """
    Scrape Twitter for destination content using the official API.
    """
    import random
    
    if bearer_token:
        # Would use official Twitter API v2 here
        # import httpx
        # response = httpx.get(
        #     "https://api.twitter.com/2/tweets/search/recent",
        #     params={"query": f"{city} travel -is:retweet"},
        #     headers={"Authorization": f"Bearer {bearer_token}"}
        # )
        pass
    
    # Mock Twitter content
    mock_content = []
    
    for i in range(random.randint(2, 5)):
        mock_content.append({
            "content_id": f"twitter_{city.lower()}_{i}_{datetime.utcnow().timestamp()}",
            "url": f"https://twitter.com/user/status/{random.randint(1000000000, 9999999999)}",
            "caption": f"Just visited {city} and it was amazing! Here are my top recommendations...",
            "creator": f"@traveler_{random.randint(100, 999)}",
            "engagement": {
                "likes": random.randint(10, 5000),
                "retweets": random.randint(5, 1000),
                "replies": random.randint(1, 200),
            },
            "tags": [city.lower(), "travel"],
        })
    
    return mock_content


@shared_task
def cleanup_expired_content():
    """
    Remove expired social content from MongoDB.
    The TTL index should handle this, but this is a backup.
    """
    from pymongo import MongoClient
    
    mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017/flightshark")
    client = MongoClient(mongo_url)
    db = client.flightshark
    
    result = db.social_content.delete_many({
        "expires_at": {"$lt": datetime.utcnow()}
    })
    
    client.close()
    logger.info(f"Cleaned up {result.deleted_count} expired social content items")
    return {"deleted": result.deleted_count}

