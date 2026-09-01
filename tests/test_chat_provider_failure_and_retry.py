"""Endpoint-level coverage for PLAN.md Section 13's
test_chat_provider_failure_and_retry.py scenario: "Provider fails twice
(retryable) then succeeds on 3rd attempt; verify retry count and backoff
invoked, no fallback."

This is distinct from existing retry coverage elsewhere in the suite:
  - tests/test_retry.py exercises the generic with_retry() helper in isolation.
  - tests/test_openai_adapter_retry_integration.py exercises retry wrapping
    OpenAIAdapter.send() directly via respx, with no router/endpoint involved.
  - tests/test_chat_fallback.py::test_route_retries_within_a_provider_before_falling_back
    exercises Router.route() directly, bypassing auth, rate limiting, and
    request_logs persistence.

None of those prove the full /v1/chat stack (auth -> rate limit -> router ->
retry -> usage logging -> response schema) behaves correctly when a provider
recovers mid-request. This file closes that gap.
"""
import pytest

from app.deps import get_router
from app.main import app
from app.providers.errors import RetryableProviderError
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


async def test_chat_recovers_from_transient_failures_without_falling_back(
    client, seeded_api_key_pair, fetch_request_logs
):
    raw_key, _ = seeded_api_key_pair

    # Fails twice (retryable), succeeds on the 3rd call -- exactly PLAN.md's
    # "max 2 retries per provider (3 attempts total)" policy (Section 8).
    groq = FakeAdapter(
        "groq",
        [
            RetryableProviderError("transient error 1"),
            RetryableProviderError("transient error 2"),
            make_response("recovered on third attempt"),
        ],
    )
    openai = FakeAdapter("openai", [make_response("should never be called")])
    app.dependency_overrides[get_router] = lambda: Router(adapters={"groq": groq, "openai": openai})

    resp = await client.post(
        "/v1/chat",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"model": "fast-cheap", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert resp.status_code == 200
    body = resp.json()

    # Recovered on the same provider -- this is retry, not fallback.
    assert body["provider"] == "groq"
    assert body["content"] == "recovered on third attempt"
    assert body["fallback_occurred"] is False

    # All 3 attempts were against groq; openai was never touched.
    assert groq.call_count == 3
    assert openai.call_count == 0

    rows = await fetch_request_logs()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "success"  # not "fallback_success"
    assert row["provider_used"] == "groq"
    assert row["fallback_occurred"] in (0, False)
    assert row["attempt_count"] == 1  # one provider-chain entry attempted (its internal retries aren't chain hops)
