"""Async SQLAlchemy engine/session setup.

Per PLAN.md's migration decision (Section 4), schema is managed via a single
init.sql rather than a migration tool, so this module intentionally has no
ORM model classes yet -- those (and Alembic-style concerns) are out of scope
for Phase 1. Queries against api_keys/request_logs use SQLAlchemy Core
(text()) against a plain AsyncSession.
"""
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

_engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
_session_factory = async_sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    return _engine


async def get_session() -> AsyncSession:
    """Yield an AsyncSession for use as a FastAPI dependency."""
    async with _session_factory() as session:
        yield session
