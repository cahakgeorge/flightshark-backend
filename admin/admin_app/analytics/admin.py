"""
Analytics Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Avg
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateFilter

from .models import SearchLog, PopularRoute, ConversionEvent, DailyMetrics


@admin.register(SearchLog)
class SearchLogAdmin(ModelAdmin):
    list_display = (
        'route_display', 'departure_date', 'passengers', 
        'results_count', 'price_display', 'performance_display', 'created_at'
    )
    list_filter = (
        'origin_code', 
        'destination_code', 
        'cache_hit',
        ('created_at', RangeDateFilter),
    )
    search_fields = ('origin_code', 'destination_code', 'session_id')
    readonly_fields = (
        'id', 'origin_code', 'destination_code', 'departure_date', 'return_date',
        'passengers', 'cabin_class', 'results_count', 'lowest_price', 'average_price',
        'user_id', 'session_id', 'ip_country', 'device_type', 
        'response_time_ms', 'cache_hit', 'created_at'
    )
    
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def route_display(self, obj):
        return format_html(
            '<strong>{}</strong> → <strong>{}</strong>',
            obj.origin_code,
            obj.destination_code
        )
    route_display.short_description = 'Route'
    
    def price_display(self, obj):
        if obj.lowest_price:
            return format_html(
                '<span style="color: #10b981;">€{}</span>',
                obj.lowest_price
            )
        return '-'
    price_display.short_description = 'Lowest'
    
    def performance_display(self, obj):
        if obj.response_time_ms:
            color = '#10b981' if obj.response_time_ms < 500 else '#f59e0b' if obj.response_time_ms < 1000 else '#ef4444'
            cache = '✓' if obj.cache_hit else '✗'
            return format_html(
                '<span style="color: {};">{}ms</span> <span title="Cache hit">{}</span>',
                color,
                obj.response_time_ms,
                cache
            )
        return '-'
    performance_display.short_description = 'Performance'


@admin.register(PopularRoute)
class PopularRouteAdmin(ModelAdmin):
    list_display = (
        'rank_display', 'route_display', 'period_type', 'period_start',
        'search_count', 'unique_users', 'price_display', 'rank_change_display'
    )
    list_filter = ('period_type', 'origin_code', ('period_start', RangeDateFilter))
    search_fields = ('origin_code', 'destination_code')
    readonly_fields = (
        'id', 'origin_code', 'destination_code', 'period_type', 'period_start',
        'search_count', 'unique_users', 'avg_price', 'min_price', 
        'rank', 'rank_change', 'created_at'
    )
    
    ordering = ['-period_start', 'rank']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def rank_display(self, obj):
        return format_html(
            '<span style="background: #f0f9ff; padding: 4px 10px; border-radius: 20px; font-weight: bold;">#{}</span>',
            obj.rank
        )
    rank_display.short_description = '#'
    
    def route_display(self, obj):
        return format_html(
            '<strong>{}</strong> → <strong>{}</strong>',
            obj.origin_code,
            obj.destination_code
        )
    route_display.short_description = 'Route'
    
    def price_display(self, obj):
        if obj.avg_price:
            return f'€{obj.avg_price} (min: €{obj.min_price})'
        return '-'
    price_display.short_description = 'Price'
    
    def rank_change_display(self, obj):
        if obj.rank_change > 0:
            return format_html(
                '<span style="color: #10b981;">↑{}</span>',
                obj.rank_change
            )
        elif obj.rank_change < 0:
            return format_html(
                '<span style="color: #ef4444;">↓{}</span>',
                abs(obj.rank_change)
            )
        return '-'
    rank_change_display.short_description = 'Change'


@admin.register(ConversionEvent)
class ConversionEventAdmin(ModelAdmin):
    list_display = ('event_badge', 'route', 'price', 'affiliate', 'session_id', 'created_at')
    list_filter = ('event_type', ('created_at', RangeDateFilter))
    search_fields = ('session_id', 'route', 'affiliate')
    readonly_fields = (
        'id', 'event_type', 'user_id', 'session_id', 'route', 
        'price', 'affiliate', 'metadata', 'created_at'
    )
    
    date_hierarchy = 'created_at'
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def event_badge(self, obj):
        colors = {
            'search': '#6366f1',
            'view_results': '#8b5cf6',
            'select_flight': '#ec4899',
            'click_affiliate': '#10b981',
            'create_trip': '#f59e0b',
            'invite_member': '#06b6d4',
            'set_alert': '#f97316',
        }
        color = colors.get(obj.event_type, '#666')
        return format_html(
            '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_event_type_display()
        )
    event_badge.short_description = 'Event'


@admin.register(DailyMetrics)
class DailyMetricsAdmin(ModelAdmin):
    list_display = (
        'date', 'users_display', 'searches_display', 'trips_display', 
        'alerts_display', 'revenue_display', 'performance_display'
    )
    list_filter = (('date', RangeDateFilter),)
    readonly_fields = (
        'id', 'date', 'total_users', 'new_users', 'active_users',
        'total_searches', 'unique_routes_searched', 'trips_created', 'trip_members_added',
        'alerts_created', 'alerts_triggered', 'affiliate_clicks', 'estimated_revenue',
        'avg_response_time_ms', 'cache_hit_rate', 'created_at'
    )
    
    ordering = ['-date']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def users_display(self, obj):
        return format_html(
            '<span title="Total: {} | New: {} | Active: {}">'
            '👤 {} <span style="color: #10b981;">(+{})</span></span>',
            obj.total_users, obj.new_users, obj.active_users,
            obj.active_users, obj.new_users
        )
    users_display.short_description = 'Users'
    
    def searches_display(self, obj):
        return format_html(
            '<span title="Routes: {}">🔍 {}</span>',
            obj.unique_routes_searched,
            obj.total_searches
        )
    searches_display.short_description = 'Searches'
    
    def trips_display(self, obj):
        return format_html(
            '<span title="Members added: {}">✈️ {}</span>',
            obj.trip_members_added,
            obj.trips_created
        )
    trips_display.short_description = 'Trips'
    
    def alerts_display(self, obj):
        return format_html(
            '<span title="Triggered: {}">🔔 {}</span>',
            obj.alerts_triggered,
            obj.alerts_created
        )
    alerts_display.short_description = 'Alerts'
    
    def revenue_display(self, obj):
        if obj.estimated_revenue:
            return format_html(
                '<span style="color: #10b981; font-weight: bold;">€{}</span> <span style="font-size: 11px;">({} clicks)</span>',
                obj.estimated_revenue,
                obj.affiliate_clicks
            )
        return '-'
    revenue_display.short_description = 'Revenue'
    
    def performance_display(self, obj):
        if obj.avg_response_time_ms:
            color = '#10b981' if obj.avg_response_time_ms < 500 else '#f59e0b' if obj.avg_response_time_ms < 1000 else '#ef4444'
            return format_html(
                '<span style="color: {};">{}ms</span> <span style="font-size: 11px;">({:.0f}% cache)</span>',
                color,
                obj.avg_response_time_ms,
                obj.cache_hit_rate or 0
            )
        return '-'
    performance_display.short_description = 'Perf'

