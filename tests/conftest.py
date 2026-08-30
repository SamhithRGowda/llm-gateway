"""Shared test fixtures.

Uses an in-memory SQLite DB instead of Postgres for speed and zero Docker
dependency in the unit test suite, per PLAN.md Section 13's guidance ("SQLite
in-memory is acceptable for most tests if schema is simple enough to be
dialect-agnostic"). Postgres-only features from init.sql (pgcrypto/gen_random_uuid,
TIMESTAMPTZ) are swapped for SQLite-compatible equivalents here; the real
schema used at runtime is still app/db/migrations/init.sql against Postgres.

Phase 5 note: the `client` fixture also overrides the rate limiter dependency
with a fakeredis-backed instance (generous capacity) so that tests unrelated
to rate limiting don't depend on -- or get blocked by -- a real Redis server.
Rate-limiting-specific tests build their own RateLimiter with a small limit.
"""
import uuid

import fakeredis.aioredis
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.api_keys import hash_api_key
from app.deps import get_db_session, get_rate_limiter
from app.main import app
from app.ratelimit.limiter import RateLimiter

TEST_SCHEMA = """
CREATE TABLE api_keys (
    id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    rate_limit_per_min INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    active BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE request_logs (
    id TEXT PRIMARY KEY,
    api_key_id TEXT,
    model_alias TEXT,
    provider_used TEXT,
    model_used TEXT,
    status TEXT,
    attempt_count INTEGER,
    fallback_occurred BOOLEAN,
    input_tokens INTEGER,
    output_tokens INTEGER,
    total_tokens INTEGER,
    estimated_cost_usd NUMERIC,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


@pytest_asyncio.fixture
async def test_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for statement in TEST_SCHEMA.strip().split(";"):
            statement = statement.strip()
            if statement:
                await conn.execute(text(statement))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_api_key(test_engine):
    """Inserts one active API key directly and returns its raw (unhashed) value."""
    raw_key = "test-raw-key-12345"
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO api_keys (id, key_hash, label, active) "
                "VALUES (:id, :key_hash, :label, 1)"
            ),
            {"id": str(uuid.uuid4()), "key_hash": hash_api_key(raw_key), "label": "test-client"},
        )
        await session.commit()
    return raw_key


@pytest_asyncio.fixture
async def seeded_api_key_pair(test_engine):
    """Like seeded_api_key, but also returns the key's id -- needed by Phase 4
    tests that verify a request_logs row was written for a given api_key_id."""
    raw_key = "test-raw-key-chat-98765"
    key_id = str(uuid.uuid4())
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        await session.execute(
            text(
                "INSERT INTO api_keys (id, key_hash, label, active) "
                "VALUES (:id, :key_hash, :label, 1)"
            ),
            {"id": key_id, "key_hash": hash_api_key(raw_key), "label": "chat-test-client"},
        )
        await session.commit()
    return raw_key, key_id


@pytest_asyncio.fixture
async def fetch_request_logs(test_engine):
    """Returns an async callable that fetches all request_logs rows, for
    Phase 4 tests asserting usage/cost rows were written correctly."""

    async def _fetch():
        session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
        async with session_factory() as session:
            result = await session.execute(text("SELECT * FROM request_logs"))
            return result.mappings().all()

    return _fetch


@pytest_asyncio.fixture
async def client(test_engine):
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def override_get_db_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Generous fakeredis-backed limiter so unrelated tests never get 429'd.
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_rate_limiter] = lambda: RateLimiter(redis_client=fake_redis)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
