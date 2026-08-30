"""End-to-end demonstration (Phase 2 completion criterion): calling
OpenAIAdapter.send() through the generic retry helper recovers from an
injected transient failure. This is the automated equivalent of the "temporary
internal script" described in PLAN.md's Phase 2 completion criteria -- no
routing/fallback/circuit-breaker logic is involved, just retry + one adapter.
"""
import httpx
import pytest
import respx

from app.providers.base import NormalizedRequest
from app.providers.errors import RetryableProviderError
from app.providers.openai_adapter import OpenAIAdapter
from app.reliability.retry import with_retry

pytestmark = pytest.mark.asyncio


async def _no_op_sleep(_seconds: float) -> None:
    return None


@respx.mock
async def test_retry_recovers_openai_adapter_from_transient_failure():
    route = respx.post("https://api.openai.com/v1/chat/completions")
    route.side_effect = [
        httpx.Response(500, text="server error"),
        httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"content": "recovered response"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        ),
    ]

    adapter = OpenAIAdapter(api_key="test-key")
    request = NormalizedRequest(messages=[{"role": "user", "content": "Hi"}])

    response = await with_retry(
        func=lambda: adapter.send("gpt-4o-mini", request),
        is_retryable=adapter.is_retryable_error,
        sleep=_no_op_sleep,
    )

    assert response.content == "recovered response"
    assert response.input_tokens == 5
    assert response.output_tokens == 2
    assert route.call_count == 2


@respx.mock
async def test_retry_gives_up_after_exhausting_attempts_against_adapter():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="server error")
    )

    adapter = OpenAIAdapter(api_key="test-key")
    request = NormalizedRequest(messages=[{"role": "user", "content": "Hi"}])

    with pytest.raises(RetryableProviderError):
        await with_retry(
            func=lambda: adapter.send("gpt-4o-mini", request),
            is_retryable=adapter.is_retryable_error,
            sleep=_no_op_sleep,
        )
