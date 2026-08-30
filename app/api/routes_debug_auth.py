"""Phase 1 auth-verification route.

This route exists only to prove the API key auth dependency works end-to-end
(a seeded key resolves to a record; a missing/invalid key is rejected with
401). PLAN.md Phase 1's completion criterion calls for exactly this: "a
dependency-injected test route." It intentionally does nothing else and will
be superseded by the real /v1/chat endpoint in Phase 4.
"""
from fastapi import APIRouter, Depends

from app.auth.api_keys import ApiKeyRecord
from app.deps import get_current_api_key

router = APIRouter()


@router.get("/v1/_whoami")
async def whoami(api_key: ApiKeyRecord = Depends(get_current_api_key)) -> dict:
    return {"api_key_id": api_key.id, "label": api_key.label}
