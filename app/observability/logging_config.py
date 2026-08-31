"""Structured JSON request logging, per PLAN.md Section 11.

One JSON log line per /v1/chat request, with request_id, api_key_label,
model_alias, provider_used, status, latency_ms, and fallback_occurred.
Message content is never logged -- only request metadata.
"""
import json
import logging
import sys

_LOGGER_NAME = "llm_gateway.requests"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"event": record.getMessage()}
        fields = getattr(record, "fields", None)
        if fields:
            payload.update(fields)
        return json.dumps(payload, default=str)


def get_request_logger() -> logging.Logger:
    """Returns the shared request logger, configured with a JSON formatter
    on first access."""
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_chat_request(
    *,
    request_id: str,
    api_key_label: str,
    model_alias: str,
    provider_used: str | None,
    status: str,
    latency_ms: int,
    fallback_occurred: bool,
) -> None:
    """Emit one structured JSON log line for a completed /v1/chat request.

    Never includes message content (PLAN.md Section 11: "Never log full
    message content ... log message count and character length only, not
    content" -- since /v1/chat doesn't currently track message length
    separately, this log line simply omits any message-derived field).
    """
    get_request_logger().info(
        "chat_request",
        extra={
            "fields": {
                "request_id": request_id,
                "api_key_label": api_key_label,
                "model_alias": model_alias,
                "provider_used": provider_used,
                "status": status,
                "latency_ms": latency_ms,
                "fallback_occurred": fallback_occurred,
            }
        },
    )
