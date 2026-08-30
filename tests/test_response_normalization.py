import httpx
import pytest
import respx

from app.providers.base import NormalizedRequest
from app.providers.errors import FatalProviderError, ProviderRateLimitedError, RetryableProviderError
from app.providers.openai_adapter import OpenAIAdapter

pytestmark = pytest.mark.asyncio


def make_adapter() -> OpenAIAdapter:
    return OpenAIAdapter(api_key="test-key")


@respx.mock
async def test_send_normalizes_successful_response():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "choices": [{"message": {"role": "assistant", "content": "Hello there!"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
            },
        )
    )

    adapter = make_adapter()
    request = NormalizedRequest(messages=[{"role": "user", "content": "Hi"}])
    response = await adapter.send("gpt-4o-mini", request)

    assert response.content == "Hello there!"
    assert response.input_tokens == 8
    assert response.output_tokens == 4
    assert response.raw_provider_model == "gpt-4o-mini-2024-07-18"


@respx.mock
async def test_send_includes_optional_params_in_payload():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    )

    adapter = make_adapter()
    request = NormalizedRequest(messages=[{"role": "user", "content": "Hi"}], max_tokens=50, temperature=0.2)
    await adapter.send("gpt-4o-mini", request)

    sent_body = route.calls.last.request.content
    import json

    parsed = json.loads(sent_body)
    assert parsed["max_tokens"] == 50
    assert parsed["temperature"] == 0.2


@respx.mock
async def test_send_raises_retryable_on_500():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(500, text="internal error")
    )
    adapter = make_adapter()
    with pytest.raises(RetryableProviderError):
        await adapter.send("gpt-4o-mini", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))


@respx.mock
async def test_send_raises_rate_limited_on_429_with_retry_after():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(429, text="rate limited", headers={"Retry-After": "3"})
    )
    adapter = make_adapter()
    with pytest.raises(ProviderRateLimitedError) as exc_info:
        await adapter.send("gpt-4o-mini", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))
    assert exc_info.value.retry_after_seconds == 3.0


@respx.mock
async def test_send_raises_fatal_on_400():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(400, text="bad request")
    )
    adapter = make_adapter()
    with pytest.raises(FatalProviderError):
        await adapter.send("gpt-4o-mini", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))


@respx.mock
async def test_send_raises_fatal_on_401():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(401, text="invalid api key")
    )
    adapter = make_adapter()
    with pytest.raises(FatalProviderError):
        await adapter.send("gpt-4o-mini", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))


async def test_send_raises_retryable_on_connection_error():
    adapter = make_adapter()

    with respx.mock:
        respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=httpx.ConnectError("boom"))
        with pytest.raises(RetryableProviderError):
            await adapter.send("gpt-4o-mini", NormalizedRequest(messages=[{"role": "user", "content": "Hi"}]))



