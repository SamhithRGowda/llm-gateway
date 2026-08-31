# --- Router integration: circuit breaker gating + fallback (Phase 6) -------

import time

import pytest

from app.providers.base import NormalizedRequest
from app.providers.errors import FatalProviderError
from app.reliability.circuit_breaker import CircuitBreaker, CircuitState
from app.routing.router import Router

from test_chat_fallback import FakeAdapter, make_response

pytestmark = pytest.mark.asyncio


def make_breaker(failure_threshold: int = 3, cooldown_seconds: float = 0.2) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds)


def make_request() -> NormalizedRequest:
    return NormalizedRequest(messages=[{"role": "user", "content": "hi"}])


async def test_router_skips_provider_whose_circuit_is_open_without_calling_it():
    # "fast-cheap" chain is [groq, openai]. groq's breaker is pre-tripped OPEN.
    groq_breaker = make_breaker(failure_threshold=1, cooldown_seconds=999)
    groq_breaker.record_failure()  # trips OPEN
    openai_breaker = make_breaker(failure_threshold=1, cooldown_seconds=999)

    groq = FakeAdapter("groq", [make_response("should not be called")])
    openai = FakeAdapter("openai", [make_response("from openai")])
    router = Router(
        adapters={"groq": groq, "openai": openai},
        circuit_breakers={"groq": groq_breaker, "openai": openai_breaker},
    )

    result = await router.route("fast-cheap", make_request())

    assert result.provider == "openai"
    assert result.fallback_occurred is True
    assert groq.call_count == 0  # skipped without a network attempt
    assert result.attempts[0].provider == "groq"
    assert result.attempts[0].error_type == "CircuitOpen"


async def test_router_trips_breaker_after_repeated_provider_failures():
    groq_breaker = make_breaker(failure_threshold=2, cooldown_seconds=999)
    openai_breaker = make_breaker(failure_threshold=2, cooldown_seconds=999)
    router = Router(
        adapters={
            "groq": FakeAdapter("groq", [FatalProviderError("down")]),
            "openai": FakeAdapter("openai", [make_response("ok")]),
        },
        circuit_breakers={"groq": groq_breaker, "openai": openai_breaker},
    )

    await router.route("fast-cheap", make_request())
    assert groq_breaker.state == CircuitState.CLOSED  # 1st failure, below threshold

    router._adapters["groq"] = FakeAdapter("groq", [FatalProviderError("still down")])
    await router.route("fast-cheap", make_request())
    assert groq_breaker.state == CircuitState.OPEN  # 2nd consecutive failure trips it


async def test_router_records_success_and_keeps_breaker_closed():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=999)
    router = Router(
        adapters={"openai": FakeAdapter("openai", [make_response("ok")])},
        circuit_breakers={"openai": breaker},
    )

    result = await router.route("premium", make_request())

    assert result.provider == "openai"
    assert breaker.state == CircuitState.CLOSED


async def test_router_half_open_probe_success_closes_breaker_and_routes_normally():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=0.05)
    breaker.record_failure()  # trip OPEN
    time.sleep(0.06)  # cooldown elapses -> HALF_OPEN on next state check

    router = Router(
        adapters={"openai": FakeAdapter("openai", [make_response("recovered")])},
        circuit_breakers={"openai": breaker},
    )

    result = await router.route("premium", make_request())

    assert result.provider == "openai"
    assert result.response.content == "recovered"
    assert breaker.state == CircuitState.CLOSED


async def test_router_half_open_probe_failure_reopens_breaker():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=0.05)
    breaker.record_failure()  # trip OPEN
    time.sleep(0.06)  # -> HALF_OPEN

    router = Router(
        adapters={"openai": FakeAdapter("openai", [FatalProviderError("still down")])},
        circuit_breakers={"openai": breaker},
    )

    with pytest.raises(Exception):
        await router.route("premium", make_request())

    assert breaker.state == CircuitState.OPEN


async def test_openai_and_groq_breakers_are_independent():
    groq_breaker = make_breaker(failure_threshold=1, cooldown_seconds=999)
    openai_breaker = make_breaker(failure_threshold=1, cooldown_seconds=999)
    router = Router(
        adapters={
            "groq": FakeAdapter("groq", [FatalProviderError("groq down")]),
            "openai": FakeAdapter("openai", [make_response("openai fine")]),
        },
        circuit_breakers={"groq": groq_breaker, "openai": openai_breaker},
    )

    await router.route("fast-cheap", make_request())

    assert groq_breaker.state == CircuitState.OPEN
    assert openai_breaker.state == CircuitState.CLOSED


async def test_router_reports_circuit_states_for_health_endpoint():
    groq_breaker = make_breaker(failure_threshold=1, cooldown_seconds=999)
    openai_breaker = make_breaker(failure_threshold=1, cooldown_seconds=999)
    router = Router(
        adapters={
            "groq": FakeAdapter("groq", [FatalProviderError("groq down")]),
            "openai": FakeAdapter("openai", [make_response("ok")]),
        },
        circuit_breakers={"groq": groq_breaker, "openai": openai_breaker},
    )

    await router.route("fast-cheap", make_request())

    states = router.get_circuit_states()
    assert states == {"groq": "open", "openai": "closed"}
