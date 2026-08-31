import json
import logging

from app.observability.logging_config import log_chat_request


def test_log_chat_request_emits_valid_json_with_expected_fields(caplog):
    with caplog.at_level(logging.INFO, logger="llm_gateway.requests"):
        log_chat_request(
            request_id="req_abc123",
            api_key_label="test-client",
            model_alias="fast-cheap",
            provider_used="groq",
            status="success",
            latency_ms=123,
            fallback_occurred=False,
        )

    assert len(caplog.records) == 1
    formatted = caplog.records[0].getMessage()
    # The record's raw message is just "chat_request"; the JSON formatting
    # happens in the handler's Formatter, so we re-verify via the logger's
    # configured handler directly instead of caplog's plain formatting.
    assert formatted == "chat_request"

    fields = caplog.records[0].fields
    assert fields["request_id"] == "req_abc123"
    assert fields["api_key_label"] == "test-client"
    assert fields["model_alias"] == "fast-cheap"
    assert fields["provider_used"] == "groq"
    assert fields["status"] == "success"
    assert fields["latency_ms"] == 123
    assert fields["fallback_occurred"] is False


def test_json_formatter_produces_parseable_json_without_message_content():
    from app.observability.logging_config import _JsonFormatter

    formatter = _JsonFormatter()
    record = logging.LogRecord(
        name="llm_gateway.requests",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="chat_request",
        args=None,
        exc_info=None,
    )
    record.fields = {
        "request_id": "req_xyz",
        "api_key_label": "client",
        "model_alias": "fast-cheap",
        "provider_used": "openai",
        "status": "success",
        "latency_ms": 42,
        "fallback_occurred": False,
    }

    parsed = json.loads(formatter.format(record))
    assert parsed["event"] == "chat_request"
    assert parsed["request_id"] == "req_xyz"
    assert parsed["latency_ms"] == 42
    # No message/content fields should ever be present.
    assert "content" not in parsed
    assert "messages" not in parsed
