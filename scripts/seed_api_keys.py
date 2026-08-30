"""Seed one demo API key into the api_keys table.

Usage (from repo root, with DATABASE_URL pointed at a running Postgres, e.g.
via `docker-compose exec gateway python scripts/seed_api_keys.py`):

    python scripts/seed_api_keys.py [label]

Prints the raw key exactly once -- it is not recoverable afterwards, only its
hash is stored (see app/auth/api_keys.py).
"""
import asyncio
import secrets
import sys

from sqlalchemy import text

from app.auth.api_keys import hash_api_key
from app.db.base import get_engine


async def seed(label: str) -> None:
    raw_key = secrets.token_urlsafe(32)
    key_hash = hash_api_key(raw_key)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO api_keys (key_hash, label)
                VALUES (:key_hash, :label)
                """
            ),
            {"key_hash": key_hash, "label": label},
        )

    print(f"Seeded API key for label={label!r}")
    print(f"Raw key (save this, it will not be shown again): {raw_key}")


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "demo-client"
    asyncio.run(seed(label))
