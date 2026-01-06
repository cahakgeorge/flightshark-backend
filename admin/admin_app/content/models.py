"""
Social Content Models for Django Admin
"""
from django.db import models
import uuid


class SocialContent(models.Model):
    """
    Social media content about destinations (TikTok, Instagram, Twitter)
    This is managed/moderated via Django Admin
    """
    PLATFORM_CHOICES = [
        ('tiktok', 'TikTok'),
        ('instagram', 'Instagram'),
        ('twitter', 'Twitter/X'),
        ('youtube', 'YouTube'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Platform info
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    content_id = models.CharField(max_length=255, help_text='Platform-specific content ID')
    url = models.URLField(max_length=500)
    
    # Content details
    caption = models.TextField(blank=True)
    creator = models.CharField(max_length=255, blank=True)
    creator_url = models.URLField(max_length=500, blank=True)
    thumbnail_url = models.URLField(max_length=500, blank=True)
    
    # Destination linking
    destination_code = models.CharField(max_length=10, db_index=True)
    destination_name = models.CharField(max_length=255, blank=True)
    
    # Engagement metrics
    views = models.BigIntegerField(default=0)
    likes = models.BigIntegerField(default=0)
    comments = models.BigIntegerField(default=0)
    shares = models.BigIntegerField(default=0)
    
    # Tags
    tags = models.JSONField(default=list, blank=True)
    
    # Moderation
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    moderation_notes = models.TextField(blank=True)
    moderated_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='moderated_content'
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    scraped_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'social_content'
        ordering = ['-scraped_at']
        unique_together = ['platform', 'content_id']
        verbose_name = 'Social Content'
        verbose_name_plural = 'Social Content'
    
    def __str__(self):
        return f"{self.platform} - {self.destination_code} - {self.creator}"
    
    @property
    def engagement_score(self):
        """Calculate engagement score"""
        return self.likes + (self.comments * 2) + (self.shares * 3)
    
    @property
    def is_expired(self):
        from django.utils import timezone
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False


class ContentCuration(models.Model):
    """
    Manually curated content collections
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    
    destination_code = models.CharField(max_length=10, blank=True, db_index=True)
    
    content_items = models.ManyToManyField(
        SocialContent,
        related_name='curations',
        blank=True
    )
    
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='content_curations'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'content_curations'
        ordering = ['display_order', 'name']
        verbose_name = 'Content Curation'
        verbose_name_plural = 'Content Curations'
    
    def __str__(self):
        return self.name
