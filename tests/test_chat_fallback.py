import pytest

from app.providers.base import NormalizedRequest, NormalizedResponse, ProviderAdapter
from app.providers.errors import FatalProviderError, RetryableProviderError
from app.routing.router import AllProvidersFailedError, Router

pytestmark = pytest.mark.asyncio


class FakeAdapter(ProviderAdapter):
    """A minimal in-memory ProviderAdapter for exercising router logic without
    any HTTP calls or retry-timing concerns."""

    def __init__(self, name: str, outcomes: list):
        self.name = name
        self._outcomes = list(outcomes)  # each item: NormalizedResponse or Exception
        self.call_count = 0

    def is_retryable_error(self, exc: Exception) -> bool:
        return isinstance(exc, RetryableProviderError)

    async def send(self, model: str, request: NormalizedRequest) -> NormalizedResponse:
        self.call_count += 1
        outcome = self._outcomes.pop(0) if self._outcomes else self._outcomes
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_response(content: str) -> NormalizedResponse:
    return NormalizedResponse(content=content, input_tokens=1, output_tokens=1, raw_provider_model="fake-model")


async def test_route_succeeds_on_first_provider_without_fallback():
    groq = FakeAdapter("groq", [make_response("from groq")])
    openai = FakeAdapter("openai", [make_response("from openai")])
    router = Router(adapters={"groq": groq, "openai": openai})

    result = await router.route("fast-cheap", NormalizedRequest(messages=[{"role": "user", "content": "hi"}]))

    assert result.provider == "groq"
    assert result.response.content == "from groq"
    assert result.fallback_occurred is False
    assert openai.call_count == 0


async def test_route_falls_back_to_second_provider_when_first_exhausts_retries():
    # "fast-cheap" chain is [groq, openai]; groq always fails (non-retryable
    # so it fails fast), openai succeeds.
    groq = FakeAdapter("groq", [FatalProviderError("groq is down")])
    openai = FakeAdapter("openai", [make_response("from openai fallback")])
    router = Router(adapters={"groq": groq, "openai": openai})

    result = await router.route("fast-cheap", NormalizedRequest(messages=[{"role": "user", "content": "hi"}]))

    assert result.provider == "openai"
    assert result.response.content == "from openai fallback"
    assert result.fallback_occurred is True
    assert len(result.attempts) == 1
    assert result.attempts[0].provider == "groq"
    assert result.attempts[0].error_type == "FatalProviderError"


async def test_route_raises_all_providers_failed_when_entire_chain_fails():
    groq = FakeAdapter("groq", [FatalProviderError("groq is down")])
    openai = FakeAdapter("openai", [FatalProviderError("openai is down too")])
    router = Router(adapters={"groq": groq, "openai": openai})

    with pytest.raises(AllProvidersFailedError) as exc_info:
        await router.route("fast-cheap", NormalizedRequest(messages=[{"role": "user", "content": "hi"}]))

    assert exc_info.value.alias == "fast-cheap"
    assert [a.provider for a in exc_info.value.attempts] == ["groq", "openai"]


async def test_route_retries_within_a_provider_before_falling_back():
    # premium alias is openai-only; simulate one retryable failure then success.
    openai = FakeAdapter("openai", [RetryableProviderError("transient"), make_response("recovered")])
    router = Router(adapters={"openai": openai})

    result = await router.route("premium", NormalizedRequest(messages=[{"role": "user", "content": "hi"}]))

    assert result.provider == "openai"
    assert result.response.content == "recovered"
    assert result.fallback_occurred is False
    assert openai.call_count == 2


async def test_route_skips_alias_entries_with_no_registered_adapter():
    # Only openai adapter registered even though "fast-cheap" also lists groq.
    openai = FakeAdapter("openai", [make_response("from openai only")])
    router = Router(adapters={"openai": openai})

    result = await router.route("fast-cheap", NormalizedRequest(messages=[{"role": "user", "content": "hi"}]))

    assert result.provider == "openai"
    assert result.fallback_occurred is True
    assert result.attempts[0].provider == "groq"
    assert result.attempts[0].error_type == "ConfigurationError"
