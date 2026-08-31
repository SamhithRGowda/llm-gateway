"""GET /stats -- human-readable usage summary, per PLAN.md Section 5/Phase 7.

Computed via a query against request_logs (last N rows), matching PLAN.md's
"Computed via a query against request_logs (last N rows or last time window,
whichever's simpler to implement well)". Last-N-rows is used here for
simplicity and dialect-agnostic SQL (works the same on SQLite in tests and
Postgres at runtime).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db_session

router = APIRouter()

_WINDOW_SIZE = 1000
_SUCCESS_STATUSES = {"success", "fallback_success"}


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_db_session)) -> dict:
    result = await session.execute(
        text(
            "SELECT status, provider_used, latency_ms, estimated_cost_usd "
            "FROM request_logs ORDER BY created_at DESC LIMIT :limit"
        ),
        {"limit": _WINDOW_SIZE},
    )
    rows = result.mappings().all()

    window_label = f"last_{_WINDOW_SIZE}_requests"
    total_requests = len(rows)

    if total_requests == 0:
        return {
            "window": window_label,
            "total_requests": 0,
            "success_rate": 0.0,
            "fallback_rate": 0.0,
            "avg_latency_ms": 0.0,
            "total_estimated_cost_usd": 0.0,
            "by_provider": {},
        }

    success_count = sum(1 for row in rows if row["status"] in _SUCCESS_STATUSES)
    fallback_count = sum(1 for row in rows if row["status"] == "fallback_success")
    latencies = [row["latency_ms"] for row in rows if row["latency_ms"] is not None]
    total_cost = sum(float(row["estimated_cost_usd"]) for row in rows if row["estimated_cost_usd"] is not None)

    by_provider: dict[str, dict] = {}
    for row in rows:
        provider = row["provider_used"]
        if provider is None:
            continue
        entry = by_provider.setdefault(provider, {"requests": 0, "successes": 0})
        entry["requests"] += 1
        if row["status"] in _SUCCESS_STATUSES:
            entry["successes"] += 1

    by_provider_output = {
        provider: {
            "requests": data["requests"],
            "success_rate": round(data["successes"] / data["requests"], 4),
        }
        for provider, data in by_provider.items()
    }

    return {
        "window": window_label,
        "total_requests": total_requests,
        "success_rate": round(success_count / total_requests, 4),
        "fallback_rate": round(fallback_count / total_requests, 4),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "total_estimated_cost_usd": round(total_cost, 6),
        "by_provider": by_provider_output,
    }
