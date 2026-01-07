"""
Destination & Reference Data Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import (
    Destination, DestinationTag, BestBookingTime,
    Airport, Airline, Route, Aircraft
)


# ===================
# RESOURCES (Import/Export)
# ===================

class DestinationResource(resources.ModelResource):
    class Meta:
        model = Destination
        fields = ('id', 'city', 'country', 'airport_code', 'description', 
                  'tags', 'highlights', 'best_time_to_visit', 'average_price',
                  'image_url', 'is_active', 'is_featured')
        import_id_fields = ['airport_code']


class AirportResource(resources.ModelResource):
    class Meta:
        model = Airport
        fields = ('iata_code', 'icao_code', 'name', 'city', 'country', 
                  'country_code', 'latitude', 'longitude', 'timezone',
                  'is_major', 'is_active')
        import_id_fields = ['iata_code']


class AirlineResource(resources.ModelResource):
    class Meta:
        model = Airline
        fields = ('iata_code', 'icao_code', 'name', 'country', 'country_code',
                  'logo_url', 'alliance', 'is_low_cost', 'is_active')
        import_id_fields = ['iata_code']


class RouteResource(resources.ModelResource):
    class Meta:
        model = Route
        fields = ('origin_code', 'destination_code', 'airline_code',
                  'typical_duration_minutes', 'distance_km',
                  'typical_price_low', 'typical_price_high', 'is_active')


# ===================
# INLINES
# ===================

class BestBookingTimeInline(TabularInline):
    model = BestBookingTime
    extra = 0
    fields = ('days_before_departure', 'best_day_of_week', 'best_month', 'average_savings')


# ===================
# DESTINATION ADMIN
# ===================

@admin.register(DestinationTag)
class DestinationTagAdmin(ModelAdmin):
    list_display = ('display_name', 'slug', 'color_preview', 'is_active', 'display_order')
    list_editable = ('is_active', 'display_order')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('display_order', 'name')
    
    def display_name(self, obj):
        return f"{obj.emoji} {obj.name}" if obj.emoji else obj.name
    display_name.short_description = 'Name'
    
    def color_preview(self, obj):
        return format_html(
            '<span style="background-color: {}; padding: 2px 12px; border-radius: 4px;">&nbsp;</span>',
            obj.color
        )
    color_preview.short_description = 'Color'


@admin.register(Destination)
class DestinationAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = DestinationResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    
    list_display = (
        'city', 'country', 'airport_code', 'tag_display', 
        'average_price_display', 'is_active', 'is_featured', 'image_preview'
    )
    list_filter = ('is_active', 'is_featured', 'country')
    search_fields = ('city', 'country', 'airport_code', 'tags')
    list_editable = ('is_active', 'is_featured')
    readonly_fields = ('id', 'created_at', 'updated_at', 'image_preview_large')
    
    inlines = [BestBookingTimeInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('city', 'country', 'airport_code'),
        }),
        ('Content', {
            'fields': ('description', 'tags', 'highlights', 'best_time_to_visit'),
        }),
        ('Pricing', {
            'fields': ('average_price',),
        }),
        ('Media', {
            'fields': ('image_url', 'hero_image', 'image_preview_large'),
        }),
        ('Status', {
            'fields': ('is_active', 'is_featured'),
        }),
        ('Metadata', {
            'fields': ('extra_data',),
            'classes': ('collapse',),
        }),
        ('System', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def tag_display(self, obj):
        if not obj.tags:
            return '-'
        return format_html(
            ' '.join([
                f'<span style="background: #e0f2fe; padding: 2px 8px; border-radius: 12px; font-size: 11px; margin-right: 4px;">{tag}</span>'
                for tag in obj.tags[:3]
            ])
        )
    tag_display.short_description = 'Tags'
    
    def average_price_display(self, obj):
        if obj.average_price:
            return f'€{obj.average_price}'
        return '-'
    average_price_display.short_description = 'Avg Price'
    
    def image_preview(self, obj):
        url = obj.hero_image.url if obj.hero_image else obj.image_url
        if url:
            return format_html(
                '<img src="{}" style="width: 60px; height: 40px; object-fit: cover; border-radius: 4px;" />',
                url
            )
        return '-'
    image_preview.short_description = 'Image'
    
    def image_preview_large(self, obj):
        url = obj.hero_image.url if obj.hero_image else obj.image_url
        if url:
            return format_html(
                '<img src="{}" style="max-width: 400px; max-height: 300px; border-radius: 8px;" />',
                url
            )
        return 'No image'
    image_preview_large.short_description = 'Preview'


@admin.register(BestBookingTime)
class BestBookingTimeAdmin(ModelAdmin):
    list_display = ('destination', 'days_before_departure', 'best_day_of_week', 'best_month', 'average_savings')
    list_filter = ('best_day_of_week', 'best_month')
    search_fields = ('destination__city', 'destination__airport_code')
    autocomplete_fields = ['destination']


# ===================
# AIRPORT ADMIN
# ===================

@admin.register(Airport)
class AirportAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = AirportResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    
    list_display = (
        'iata_code', 'name', 'city', 'country_code', 
        'is_major_badge', 'is_active', 'coordinates'
    )
    list_filter = ('is_active', 'is_major', 'country_code', 'airport_type')
    search_fields = ('iata_code', 'icao_code', 'name', 'city', 'country')
    list_editable = ('is_active',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('city', 'name')
    
    fieldsets = (
        ('Codes', {
            'fields': ('iata_code', 'icao_code'),
        }),
        ('Location', {
            'fields': ('name', 'city', 'country', 'country_code'),
        }),
        ('Coordinates', {
            'fields': ('latitude', 'longitude', 'timezone', 'altitude_ft'),
        }),
        ('Status', {
            'fields': ('airport_type', 'is_active', 'is_major'),
        }),
        ('System', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def is_major_badge(self, obj):
        if obj.is_major:
            return format_html(
                '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">Major</span>'
            )
        return '-'
    is_major_badge.short_description = 'Major'
    
    def coordinates(self, obj):
        if obj.latitude and obj.longitude:
            return f"{obj.latitude:.4f}, {obj.longitude:.4f}"
        return '-'
    coordinates.short_description = 'Lat/Long'
    
    actions = ['mark_as_major', 'mark_as_regular']
    
    @admin.action(description='Mark as major airport')
    def mark_as_major(self, request, queryset):
        queryset.update(is_major=True)
    
    @admin.action(description='Mark as regular airport')
    def mark_as_regular(self, request, queryset):
        queryset.update(is_major=False)


# ===================
# AIRLINE ADMIN
# ===================

@admin.register(Airline)
class AirlineAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = AirlineResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    
    list_display = (
        'logo_preview', 'iata_code', 'name', 'country_code',
        'alliance_badge', 'type_badge', 'rating_display', 'is_active'
    )
    list_filter = ('is_active', 'is_low_cost', 'alliance', 'airline_type', 'country_code')
    search_fields = ('iata_code', 'icao_code', 'name', 'country')
    list_editable = ('is_active',)
    readonly_fields = ('id', 'created_at', 'updated_at', 'logo_preview_large')
    ordering = ('name',)
    
    fieldsets = (
        ('Codes', {
            'fields': ('iata_code', 'icao_code'),
        }),
        ('Information', {
            'fields': ('name', 'full_name', 'country', 'country_code'),
        }),
        ('Branding', {
            'fields': ('logo_url', 'logo_preview_large', 'primary_color'),
        }),
        ('Classification', {
            'fields': ('airline_type', 'alliance', 'is_low_cost'),
        }),
        ('Contact', {
            'fields': ('website', 'phone'),
        }),
        ('Operations', {
            'fields': ('hub_airports', 'fleet_size'),
        }),
        ('Ratings', {
            'fields': ('rating', 'on_time_performance'),
        }),
        ('Status', {
            'fields': ('is_active',),
        }),
        ('System', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def logo_preview(self, obj):
        if obj.logo_url:
            return format_html(
                '<img src="{}" style="width: 40px; height: 40px; object-fit: contain;" />',
                obj.logo_url
            )
        return '-'
    logo_preview.short_description = 'Logo'
    
    def logo_preview_large(self, obj):
        if obj.logo_url:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 100px;" />',
                obj.logo_url
            )
        return 'No logo'
    logo_preview_large.short_description = 'Logo Preview'
    
    def alliance_badge(self, obj):
        if obj.alliance:
            colors = {
                'Star Alliance': '#1a1a1a',
                'Oneworld': '#e31837',
                'SkyTeam': '#004990',
            }
            color = colors.get(obj.alliance, '#666')
            return format_html(
                '<span style="background: {}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
                color, obj.alliance
            )
        return '-'
    alliance_badge.short_description = 'Alliance'
    
    def type_badge(self, obj):
        if obj.is_low_cost:
            return format_html(
                '<span style="background: #f59e0b; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px;">Low Cost</span>'
            )
        return '-'
    type_badge.short_description = 'Type'
    
    def rating_display(self, obj):
        if obj.rating:
            return f"⭐ {obj.rating:.1f}"
        return '-'
    rating_display.short_description = 'Rating'


# ===================
# ROUTE ADMIN
# ===================

@admin.register(Route)
class RouteAdmin(ModelAdmin, ImportExportModelAdmin):
    resource_class = RouteResource
    import_form_class = ImportForm
    export_form_class = ExportForm
    
    list_display = (
        'route_display', 'airline_code', 'duration_display',
        'distance_display', 'price_display', 'is_direct', 'is_active'
    )
    list_filter = ('is_active', 'is_direct', 'seasonal', 'airline_code')
    search_fields = ('origin_code', 'destination_code', 'airline_code')
    list_editable = ('is_active',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    ordering = ('origin_code', 'destination_code')
    
    fieldsets = (
        ('Route', {
            'fields': ('origin_code', 'destination_code', 'airline_code'),
        }),
        ('Details', {
            'fields': ('is_direct', 'typical_duration_minutes', 'distance_km'),
        }),
        ('Schedule', {
            'fields': ('flights_per_week', 'operates_days'),
        }),
        ('Pricing', {
            'fields': ('typical_price_low', 'typical_price_high'),
        }),
        ('Seasonal', {
            'fields': ('seasonal', 'season_start', 'season_end'),
        }),
        ('Status', {
            'fields': ('is_active',),
        }),
        ('System', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def route_display(self, obj):
        return format_html(
            '<strong>{}</strong> → <strong>{}</strong>',
            obj.origin_code, obj.destination_code
        )
    route_display.short_description = 'Route'
    
    def duration_display(self, obj):
        if obj.typical_duration_minutes:
            hours = obj.typical_duration_minutes // 60
            mins = obj.typical_duration_minutes % 60
            return f"{hours}h {mins}m"
        return '-'
    duration_display.short_description = 'Duration'
    
    def distance_display(self, obj):
        if obj.distance_km:
            return f"{obj.distance_km:,} km"
        return '-'
    distance_display.short_description = 'Distance'
    
    def price_display(self, obj):
        if obj.typical_price_low and obj.typical_price_high:
            return f"€{obj.typical_price_low:.0f} - €{obj.typical_price_high:.0f}"
        return '-'
    price_display.short_description = 'Price Range'


# ===================
# AIRCRAFT ADMIN
# ===================

@admin.register(Aircraft)
class AircraftAdmin(ModelAdmin):
    list_display = (
        'iata_code', 'name', 'manufacturer', 
        'typical_seats', 'aircraft_type', 'is_active'
    )
    list_filter = ('is_active', 'aircraft_type', 'manufacturer')
    search_fields = ('iata_code', 'icao_code', 'name', 'manufacturer')
    list_editable = ('is_active',)
    readonly_fields = ('id', 'created_at')
    ordering = ('manufacturer', 'name')
    
    fieldsets = (
        ('Codes', {
            'fields': ('iata_code', 'icao_code'),
        }),
        ('Information', {
            'fields': ('name', 'manufacturer', 'model'),
        }),
        ('Specifications', {
            'fields': ('typical_seats', 'range_km', 'cruise_speed_kmh', 'aircraft_type'),
        }),
        ('Status', {
            'fields': ('is_active',),
        }),
        ('System', {
            'fields': ('id', 'created_at'),
            'classes': ('collapse',),
        }),
    )
