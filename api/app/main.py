"""
Flightshark API - Main Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, Response
import time
import logging

# Prometheus metrics
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST, REGISTRY

from app.config import settings

# Define Prometheus metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint']
)
from app.routers import auth, flights, trips, destinations, users, health, airports, airlines, admin_data, insights
from app.utils.database import init_db, close_db, AsyncSessionLocal
from app.utils.redis import init_redis, close_redis
from app.utils.mongodb import init_mongodb, close_mongodb
from app.services.airport_cache import AirportCacheService

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager - handles startup and shutdown events
    """
    # Startup
    logger.info("Starting Flightshark API...")
    
    await init_db()
    await init_redis()
    await init_mongodb()
    
    logger.info("All connections established successfully")
    
    # Preload reference data into cache for instant search
    logger.info("Preloading reference data into cache...")
    try:
        # Check if airports are already cached (from previous startup)
        cache_loaded = await AirportCacheService.is_cache_loaded()
        
        if not cache_loaded:
            # Load airports into Redis cache
            async with AsyncSessionLocal() as db:
                airport_count = await AirportCacheService.load_airports_to_cache(db)
                logger.info(f"Preloaded {airport_count} airports into cache")
        else:
            logger.info("Airport cache already loaded (from previous session)")
    except Exception as e:
        logger.warning(f"Failed to preload airport cache: {e}. Will use database fallback.")
    
    logger.info("Flightshark API ready to serve requests!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Flightshark API...")
    
    await close_db()
    await close_redis()
    await close_mongodb()
    
    logger.info("Cleanup completed")


# Create FastAPI application
app = FastAPI(
    title="Flightshark API",
    description="""
    ## Flight Search & Group Trip Planning API
    
    Flightshark helps travelers find the best flight deals and plan group trips from multiple cities.
    
    ### Features
    - 🔍 Search flights across multiple airlines
    - 👥 Plan group trips from different origin cities
    - 🎯 Discover destinations based on preferences
    - 🔔 Set price alerts and get notified
    - ✈️ Track flight prices over time
    
    ### Authentication
    This API uses JWT Bearer tokens for authentication. 
    Include the token in the Authorization header: `Bearer <token>`
    """,
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware with Prometheus metrics
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    # Record metrics (skip /metrics endpoint to avoid recursion)
    if request.url.path != "/metrics":
        endpoint = request.url.path
        method = request.method
        status = response.status_code
        
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(process_time)
    
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(flights.router, prefix="/flights", tags=["Flights"])
app.include_router(trips.router, prefix="/trips", tags=["Trips"])
app.include_router(destinations.router, prefix="/destinations", tags=["Destinations"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(airports.router, prefix="/airports", tags=["Airports"])
app.include_router(airlines.router, prefix="/airlines", tags=["Airlines"])
app.include_router(insights.router, prefix="/insights", tags=["Market Insights"])
app.include_router(admin_data.router, prefix="/admin/data", tags=["Admin - Data Seeding"])


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Flightshark API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )

