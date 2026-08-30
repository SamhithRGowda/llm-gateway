"""Insert/query helpers for request_logs, per PLAN.md's repo structure
("app/usage/repository.py # insert/query usage rows").
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.usage.models import RequestLog


async def create_request_log(session: AsyncSession, **fields) -> RequestLog:
    """Insert one request_logs row and commit."""
    log = RequestLog(**fields)
    session.add(log)
    await session.commit()
    return log
