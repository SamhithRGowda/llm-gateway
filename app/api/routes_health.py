"""Liveness endpoint.

Reports basic liveness plus, per PLAN.md Phase 6 ("Update /health to report
circuit state"), each provider's current circuit-breaker state. Postgres/Redis
dependency connectivity checks are not part of Phase 6's scope and are left
for a later phase.
"""
from fastapi import APIRouter, Depends

from app.deps import get_router
from app.routing.router import Router

router = APIRouter()


@router.get("/health")
async def health(provider_router: Router = Depends(get_router)) -> dict:
    return {
        "status": "ok",
        "providers": {
            name: {"circuit_state": state}
            for name, state in provider_router.get_circuit_states().items()
        },
    }
