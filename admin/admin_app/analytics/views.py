"""
Analytics API Views
"""
from django.http import JsonResponse
from django.db.models import Count, Sum, Avg
from django.utils import timezone
from datetime import timedelta

from .models import SearchLog, PopularRoute, DailyMetrics


def dashboard_stats(request):
    """
    Return dashboard statistics for the admin interface
    """
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Get recent metrics
    recent_metrics = DailyMetrics.objects.filter(date__gte=week_ago).order_by('-date')
    
    # Calculate totals
    totals = recent_metrics.aggregate(
        total_searches=Sum('total_searches'),
        total_new_users=Sum('new_users'),
        total_trips=Sum('trips_created'),
        total_revenue=Sum('estimated_revenue'),
        avg_response=Avg('avg_response_time_ms'),
    )
    
    # Today's stats
    today_metrics = DailyMetrics.objects.filter(date=today).first()
    
    return JsonResponse({
        'today': {
            'active_users': today_metrics.active_users if today_metrics else 0,
            'searches': today_metrics.total_searches if today_metrics else 0,
            'trips': today_metrics.trips_created if today_metrics else 0,
            'revenue': float(today_metrics.estimated_revenue) if today_metrics else 0,
        },
        'week': {
            'searches': totals['total_searches'] or 0,
            'new_users': totals['total_new_users'] or 0,
            'trips': totals['total_trips'] or 0,
            'revenue': float(totals['total_revenue']) if totals['total_revenue'] else 0,
            'avg_response_ms': int(totals['avg_response']) if totals['avg_response'] else 0,
        },
        'trend': list(recent_metrics.values('date', 'total_searches', 'active_users', 'estimated_revenue')),
    })


def popular_routes(request):
    """
    Return popular routes for the current period
    """
    period = request.GET.get('period', 'week')
    limit = int(request.GET.get('limit', 10))
    
    routes = PopularRoute.objects.filter(
        period_type=period
    ).order_by('rank')[:limit]
    
    return JsonResponse({
        'period': period,
        'routes': [
            {
                'rank': r.rank,
                'origin': r.origin_code,
                'destination': r.destination_code,
                'searches': r.search_count,
                'users': r.unique_users,
                'avg_price': float(r.avg_price) if r.avg_price else None,
                'change': r.rank_change,
            }
            for r in routes
        ]
    })

