"""Database engine and session dependency."""

import logging
from collections.abc import AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    pool_size=10,
    max_overflow=5,
    pool_timeout=10,
    pool_pre_ping=True,  # ตรวจสอบ connection ก่อนใช้ — ป้องกัน stale connection
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async database session."""
    try:
        async with AsyncSessionLocal() as session:
            yield session
    except (OperationalError, SQLAlchemyError) as exc:
        logger.error("Database error: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    except (ConnectionRefusedError, OSError) as exc:
        logger.error("Database connection refused: %s", exc)
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
