"""Shared FastAPI dependencies: DB session injection and API key auth."""
from fastapi import Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app.auth.api_keys import ApiKeyRecord, get_active_api_key
from app.db.base import get_session
from app.providers.groq_adapter import GroqAdapter
from app.providers.openai_adapter import OpenAIAdapter
from app.ratelimit.limiter import RateLimiter
from app.routing.router import Router

# Re-exported so routes can do `Depends(get_db_session)`.
get_db_session = get_session

# One Router instance, built once with the real provider adapters. Adapters
# only read their API key from settings at send()-time, so constructing them
# here does not require credentials to be present unless a request actually
# reaches that provider.
_router = Router(adapters={"openai": OpenAIAdapter(), "groq": GroqAdapter()})


def get_router() -> Router:
    return _router


# One RateLimiter instance, built once against the configured Redis URL.
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    return _rate_limiter


async def get_current_api_key(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyRecord:
    """Validate the `Authorization: Bearer <key>` header against api_keys.

    Raises 401 if the header is missing/malformed or the key is unknown/inactive.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed API key")

    raw_key = authorization.split(" ", 1)[1].strip()
    if not raw_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or malformed API key")

    key_record = await get_active_api_key(session, raw_key)
    if key_record is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or inactive API key")

    return key_record
