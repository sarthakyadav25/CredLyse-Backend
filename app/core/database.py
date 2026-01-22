"""
Database Configuration

Async SQLAlchemy 2.0 setup with asyncpg driver for PostgreSQL/NeonDB.
"""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    
    All models should inherit from this class.
    """
    pass


# Module-level engine instance (lazily initialized)
_engine: Optional[AsyncEngine] = None
_async_session_maker: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """
    Get or create the async engine.
    
    Lazy initialization to avoid import-time database connection issues.
    Handles SSL configuration for NeonDB/asyncpg compatibility.
    """
    global _engine
    if _engine is None:
        import ssl
        from app.core.config import settings
        
        # Get the database URL and strip query parameters for asyncpg
        # (asyncpg doesn't accept sslmode/channel_binding params in URL)
        db_url = settings.DATABASE_URL
        if "?" in db_url:
            db_url = db_url.split("?")[0]
        
        # Create SSL context for NeonDB
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        _engine = create_async_engine(
            db_url,
            echo=settings.is_development,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=40,
            connect_args={"ssl": ssl_context},
        )
    return _engine


def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        _async_session_maker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    
    Usage in FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...
    
    Yields:
        AsyncSession: An async database session.
    """
    session_maker = get_session_maker()
    async with session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize database tables.
    
    Note: In production, use Alembic migrations instead.
    This is useful for testing or initial development.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
