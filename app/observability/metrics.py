"""Prometheus counters/histograms, per PLAN.md Section 5's GET /metrics spec.

A single shared set of metrics (default registry), updated by the /v1/chat
endpoint and exposed via GET /metrics (app/api/routes_metrics.py). Exactly
the six metrics PLAN.md names -- no additional metrics invented.
"""
from prometheus_client import Counter, Histogram

REQUESTS_TOTAL = Counter(
    "gateway_requests_total",
    "Total /v1/chat requests, by outcome status, provider used, and model alias.",
    ["status", "provider", "model_alias"],
)

REQUEST_LATENCY_SECONDS = Histogram(
    "gateway_request_latency_seconds",
    "End-to-end /v1/chat request latency in seconds, by provider used.",
    ["provider"],
)

FALLBACK_EVENTS_TOTAL = Counter(
    "gateway_fallback_events_total",
    "Total provider fallback events, by the provider fallen away from and to.",
    ["from_provider", "to_provider"],
)

RATE_LIMIT_EXCEEDED_TOTAL = Counter(
    "gateway_rate_limit_exceeded_total",
    "Total requests rejected due to rate limiting, by API key label.",
    ["api_key_label"],
)

TOKENS_TOTAL = Counter(
    "gateway_tokens_total",
    "Total tokens processed, by provider and direction (input/output).",
    ["provider", "direction"],
)

ESTIMATED_COST_USD_TOTAL = Counter(
    "gateway_estimated_cost_usd_total",
    "Total estimated cost in USD, by provider.",
    ["provider"],
)
