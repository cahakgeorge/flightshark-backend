"""
Notification Tasks - Price Alerts, Check-in Reminders, etc.
"""
from celery import shared_task
import logging
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def check_price_alerts(self):
    """
    Check all active price alerts against current prices.
    Runs every 30 minutes.
    """
    import psycopg2
    
    logger.info("Checking price alerts...")
    
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    alerts_triggered = 0
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Get active alerts with current prices below target
            cur.execute("""
                WITH current_prices AS (
                    SELECT DISTINCT ON (origin_code, destination_code)
                        origin_code,
                        destination_code,
                        MIN(price) as current_min_price
                    FROM price_history
                    WHERE time > NOW() - INTERVAL '1 hour'
                    GROUP BY origin_code, destination_code
                )
                SELECT 
                    a.id,
                    a.user_id,
                    a.origin_code,
                    a.destination_code,
                    a.target_price,
                    p.current_min_price,
                    u.email
                FROM price_alerts a
                JOIN current_prices p 
                    ON a.origin_code = p.origin_code 
                    AND a.destination_code = p.destination_code
                JOIN users u ON a.user_id = u.id
                WHERE a.is_active = true
                AND p.current_min_price <= a.target_price
                AND (a.last_notified_at IS NULL OR a.last_notified_at < NOW() - INTERVAL '6 hours')
            """)
            
            alerts = cur.fetchall()
            
            for alert in alerts:
                alert_id, user_id, origin, dest, target, current, email = alert
                
                # Send notification
                send_price_alert_email.delay(
                    email=email,
                    origin=origin,
                    destination=dest,
                    target_price=float(target),
                    current_price=float(current),
                )
                
                # Update last_notified_at
                cur.execute(
                    "UPDATE price_alerts SET last_notified_at = %s WHERE id = %s",
                    (datetime.utcnow(), alert_id)
                )
                
                alerts_triggered += 1
            
            conn.commit()
    
    logger.info(f"Triggered {alerts_triggered} price alerts")
    return {"alerts_triggered": alerts_triggered}


@shared_task
def send_price_alert_email(email: str, origin: str, destination: str, target_price: float, current_price: float):
    """
    Send price alert email to user.
    """
    logger.info(f"Sending price alert to {email}: {origin}->{destination} @ €{current_price}")
    
    # Would use SendGrid, SES, or similar
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    
    if sendgrid_key:
        # import sendgrid
        # sg = sendgrid.SendGridAPIClient(api_key=sendgrid_key)
        # message = sendgrid.Mail(
        #     from_email=os.getenv("FROM_EMAIL", "noreply@flightshark.com"),
        #     to_emails=email,
        #     subject=f"🎉 Price drop! {origin} → {destination} now €{current_price}",
        #     html_content=f"""
        #         <h1>Great news! Prices dropped!</h1>
        #         <p>Flights from {origin} to {destination} are now €{current_price}</p>
        #         <p>Your target was €{target_price}</p>
        #         <a href="https://flightshark.com/search?from={origin}&to={destination}">
        #             Book Now
        #         </a>
        #     """
        # )
        # sg.send(message)
        pass
    else:
        logger.info(f"[MOCK EMAIL] Price alert to {email}: {origin}->{destination} @ €{current_price}")
    
    return {"sent": True, "email": email}


@shared_task(bind=True, max_retries=3)
def send_checkin_reminders(self):
    """
    Send check-in reminders for flights departing in ~24 hours.
    Runs hourly.
    """
    import psycopg2
    
    logger.info("Checking for check-in reminders...")
    
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    reminders_sent = 0
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Find trips with departures in 22-26 hours
            cur.execute("""
                SELECT 
                    t.id,
                    t.name,
                    t.destination_code,
                    t.departure_date,
                    u.email,
                    u.full_name
                FROM trips t
                JOIN trip_members tm ON t.id = tm.trip_id
                JOIN users u ON tm.user_id = u.id
                WHERE t.status = 'confirmed'
                AND t.departure_date = CURRENT_DATE + INTERVAL '1 day'
                AND tm.status = 'confirmed'
            """)
            
            for row in cur.fetchall():
                trip_id, trip_name, dest, dep_date, email, name = row
                
                send_checkin_reminder_email.delay(
                    email=email,
                    name=name or "Traveler",
                    trip_name=trip_name,
                    destination=dest,
                    departure_date=str(dep_date),
                )
                reminders_sent += 1
    
    logger.info(f"Sent {reminders_sent} check-in reminders")
    return {"reminders_sent": reminders_sent}


@shared_task
def send_checkin_reminder_email(email: str, name: str, trip_name: str, destination: str, departure_date: str):
    """
    Send check-in reminder email.
    """
    logger.info(f"Sending check-in reminder to {email} for trip to {destination}")
    
    # Would integrate with email service
    logger.info(f"[MOCK EMAIL] Check-in reminder to {email}: Don't forget to check in for {trip_name}!")
    
    return {"sent": True, "email": email}


@shared_task
def notify_price_drop(origin: str, destination: str, current_price: float, drop_percent: float):
    """
    Notify users about significant price drops on a route.
    """
    import psycopg2
    
    logger.info(f"Price drop detected: {origin}->{destination} down {drop_percent:.1f}%")
    
    # Find users with alerts for this route
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT u.email, a.target_price
                FROM price_alerts a
                JOIN users u ON a.user_id = u.id
                WHERE a.origin_code = %s
                AND a.destination_code = %s
                AND a.is_active = true
                AND a.target_price >= %s
            """, (origin, destination, current_price))
            
            for email, target in cur.fetchall():
                send_price_alert_email.delay(
                    email=email,
                    origin=origin,
                    destination=destination,
                    target_price=float(target),
                    current_price=current_price,
                )
    
    return {"notified": True}


@shared_task
def notify_flight_status(trip_id: str, status: str, details: dict):
    """
    Notify trip members and their contacts about flight status updates.
    """
    import psycopg2
    
    logger.info(f"Flight status update for trip {trip_id}: {status}")
    
    db_url = os.getenv("DATABASE_URL", "").replace("+asyncpg", "")
    
    with psycopg2.connect(db_url) as conn:
        with conn.cursor() as cur:
            # Get trip members and their emergency contacts
            cur.execute("""
                SELECT 
                    u.email,
                    u.full_name,
                    u.preferences->>'emergency_contacts' as contacts
                FROM trip_members tm
                JOIN users u ON tm.user_id = u.id
                WHERE tm.trip_id = %s
            """, (trip_id,))
            
            for email, name, contacts_json in cur.fetchall():
                # Notify member
                logger.info(f"[MOCK] Notifying {email} of flight status: {status}")
                
                # Notify emergency contacts
                if contacts_json:
                    import json
                    contacts = json.loads(contacts_json)
                    for contact in contacts:
                        logger.info(f"[MOCK] Notifying contact {contact.get('email')}: {name}'s flight {status}")
    
    return {"trip_id": trip_id, "status": status}

