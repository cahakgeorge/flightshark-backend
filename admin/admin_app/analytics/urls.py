"""
Analytics API URLs
"""
from django.urls import path
from . import views

urlpatterns = [
    path('stats/', views.dashboard_stats, name='dashboard_stats'),
    path('popular-routes/', views.popular_routes, name='popular_routes'),
]

