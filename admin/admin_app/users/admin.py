"""
Users & Trips Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.filters.admin import RangeDateFilter

from .models import FlightsharkUser, Trip, TripMember, PriceAlert, EmergencyContact


class TripMemberInline(TabularInline):
    model = TripMember
    extra = 0
    fields = ('user', 'origin_city', 'origin_airport_code', 'role', 'status')
    readonly_fields = ('invited_at',)
    autocomplete_fields = ['user']


class EmergencyContactInline(TabularInline):
    model = EmergencyContact
    extra = 0
    fields = ('name', 'email', 'phone', 'notify_on_departure', 'notify_on_arrival', 'is_active')


class PriceAlertInline(TabularInline):
    model = PriceAlert
    extra = 0
    fields = ('origin_code', 'destination_code', 'target_price', 'current_price', 'is_active')
    readonly_fields = ('current_price', 'last_notified_at')


@admin.register(FlightsharkUser)
class FlightsharkUserAdmin(ModelAdmin):
    list_display = (
        'email', 'full_name', 'home_city', 'home_airport_code', 
        'trip_count_display', 'is_active', 'is_verified', 'created_at'
    )
    list_filter = ('is_active', 'is_verified', ('created_at', RangeDateFilter))
    search_fields = ('email', 'full_name', 'home_city', 'home_airport_code')
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_login_at')
    
    inlines = [PriceAlertInline, EmergencyContactInline]
    
    fieldsets = (
        ('Account', {
            'fields': ('email', 'full_name'),
        }),
        ('Location', {
            'fields': ('home_city', 'home_airport_code'),
        }),
        ('Status', {
            'fields': ('is_active', 'is_verified'),
        }),
        ('Preferences', {
            'fields': ('preferences',),
            'classes': ('collapse',),
        }),
        ('System', {
            'fields': ('id', 'created_at', 'updated_at', 'last_login_at'),
            'classes': ('collapse',),
        }),
    )
    
    def trip_count_display(self, obj):
        count = obj.trip_count
        if count > 0:
            return format_html(
                '<span style="background: #e0f2fe; padding: 2px 8px; border-radius: 12px;">{}</span>',
                count
            )
        return '0'
    trip_count_display.short_description = 'Trips'
    
    actions = ['activate_users', 'deactivate_users', 'verify_users']
    
    @admin.action(description='Activate selected users')
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
    
    @admin.action(description='Deactivate selected users')
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
    
    @admin.action(description='Mark as verified')
    def verify_users(self, request, queryset):
        queryset.update(is_verified=True)


@admin.register(Trip)
class TripAdmin(ModelAdmin):
    list_display = (
        'name', 'owner', 'destination_code', 'dates_display', 
        'member_count_display', 'status_badge', 'created_at'
    )
    list_filter = ('status', 'destination_code', ('created_at', RangeDateFilter))
    search_fields = ('name', 'destination_code', 'destination_name', 'owner__email')
    readonly_fields = ('id', 'created_at', 'updated_at')
    autocomplete_fields = ['owner']
    
    inlines = [TripMemberInline]
    
    fieldsets = (
        ('Trip Info', {
            'fields': ('name', 'owner'),
        }),
        ('Destination', {
            'fields': ('destination_code', 'destination_name'),
        }),
        ('Dates', {
            'fields': ('departure_date', 'return_date'),
        }),
        ('Status', {
            'fields': ('status',),
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',),
        }),
        ('System', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def dates_display(self, obj):
        if obj.departure_date and obj.return_date:
            return f"{obj.departure_date.strftime('%b %d')} - {obj.return_date.strftime('%b %d, %Y')}"
        elif obj.departure_date:
            return obj.departure_date.strftime('%b %d, %Y')
        return '-'
    dates_display.short_description = 'Dates'
    
    def member_count_display(self, obj):
        count = obj.member_count
        return format_html(
            '<span style="background: #f0fdf4; padding: 2px 8px; border-radius: 12px;">👥 {}</span>',
            count
        )
    member_count_display.short_description = 'Members'
    
    def status_badge(self, obj):
        colors = {
            'planning': '#f59e0b',
            'booked': '#10b981',
            'completed': '#6366f1',
            'cancelled': '#ef4444',
        }
        color = colors.get(obj.status, '#666')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'


@admin.register(PriceAlert)
class PriceAlertAdmin(ModelAdmin):
    list_display = (
        'route_display', 'user', 'target_price', 'current_price_display',
        'price_status', 'is_active', 'times_triggered', 'created_at'
    )
    list_filter = ('is_active', 'origin_code', 'destination_code', ('created_at', RangeDateFilter))
    search_fields = ('user__email', 'origin_code', 'destination_code')
    readonly_fields = ('id', 'times_triggered', 'last_notified_at', 'last_checked_at', 'created_at')
    autocomplete_fields = ['user']
    
    fieldsets = (
        ('Route', {
            'fields': ('origin_code', 'destination_code'),
        }),
        ('User', {
            'fields': ('user',),
        }),
        ('Price', {
            'fields': ('target_price', 'current_price'),
        }),
        ('Status', {
            'fields': ('is_active', 'expires_at'),
        }),
        ('Tracking', {
            'fields': ('times_triggered', 'last_notified_at', 'last_checked_at'),
            'classes': ('collapse',),
        }),
        ('System', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',),
        }),
    )
    
    def route_display(self, obj):
        return format_html(
            '<strong>{}</strong> → <strong>{}</strong>',
            obj.origin_code,
            obj.destination_code
        )
    route_display.short_description = 'Route'
    
    def current_price_display(self, obj):
        if obj.current_price:
            return f'€{obj.current_price}'
        return '-'
    current_price_display.short_description = 'Current'
    
    def price_status(self, obj):
        if obj.price_met:
            return format_html(
                '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px;">✓ Target Met</span>'
            )
        elif obj.current_price:
            diff = obj.current_price - obj.target_price
            return format_html(
                '<span style="color: #ef4444;">€{:.0f} above</span>',
                diff
            )
        return '-'
    price_status.short_description = 'Status'
    
    actions = ['activate_alerts', 'deactivate_alerts']
    
    @admin.action(description='Activate selected alerts')
    def activate_alerts(self, request, queryset):
        queryset.update(is_active=True)
    
    @admin.action(description='Deactivate selected alerts')
    def deactivate_alerts(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(EmergencyContact)
class EmergencyContactAdmin(ModelAdmin):
    list_display = ('name', 'user', 'email', 'phone', 'notify_on_departure', 'notify_on_arrival', 'is_active')
    list_filter = ('is_active', 'notify_on_departure', 'notify_on_arrival')
    search_fields = ('name', 'email', 'user__email')
    autocomplete_fields = ['user']

