"""Liveness endpoint.

Phase 0 scope only: returns basic liveness. Dependency status (Postgres/Redis)
and provider circuit-breaker state are added in Phase 7 per PLAN.md.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}
