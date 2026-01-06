"""
Destination Models for Django Admin
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
    metadata = models.JSONField(default=dict, blank=True)
    
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
