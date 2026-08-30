"""API key hashing and validation.

Client-facing API keys are stored as SHA-256 hashes (see PLAN.md Section 17:
"Client API keys stored hashed ... never stored/logged in plaintext"). The
raw key is only ever seen by the client at seed/creation time.
"""
import hashlib
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


@dataclass
class ApiKeyRecord:
    id: str
    label: str
    rate_limit_per_min: Optional[int]
    active: bool


async def get_active_api_key(session: AsyncSession, raw_key: str) -> Optional[ApiKeyRecord]:
    """Look up an active API key record by its raw (unhashed) value.

    Returns None if the key doesn't exist or is inactive.
    """
    key_hash = hash_api_key(raw_key)
    result = await session.execute(
        text(
            """
            SELECT id, label, rate_limit_per_min, active
            FROM api_keys
            WHERE key_hash = :key_hash AND active = true
            """
        ),
        {"key_hash": key_hash},
    )
    row = result.mappings().first()
    if row is None:
        return None
    return ApiKeyRecord(
        id=str(row["id"]),
        label=row["label"],
        rate_limit_per_min=row["rate_limit_per_min"],
        active=row["active"],
    )
