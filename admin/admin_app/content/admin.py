"""
Content Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateFilter

from .models import SocialContent, ContentCuration


@admin.register(SocialContent)
class SocialContentAdmin(ModelAdmin):
    list_display = (
        'thumbnail_preview', 'platform_badge', 'destination_code', 
        'creator', 'engagement_display', 'status_badge', 'scraped_at'
    )
    list_filter = (
        'platform', 
        'status', 
        'destination_code',
        ('scraped_at', RangeDateFilter),
    )
    search_fields = ('caption', 'creator', 'destination_code', 'destination_name', 'tags')
    list_editable = ()
    readonly_fields = (
        'id', 'scraped_at', 'updated_at', 'thumbnail_large', 
        'engagement_score_display', 'content_preview'
    )
    
    date_hierarchy = 'scraped_at'
    
    fieldsets = (
        ('Content Info', {
            'fields': ('platform', 'content_id', 'url', 'content_preview'),
        }),
        ('Details', {
            'fields': ('caption', 'creator', 'creator_url', 'thumbnail_url', 'thumbnail_large'),
        }),
        ('Destination', {
            'fields': ('destination_code', 'destination_name'),
        }),
        ('Engagement', {
            'fields': ('views', 'likes', 'comments', 'shares', 'engagement_score_display'),
        }),
        ('Tags', {
            'fields': ('tags',),
        }),
        ('Moderation', {
            'fields': ('status', 'moderation_notes', 'moderated_by', 'moderated_at'),
        }),
        ('System', {
            'fields': ('id', 'scraped_at', 'expires_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def thumbnail_preview(self, obj):
        if obj.thumbnail_url:
            return format_html(
                '<img src="{}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 8px;" />',
                obj.thumbnail_url
            )
        return '-'
    thumbnail_preview.short_description = 'Preview'
    
    def thumbnail_large(self, obj):
        if obj.thumbnail_url:
            return format_html(
                '<img src="{}" style="max-width: 300px; max-height: 300px; border-radius: 8px;" />',
                obj.thumbnail_url
            )
        return 'No thumbnail'
    thumbnail_large.short_description = 'Thumbnail Preview'
    
    def content_preview(self, obj):
        return format_html(
            '<a href="{}" target="_blank" class="button">View on {}</a>',
            obj.url,
            obj.get_platform_display()
        )
    content_preview.short_description = 'View Content'
    
    def platform_badge(self, obj):
        colors = {
            'tiktok': '#000000',
            'instagram': '#E4405F',
            'twitter': '#1DA1F2',
            'youtube': '#FF0000',
        }
        color = colors.get(obj.platform, '#666')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_platform_display()
        )
    platform_badge.short_description = 'Platform'
    
    def status_badge(self, obj):
        colors = {
            'pending': '#f59e0b',
            'approved': '#10b981',
            'rejected': '#ef4444',
            'expired': '#6b7280',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def engagement_display(self, obj):
        return format_html(
            '<span title="Views: {} | Likes: {} | Comments: {}">'
            '❤️ {} · 💬 {} · 👁️ {}</span>',
            obj.views, obj.likes, obj.comments,
            self._format_number(obj.likes),
            self._format_number(obj.comments),
            self._format_number(obj.views)
        )
    engagement_display.short_description = 'Engagement'
    
    def engagement_score_display(self, obj):
        return f"{obj.engagement_score:,}"
    engagement_score_display.short_description = 'Engagement Score'
    
    def _format_number(self, num):
        if num >= 1_000_000:
            return f'{num / 1_000_000:.1f}M'
        if num >= 1_000:
            return f'{num / 1_000:.1f}K'
        return str(num)
    
    actions = ['approve_content', 'reject_content', 'mark_expired']
    
    @admin.action(description='Approve selected content')
    def approve_content(self, request, queryset):
        queryset.update(
            status='approved',
            moderated_by=request.user,
            moderated_at=timezone.now()
        )
        self.message_user(request, f'{queryset.count()} content items approved.')
    
    @admin.action(description='Reject selected content')
    def reject_content(self, request, queryset):
        queryset.update(
            status='rejected',
            moderated_by=request.user,
            moderated_at=timezone.now()
        )
        self.message_user(request, f'{queryset.count()} content items rejected.')
    
    @admin.action(description='Mark as expired')
    def mark_expired(self, request, queryset):
        queryset.update(status='expired')
        self.message_user(request, f'{queryset.count()} content items marked as expired.')


@admin.register(ContentCuration)
class ContentCurationAdmin(ModelAdmin):
    list_display = ('name', 'destination_code', 'content_count', 'is_active', 'display_order', 'created_by')
    list_filter = ('is_active', 'destination_code')
    search_fields = ('name', 'slug', 'description')
    list_editable = ('is_active', 'display_order')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('content_items',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'slug', 'description'),
        }),
        ('Destination', {
            'fields': ('destination_code',),
        }),
        ('Content', {
            'fields': ('content_items',),
        }),
        ('Settings', {
            'fields': ('is_active', 'display_order'),
        }),
        ('System', {
            'fields': ('id', 'created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def content_count(self, obj):
        return obj.content_items.count()
    content_count.short_description = 'Items'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
