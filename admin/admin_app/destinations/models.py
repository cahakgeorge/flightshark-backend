"""
Destination & Reference Data Models for Django Admin
"""
from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid


class DestinationTag(models.Model):
    """
    Tags for categorizing destinations (sunny, adventure, party, etc.)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    emoji = models.CharField(max_length=10, blank=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#0ca4eb', help_text='Hex color code')
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'destination_tags'
        ordering = ['display_order', 'name']
        verbose_name = 'Destination Tag'
        verbose_name_plural = 'Destination Tags'
    
    def __str__(self):
        return f"{self.emoji} {self.name}" if self.emoji else self.name


class Destination(models.Model):
    """
    Destination information - managed via Django Admin
    Maps to the 'destinations' table used by FastAPI
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    city = models.CharField(max_length=255)
    country = models.CharField(max_length=255)
    airport_code = models.CharField(max_length=10, unique=True, db_index=True)
    
    description = models.TextField(blank=True)
    tags = ArrayField(
        models.CharField(max_length=50),
        default=list,
        blank=True,
        help_text='Tags like: sunny, adventure, party, family, romantic'
    )
    highlights = ArrayField(
        models.CharField(max_length=255),
        default=list,
        blank=True,
        help_text='Key attractions or things the city is known for'
    )
    best_time_to_visit = models.CharField(max_length=100, blank=True)
    average_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text='Average flight price in EUR'
    )
    
    image_url = models.URLField(max_length=500, blank=True)
    hero_image = models.ImageField(upload_to='destinations/', blank=True, null=True)
    
    # Metadata (flexible JSON field)
    extra_data = models.JSONField(default=dict, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'destinations'
        ordering = ['city']
        verbose_name = 'Destination'
        verbose_name_plural = 'Destinations'
    
    def __str__(self):
        return f"{self.city} ({self.airport_code})"
    
    @property
    def tag_list(self):
        return ', '.join(self.tags) if self.tags else '-'


class BestBookingTime(models.Model):
    """
    Best times to book flights for a destination
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    destination = models.ForeignKey(
        Destination, 
        on_delete=models.CASCADE, 
        related_name='booking_times'
    )
    
    days_before_departure = models.IntegerField(
        help_text='Optimal days before departure to book'
    )
    best_day_of_week = models.IntegerField(
        choices=[
            (0, 'Monday'),
            (1, 'Tuesday'),
            (2, 'Wednesday'),
            (3, 'Thursday'),
            (4, 'Friday'),
            (5, 'Saturday'),
            (6, 'Sunday'),
        ],
        null=True,
        blank=True,
        help_text='Best day to book'
    )
    best_month = models.IntegerField(
        choices=[(i, m) for i, m in enumerate([
            'January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'
        ], 1)],
        null=True,
        blank=True,
        help_text='Best month to travel'
    )
    
    average_savings = models.DecimalField(
        max_digits=5, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text='Average savings percentage'
    )
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'best_booking_times'
        verbose_name = 'Best Booking Time'
        verbose_name_plural = 'Best Booking Times'
    
    def __str__(self):
        return f"{self.destination.city} - Book {self.days_before_departure} days ahead"


# ===================
# REFERENCE DATA
# ===================

class Airport(models.Model):
    """
    Airport reference data - all airports worldwide
    """
    AIRPORT_TYPES = [
        ('airport', 'Airport'),
        ('heliport', 'Heliport'),
        ('seaplane_base', 'Seaplane Base'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Codes
    iata_code = models.CharField(max_length=3, unique=True, db_index=True, help_text='3-letter IATA code (e.g., DUB)')
    icao_code = models.CharField(max_length=4, unique=True, null=True, blank=True, help_text='4-letter ICAO code (e.g., EIDW)')
    
    # Names
    name = models.CharField(max_length=255, help_text='Airport name (e.g., Dublin Airport)')
    city = models.CharField(max_length=255, help_text='City name')
    country = models.CharField(max_length=255)
    country_code = models.CharField(max_length=2, db_index=True, help_text='ISO 2-letter country code')
    
    # Location
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    timezone = models.CharField(max_length=50, blank=True, help_text='e.g., Europe/Dublin')
    altitude_ft = models.IntegerField(null=True, blank=True)
    
    # Type and status
    airport_type = models.CharField(max_length=50, choices=AIRPORT_TYPES, default='airport')
    is_active = models.BooleanField(default=True)
    is_major = models.BooleanField(default=False, help_text='Major international airport')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'airports'
        ordering = ['city', 'name']
        verbose_name = 'Airport'
        verbose_name_plural = 'Airports'
    
    def __str__(self):
        return f"{self.city} - {self.name} ({self.iata_code})"


class Airline(models.Model):
    """
    Airline reference data
    """
    AIRLINE_TYPES = [
        ('scheduled', 'Scheduled'),
        ('charter', 'Charter'),
        ('cargo', 'Cargo'),
        ('low_cost', 'Low Cost'),
    ]
    
    ALLIANCES = [
        ('', 'None'),
        ('Star Alliance', 'Star Alliance'),
        ('Oneworld', 'Oneworld'),
        ('SkyTeam', 'SkyTeam'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Codes
    iata_code = models.CharField(max_length=2, unique=True, db_index=True, help_text='2-letter IATA code (e.g., FR)')
    icao_code = models.CharField(max_length=3, unique=True, null=True, blank=True, help_text='3-letter ICAO code (e.g., RYR)')
    
    # Names
    name = models.CharField(max_length=255, help_text='Airline name (e.g., Ryanair)')
    full_name = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=255, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    
    # Branding
    logo_url = models.URLField(max_length=500, blank=True, help_text='URL to airline logo')
    primary_color = models.CharField(max_length=7, blank=True, help_text='Hex color (e.g., #003366)')
    
    # Type
    airline_type = models.CharField(max_length=50, choices=AIRLINE_TYPES, default='scheduled')
    alliance = models.CharField(max_length=50, choices=ALLIANCES, blank=True)
    
    # Contact
    website = models.URLField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    
    # Operational
    hub_airports = ArrayField(
        models.CharField(max_length=3),
        default=list,
        blank=True,
        help_text='Hub airport IATA codes'
    )
    fleet_size = models.IntegerField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    is_low_cost = models.BooleanField(default=False)
    
    # Ratings
    rating = models.FloatField(null=True, blank=True, help_text='1-5 scale')
    on_time_performance = models.FloatField(null=True, blank=True, help_text='Percentage')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'airlines'
        ordering = ['name']
        verbose_name = 'Airline'
        verbose_name_plural = 'Airlines'
    
    def __str__(self):
        return f"{self.name} ({self.iata_code})"


class Route(models.Model):
    """
    Known flight routes between airports
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Route
    origin_code = models.CharField(max_length=3, db_index=True, help_text='Origin airport IATA code')
    destination_code = models.CharField(max_length=3, db_index=True, help_text='Destination airport IATA code')
    airline_code = models.CharField(max_length=2, blank=True, help_text='Operating airline IATA code')
    
    # Route info
    is_direct = models.BooleanField(default=True)
    typical_duration_minutes = models.IntegerField(null=True, blank=True)
    distance_km = models.IntegerField(null=True, blank=True)
    
    # Frequency
    flights_per_week = models.IntegerField(null=True, blank=True)
    operates_days = ArrayField(
        models.IntegerField(),
        default=list,
        blank=True,
        help_text='Days of week (1=Mon, 7=Sun)'
    )
    
    # Pricing
    typical_price_low = models.FloatField(null=True, blank=True, help_text='Low season economy price')
    typical_price_high = models.FloatField(null=True, blank=True, help_text='High season economy price')
    
    # Status
    is_active = models.BooleanField(default=True)
    seasonal = models.BooleanField(default=False)
    season_start = models.IntegerField(null=True, blank=True, help_text='Start month (1-12)')
    season_end = models.IntegerField(null=True, blank=True, help_text='End month (1-12)')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'routes'
        ordering = ['origin_code', 'destination_code']
        unique_together = ['origin_code', 'destination_code', 'airline_code']
        verbose_name = 'Route'
        verbose_name_plural = 'Routes'
    
    def __str__(self):
        airline = f" ({self.airline_code})" if self.airline_code else ""
        return f"{self.origin_code} → {self.destination_code}{airline}"
    
    @property
    def route_code(self):
        return f"{self.origin_code}-{self.destination_code}"


class Aircraft(models.Model):
    """
    Aircraft types reference
    """
    AIRCRAFT_TYPES = [
        ('narrow_body', 'Narrow Body'),
        ('wide_body', 'Wide Body'),
        ('regional', 'Regional'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Codes
    iata_code = models.CharField(max_length=3, unique=True, help_text='IATA code (e.g., 738)')
    icao_code = models.CharField(max_length=4, blank=True, help_text='ICAO code (e.g., B738)')
    
    # Names
    name = models.CharField(max_length=255, help_text='e.g., Boeing 737-800')
    manufacturer = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    
    # Specs
    typical_seats = models.IntegerField(null=True, blank=True)
    range_km = models.IntegerField(null=True, blank=True)
    cruise_speed_kmh = models.IntegerField(null=True, blank=True)
    
    aircraft_type = models.CharField(max_length=50, choices=AIRCRAFT_TYPES, default='narrow_body')
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'aircraft'
        ordering = ['manufacturer', 'name']
        verbose_name = 'Aircraft'
        verbose_name_plural = 'Aircraft'
    
    def __str__(self):
        return f"{self.name} ({self.iata_code})"
