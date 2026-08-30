import httpx
import pytest
import respx

from app.providers.base import NormalizedRequest
from app.providers.errors import FatalProviderError, ProviderRateLimitedError, RetryableProviderError
from app.providers.groq_adapter import GroqAdapter

pytestmark = pytest.mark.asyncio


def make_adapter() -> GroqAdapter:
    return GroqAdapter(api_key="test-groq-key")


@respx.mock
async def test_send_normalizes_successful_response():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "llama-3.1-8b-instant",
                "choices": [{"message": {"role": "assistant", "content": "Hi from Groq"}}],
                "usage": {"prompt_tokens": 6, "completion_tokens": 3, "total_tokens": 9},
            },
        )
    )

    adapter = make_adapter()
    request = NormalizedRequest(messages=[{"role": "user", "content": "Hi"}])
    response = await adapter.send("llama-3.1-8b-instant", request)

    assert response.content == "Hi from Groq"
    assert response.input_tokens == 6
    assert response.output_tokens == 3
    assert response.raw_provider_model == "llama-3.1-8b-instant"


@respx.mock
async def test_send_raises_retryable_on_500():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="internal error")
    )
    adapter = make_adapter()
    with pytest.raises(RetryableProviderError):
        await adapter.send("llama-3.1-8b-instant", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))


@respx.mock
async def test_send_raises_rate_limited_on_429_with_retry_after():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(429, text="rate limited", headers={"Retry-After": "2"})
    )
    adapter = make_adapter()
    with pytest.raises(ProviderRateLimitedError) as exc_info:
        await adapter.send("llama-3.1-8b-instant", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))
    assert exc_info.value.retry_after_seconds == 2.0


@respx.mock
async def test_send_raises_fatal_on_401():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=httpx.Response(401, text="invalid api key")
    )
    adapter = make_adapter()
    with pytest.raises(FatalProviderError):
        await adapter.send("llama-3.1-8b-instant", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))


async def test_send_raises_retryable_on_connection_error():
    adapter = make_adapter()
    with respx.mock:
        respx.post("https://api.groq.com/openai/v1/chat/completions").mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(RetryableProviderError):
            await adapter.send("llama-3.1-8b-instant", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))
