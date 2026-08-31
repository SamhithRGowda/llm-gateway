"""GET /metrics -- Prometheus exposition endpoint, per PLAN.md Section 5/Phase 7.

No Prometheus/Grafana server is deployed as part of this project (out of
scope per PLAN.md Section 11) -- this endpoint just exposes the counters and
histograms for an external scraper to pull.
"""
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter()


@router.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
