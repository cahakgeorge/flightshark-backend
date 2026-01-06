"""
Flightshark API - Main Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
import time
import logging

from app.config import settings
from app.routers import auth, flights, trips, destinations, users, health
from app.utils.database import init_db, close_db
from app.utils.redis import init_redis, close_redis
from app.utils.mongodb import init_mongodb, close_mongodb

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


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(flights.router, prefix="/flights", tags=["Flights"])
app.include_router(trips.router, prefix="/trips", tags=["Trips"])
app.include_router(destinations.router, prefix="/destinations", tags=["Destinations"])
app.include_router(users.router, prefix="/users", tags=["Users"])


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Flightshark API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs" if settings.DEBUG else "disabled",
    }

