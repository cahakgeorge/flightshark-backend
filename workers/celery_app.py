"""
Celery Application Configuration
"""
from celery import Celery
from celery.schedules import crontab
import os

# Load environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

# Create Celery app
app = Celery(
    "flightshark",
    broker=RABBITMQ_URL,
    backend=REDIS_URL,
    include=[
        "tasks.flight_prices",
        "tasks.scraping",
        "tasks.notifications",
        "tasks.analytics",
    ]
)

# Celery configuration
app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # Soft limit at 4 minutes
    
    # Worker settings
    worker_prefetch_multiplier=4,
    worker_concurrency=4,
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    
    # Rate limiting
    task_annotations={
        "tasks.flight_prices.*": {"rate_limit": "10/m"},  # 10 per minute
        "tasks.scraping.*": {"rate_limit": "5/m"},  # 5 per minute (be nice to APIs)
    },
    
    # Routing
    task_routes={
        "tasks.flight_prices.*": {"queue": "flights"},
        "tasks.scraping.*": {"queue": "scraping"},
        "tasks.notifications.*": {"queue": "notifications"},
        "tasks.analytics.*": {"queue": "analytics"},
    },
)

# Beat schedule (periodic tasks)
app.conf.beat_schedule = {
    # Update prices for popular routes every 15 minutes
    "update-popular-route-prices": {
        "task": "tasks.flight_prices.update_popular_routes",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "flights"},
    },
    
    # Scrape TikTok for destinations every hour
    "scrape-tiktok-content": {
        "task": "tasks.scraping.scrape_tiktok_destinations",
        "schedule": crontab(minute=0),  # Every hour at :00
        "options": {"queue": "scraping"},
    },
    
    # Scrape Twitter/X every 2 hours
    "scrape-twitter-content": {
        "task": "tasks.scraping.scrape_twitter_destinations",
        "schedule": crontab(minute=30, hour="*/2"),  # Every 2 hours at :30
        "options": {"queue": "scraping"},
    },
    
    # Check price alerts every 30 minutes
    "check-price-alerts": {
        "task": "tasks.notifications.check_price_alerts",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "notifications"},
    },
    
    # Send check-in reminders (runs every hour, checks for flights departing soon)
    "send-checkin-reminders": {
        "task": "tasks.notifications.send_checkin_reminders",
        "schedule": crontab(minute=0),  # Every hour
        "options": {"queue": "notifications"},
    },
    
    # Generate trending insights daily at 3 AM
    "generate-trending-insights": {
        "task": "tasks.analytics.generate_trending_insights",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "analytics"},
    },
    
    # Clean up old data weekly
    "cleanup-old-data": {
        "task": "tasks.analytics.cleanup_old_data",
        "schedule": crontab(hour=4, minute=0, day_of_week=0),  # Sunday 4 AM
        "options": {"queue": "analytics"},
    },
}

if __name__ == "__main__":
    app.start()

