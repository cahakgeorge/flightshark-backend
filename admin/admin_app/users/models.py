"""
User & Trip Models for Django Admin
These mirror the FastAPI models for admin management
"""
from django.db import models
import uuid


class FlightsharkUser(models.Model):
    """
    Application users (separate from Django admin users)
    This mirrors the 'users' table used by FastAPI
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255, blank=True)
    
    # Home location
    home_city = models.CharField(max_length=100, blank=True)
    home_airport_code = models.CharField(max_length=10, blank=True)
    
    # Preferences stored as JSON
    preferences = models.JSONField(default=dict, blank=True)
    
    # Account status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
        verbose_name = 'Flightshark User'
        verbose_name_plural = 'Flightshark Users'
    
    def __str__(self):
        return self.email
    
    @property
    def trip_count(self):
        return self.trips_owned.count() + self.trip_memberships.count()


class Trip(models.Model):
    """
    Group trips
    """
    STATUS_CHOICES = [
        ('planning', 'Planning'),
        ('booked', 'Booked'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        FlightsharkUser, 
        on_delete=models.CASCADE, 
        related_name='trips_owned'
    )
    
    name = models.CharField(max_length=255)
    destination_code = models.CharField(max_length=10, db_index=True)
    destination_name = models.CharField(max_length=255, blank=True)
    
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='planning')
    
    # Trip metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'trips'
        ordering = ['-created_at']
        verbose_name = 'Trip'
        verbose_name_plural = 'Trips'
    
    def __str__(self):
        return f"{self.name} - {self.destination_code}"
    
    @property
    def member_count(self):
        return self.members.count()


class TripMember(models.Model):
    """
    Members of a group trip
    """
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('member', 'Member'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(
        FlightsharkUser, 
        on_delete=models.CASCADE, 
        related_name='trip_memberships',
        null=True,
        blank=True
    )
    
    # Origin for this member
    origin_city = models.CharField(max_length=100)
    origin_airport_code = models.CharField(max_length=10, blank=True)
    
    # Status
    role = models.CharField(max_length=50, choices=ROLE_CHOICES, default='member')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    
    # Invitation
    invited_email = models.EmailField(blank=True, help_text='Email if not a registered user')
    invited_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'trip_members'
        unique_together = ['trip', 'user']
        verbose_name = 'Trip Member'
        verbose_name_plural = 'Trip Members'
    
    def __str__(self):
        return f"{self.user or self.invited_email} - {self.trip.name}"


class PriceAlert(models.Model):
    """
    Price alerts set by users
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        FlightsharkUser, 
        on_delete=models.CASCADE, 
        related_name='price_alerts'
    )
    
    origin_code = models.CharField(max_length=10)
    destination_code = models.CharField(max_length=10)
    
    target_price = models.DecimalField(max_digits=10, decimal_places=2)
    current_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    is_active = models.BooleanField(default=True)
    
    # Tracking
    times_triggered = models.IntegerField(default=0)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'price_alerts'
        ordering = ['-created_at']
        verbose_name = 'Price Alert'
        verbose_name_plural = 'Price Alerts'
    
    def __str__(self):
        return f"{self.origin_code} → {self.destination_code} (€{self.target_price})"
    
    @property
    def route(self):
        return f"{self.origin_code} → {self.destination_code}"
    
    @property
    def price_met(self):
        if self.current_price and self.target_price:
            return self.current_price <= self.target_price
        return False


class EmergencyContact(models.Model):
    """
    Emergency contacts for flight notifications
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        FlightsharkUser,
        on_delete=models.CASCADE,
        related_name='emergency_contacts'
    )
    
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    relationship = models.CharField(max_length=100, blank=True)
    
    notify_on_departure = models.BooleanField(default=True)
    notify_on_arrival = models.BooleanField(default=True)
    
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'emergency_contacts'
        verbose_name = 'Emergency Contact'
        verbose_name_plural = 'Emergency Contacts'
    
    def __str__(self):
        return f"{self.name} ({self.user.email})"

