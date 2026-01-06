"""
Destination Admin Configuration
"""
from django.contrib import admin
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from import_export import resources
from import_export.admin import ImportExportModelAdmin

from .models import Destination, DestinationTag, BestBookingTime


class DestinationResource(resources.ModelResource):
    """Import/Export resource for destinations"""
    class Meta:
        model = Destination
        fields = ('id', 'city', 'country', 'airport_code', 'description', 
                  'tags', 'highlights', 'best_time_to_visit', 'average_price',
                  'image_url', 'is_active', 'is_featured')
        import_id_fields = ['airport_code']


class BestBookingTimeInline(TabularInline):
    model = BestBookingTime
    extra = 0
    fields = ('days_before_departure', 'best_day_of_week', 'best_month', 'average_savings')


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
            'fields': ('metadata',),
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
    
    actions = ['make_featured', 'make_unfeatured', 'activate', 'deactivate']
    
    @admin.action(description='Mark as featured')
    def make_featured(self, request, queryset):
        queryset.update(is_featured=True)
    
    @admin.action(description='Remove from featured')
    def make_unfeatured(self, request, queryset):
        queryset.update(is_featured=False)
    
    @admin.action(description='Activate destinations')
    def activate(self, request, queryset):
        queryset.update(is_active=True)
    
    @admin.action(description='Deactivate destinations')
    def deactivate(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(BestBookingTime)
class BestBookingTimeAdmin(ModelAdmin):
    list_display = ('destination', 'days_before_departure', 'best_day_of_week', 'best_month', 'average_savings')
    list_filter = ('best_day_of_week', 'best_month')
    search_fields = ('destination__city', 'destination__airport_code')
    autocomplete_fields = ['destination']
