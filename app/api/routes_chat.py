"""POST /v1/chat -- the gateway's unified chat endpoint, per PLAN.md Section 5.

Wires together: auth (Phase 1), rate limiting (Phase 5), the router +
provider adapters (Phases 2-3) with circuit breaker (Phase 6), usage/cost
persistence (Phase 4), and structured logging/metrics (Phase 7).
"""
import math
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_keys import ApiKeyRecord
from app.config import settings
from app.deps import get_current_api_key, get_db_session, get_rate_limiter, get_router
from app.observability.logging_config import log_chat_request
from app.observability.metrics import (
    ESTIMATED_COST_USD_TOTAL,
    FALLBACK_EVENTS_TOTAL,
    RATE_LIMIT_EXCEEDED_TOTAL,
    REQUEST_LATENCY_SECONDS,
    REQUESTS_TOTAL,
    TOKENS_TOTAL,
)
from app.providers.base import NormalizedRequest
from app.ratelimit.limiter import RateLimiter
from app.routing.config import UnknownModelAliasError
from app.routing.router import AllProvidersFailedError, Router
from app.usage.cost_calculator import calculate_cost
from app.usage.repository import create_request_log

router = APIRouter()

_ALLOWED_ROLES = {"system", "user", "assistant"}
_NO_PROVIDER_LABEL = "none"


class ChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1)

    @field_validator("role")
    @classmethod
    def role_must_be_known(cls, value: str) -> str:
        if value not in _ALLOWED_ROLES:
            raise ValueError(f"Invalid role {value!r}; must be one of {sorted(_ALLOWED_ROLES)}")
        return value


class ChatRequest(BaseModel):
    model: str = Field(min_length=1)
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int | None = None
    temperature: float | None = None


class ChatUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class ChatResponse(BaseModel):
    id: str
    model_alias: str
    provider: str
    model: str
    content: str
    usage: ChatUsage
    latency_ms: int
    fallback_occurred: bool


@router.post("/v1/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    api_key: ApiKeyRecord = Depends(get_current_api_key),
    session: AsyncSession = Depends(get_db_session),
    provider_router: Router = Depends(get_router),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
) -> ChatResponse:
    request_id = f"req_{uuid.uuid4().hex[:12]}"

    limit_per_min = api_key.rate_limit_per_min or settings.default_rate_limit_per_min
    rate_limit_result = await rate_limiter.check(api_key.id, limit_per_min)
    if not rate_limit_result.allowed:
        # Rate limiting happens before routing: no provider call is made, so
        # cost/latency for this request is 0 (PLAN.md Section 9).
        await create_request_log(
            session,
            api_key_id=uuid.UUID(api_key.id),
            model_alias=body.model,
            provider_used=None,
            model_used=None,
            status="rate_limited",
            attempt_count=0,
            fallback_occurred=False,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            estimated_cost_usd=None,
            latency_ms=0,
            error_message=None,
        )
        REQUESTS_TOTAL.labels(status="rate_limited", provider=_NO_PROVIDER_LABEL, model_alias=body.model).inc()
        RATE_LIMIT_EXCEEDED_TOTAL.labels(api_key_label=api_key.label).inc()
        log_chat_request(
            request_id=request_id,
            api_key_label=api_key.label,
            model_alias=body.model,
            provider_used=None,
            status="rate_limited",
            latency_ms=0,
            fallback_occurred=False,
        )
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limit_exceeded", "retry_after_seconds": rate_limit_result.retry_after_seconds},
            headers={"Retry-After": str(math.ceil(rate_limit_result.retry_after_seconds))},
        )

    normalized_request = NormalizedRequest(
        messages=[m.model_dump() for m in body.messages],
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )

    start = time.perf_counter()

    try:
        routed = await provider_router.route(body.model, normalized_request)
    except UnknownModelAliasError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "message": f"Unknown model alias: {exc.alias!r}"},
        )
    except AllProvidersFailedError as exc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        await create_request_log(
            session,
            api_key_id=uuid.UUID(api_key.id),
            model_alias=body.model,
            provider_used=None,
            model_used=None,
            status="all_failed",
            attempt_count=len(exc.attempts),
            fallback_occurred=len(exc.attempts) > 1,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            estimated_cost_usd=None,
            latency_ms=latency_ms,
            error_message=str(exc)[:500],
        )
        REQUESTS_TOTAL.labels(status="all_failed", provider=_NO_PROVIDER_LABEL, model_alias=body.model).inc()
        log_chat_request(
            request_id=request_id,
            api_key_label=api_key.label,
            model_alias=body.model,
            provider_used=None,
            status="all_failed",
            latency_ms=latency_ms,
            fallback_occurred=len(exc.attempts) > 1,
        )
        return JSONResponse(
            status_code=502,
            content={
                "error": "all_providers_failed",
                "attempts": [
                    {"provider": a.provider, "error_type": a.error_type, "message": a.message}
                    for a in exc.attempts
                ],
            },
        )

    latency_ms = int((time.perf_counter() - start) * 1000)
    input_tokens = routed.response.input_tokens
    output_tokens = routed.response.output_tokens
    total_tokens = input_tokens + output_tokens
    cost = calculate_cost(routed.provider, routed.model, input_tokens, output_tokens)
    status_label = "fallback_success" if routed.fallback_occurred else "success"

    await create_request_log(
        session,
        api_key_id=uuid.UUID(api_key.id),
        model_alias=body.model,
        provider_used=routed.provider,
        model_used=routed.model,
        status=status_label,
        attempt_count=len(routed.attempts) + 1,
        fallback_occurred=routed.fallback_occurred,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
        latency_ms=latency_ms,
        error_message=None,
    )

    REQUESTS_TOTAL.labels(status=status_label, provider=routed.provider, model_alias=body.model).inc()
    REQUEST_LATENCY_SECONDS.labels(provider=routed.provider).observe(latency_ms / 1000)
    TOKENS_TOTAL.labels(provider=routed.provider, direction="input").inc(input_tokens)
    TOKENS_TOTAL.labels(provider=routed.provider, direction="output").inc(output_tokens)
    ESTIMATED_COST_USD_TOTAL.labels(provider=routed.provider).inc(float(cost))
    if routed.fallback_occurred:
        from_provider = routed.attempts[-1].provider if routed.attempts else _NO_PROVIDER_LABEL
        FALLBACK_EVENTS_TOTAL.labels(from_provider=from_provider, to_provider=routed.provider).inc()

    log_chat_request(
        request_id=request_id,
        api_key_label=api_key.label,
        model_alias=body.model,
        provider_used=routed.provider,
        status=status_label,
        latency_ms=latency_ms,
        fallback_occurred=routed.fallback_occurred,
    )

    return ChatResponse(
        id=request_id,
        model_alias=body.model,
        provider=routed.provider,
        model=routed.model,
        content=routed.response.content,
        usage=ChatUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=float(cost),
        ),
        latency_ms=latency_ms,
        fallback_occurred=routed.fallback_occurred,
    )
