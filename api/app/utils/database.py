"""
PostgreSQL Database Connection & Session Management
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, QueuePool
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Create async engine with performance optimizations
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_timeout=10,  # Wait max 10 seconds for a connection from pool
    connect_args={
        "command_timeout": 30,  # Query timeout in seconds
        "server_settings": {
            "statement_timeout": "30000",  # 30 seconds max per statement
        }
    },
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def init_db():
    """Initialize database connection"""
    logger.info("Initializing PostgreSQL connection...")
    # Test connection
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: None)
    logger.info("PostgreSQL connection established")


async def close_db():
    """Close database connection"""
    logger.info("Closing PostgreSQL connection...")
    await engine.dispose()
    logger.info("PostgreSQL connection closed")


async def get_db() -> AsyncSession:
    """
    Dependency that provides a database session
    Usage: db: AsyncSession = Depends(get_db)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

