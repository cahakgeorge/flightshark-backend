"""
Analytics Models for Django Admin
"""
from django.db import models
import uuid


class SearchLog(models.Model):
    """
    Log of all flight searches for analytics
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Route
    origin_code = models.CharField(max_length=10, db_index=True)
    destination_code = models.CharField(max_length=10, db_index=True)
    
    # Search parameters
    departure_date = models.DateField(null=True, blank=True)
    return_date = models.DateField(null=True, blank=True)
    passengers = models.IntegerField(default=1)
    cabin_class = models.CharField(max_length=50, blank=True)
    
    # Results
    results_count = models.IntegerField(default=0)
    lowest_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    average_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # User info (anonymized)
    user_id = models.UUIDField(null=True, blank=True)
    session_id = models.CharField(max_length=100, blank=True)
    ip_country = models.CharField(max_length=2, blank=True)
    device_type = models.CharField(max_length=50, blank=True)
    
    # Performance
    response_time_ms = models.IntegerField(null=True, blank=True)
    cache_hit = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'search_logs'
        ordering = ['-created_at']
        verbose_name = 'Search Log'
        verbose_name_plural = 'Search Logs'
        indexes = [
            models.Index(fields=['origin_code', 'destination_code']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.origin_code} → {self.destination_code} ({self.created_at.date()})"
    
    @property
    def route(self):
        return f"{self.origin_code} → {self.destination_code}"


class PopularRoute(models.Model):
    """
    Aggregated popular routes (calculated by background jobs)
    """
    PERIOD_CHOICES = [
        ('day', 'Daily'),
        ('week', 'Weekly'),
        ('month', 'Monthly'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    origin_code = models.CharField(max_length=10, db_index=True)
    destination_code = models.CharField(max_length=10, db_index=True)
    
    period_type = models.CharField(max_length=10, choices=PERIOD_CHOICES)
    period_start = models.DateField()
    
    # Metrics
    search_count = models.IntegerField(default=0)
    unique_users = models.IntegerField(default=0)
    avg_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Ranking
    rank = models.IntegerField(default=0)
    rank_change = models.IntegerField(default=0, help_text='Change from previous period')
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'popular_routes'
        ordering = ['-period_start', 'rank']
        unique_together = ['origin_code', 'destination_code', 'period_type', 'period_start']
        verbose_name = 'Popular Route'
        verbose_name_plural = 'Popular Routes'
    
    def __str__(self):
        return f"#{self.rank} {self.origin_code} → {self.destination_code} ({self.period_type})"


class ConversionEvent(models.Model):
    """
    Track conversion funnel events
    """
    EVENT_TYPES = [
        ('search', 'Flight Search'),
        ('view_results', 'View Results'),
        ('select_flight', 'Select Flight'),
        ('click_affiliate', 'Click Affiliate Link'),
        ('create_trip', 'Create Trip'),
        ('invite_member', 'Invite Trip Member'),
        ('set_alert', 'Set Price Alert'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    event_type = models.CharField(max_length=50, choices=EVENT_TYPES)
    
    user_id = models.UUIDField(null=True, blank=True)
    session_id = models.CharField(max_length=100)
    
    # Event data
    route = models.CharField(max_length=20, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    affiliate = models.CharField(max_length=100, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = 'conversion_events'
        ordering = ['-created_at']
        verbose_name = 'Conversion Event'
        verbose_name_plural = 'Conversion Events'
    
    def __str__(self):
        return f"{self.event_type} - {self.created_at}"


class DailyMetrics(models.Model):
    """
    Daily aggregated metrics for dashboard
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField(unique=True)
    
    # User metrics
    total_users = models.IntegerField(default=0)
    new_users = models.IntegerField(default=0)
    active_users = models.IntegerField(default=0)
    
    # Search metrics
    total_searches = models.IntegerField(default=0)
    unique_routes_searched = models.IntegerField(default=0)
    
    # Trip metrics
    trips_created = models.IntegerField(default=0)
    trip_members_added = models.IntegerField(default=0)
    
    # Alert metrics
    alerts_created = models.IntegerField(default=0)
    alerts_triggered = models.IntegerField(default=0)
    
    # Conversion metrics
    affiliate_clicks = models.IntegerField(default=0)
    estimated_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Performance metrics
    avg_response_time_ms = models.IntegerField(null=True, blank=True)
    cache_hit_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'daily_metrics'
        ordering = ['-date']
        verbose_name = 'Daily Metrics'
        verbose_name_plural = 'Daily Metrics'
    
    def __str__(self):
        return f"Metrics for {self.date}"

