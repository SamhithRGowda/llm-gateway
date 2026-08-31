"""Routing engine, per PLAN.md Section 7 (Phase 3) and Section 8 (Phase 6).

For a given model alias, resolves the configured provider/model chain and,
for each entry in order:
  - consults that provider's circuit breaker; if OPEN, skips the provider
    immediately with no network attempt (Phase 6),
  - otherwise calls the provider via the generic retry wrapper
    (app.reliability.retry), preserving Phase 3's retry + fallback behavior,
  - on success, records the success against the breaker and returns
    immediately (marking fallback_occurred if this was not the first entry
    tried),
  - on exhausted retries, records the failure against the breaker and moves
    to the next entry.

If every entry in the chain fails (or is skipped), raises
AllProvidersFailedError with the full attempt history.
"""
from dataclasses import dataclass, field

from app.config import settings
from app.providers.base import NormalizedRequest, NormalizedResponse, ProviderAdapter
from app.reliability.circuit_breaker import CircuitBreaker
from app.reliability.retry import with_retry
from app.routing.config import resolve_chain


@dataclass
class ProviderAttempt:
    provider: str
    model: str
    error_type: str
    message: str


class AllProvidersFailedError(Exception):
    def __init__(self, alias: str, attempts: list[ProviderAttempt]):
        super().__init__(f"All providers failed for model alias {alias!r}")
        self.alias = alias
        self.attempts = attempts


@dataclass
class RoutedResponse:
    response: NormalizedResponse
    provider: str
    model: str
    fallback_occurred: bool
    attempts: list[ProviderAttempt] = field(default_factory=list)


class Router:
    """Resolves a model alias to a provider chain and orchestrates
    per-provider circuit-breaker gating, retry, and fallback across that
    chain."""

    def __init__(
        self,
        adapters: dict[str, ProviderAdapter],
        circuit_breakers: dict[str, CircuitBreaker] | None = None,
    ):
        self._adapters = adapters
        if circuit_breakers is not None:
            self._circuit_breakers = circuit_breakers
        else:
            self._circuit_breakers = {
                name: CircuitBreaker(
                    failure_threshold=settings.circuit_breaker_failure_threshold,
                    cooldown_seconds=settings.circuit_breaker_cooldown_seconds,
                )
                for name in adapters
            }

    def get_circuit_states(self) -> dict[str, str]:
        """Current circuit state per provider (e.g. {"openai": "closed"}),
        for reporting via /health."""
        return {name: breaker.state.value for name, breaker in self._circuit_breakers.items()}

    async def route(self, alias: str, request: NormalizedRequest) -> RoutedResponse:
        chain = resolve_chain(alias)
        attempts: list[ProviderAttempt] = []

        for index, entry in enumerate(chain):
            adapter = self._adapters.get(entry.provider)
            if adapter is None:
                attempts.append(
                    ProviderAttempt(
                        provider=entry.provider,
                        model=entry.model,
                        error_type="ConfigurationError",
                        message=f"No adapter registered for provider {entry.provider!r}",
                    )
                )
                continue

            breaker = self._circuit_breakers.get(entry.provider)
            if breaker is not None and not breaker.allow_request():
                attempts.append(
                    ProviderAttempt(
                        provider=entry.provider,
                        model=entry.model,
                        error_type="CircuitOpen",
                        message=f"Circuit breaker open for provider {entry.provider!r}; skipped without a network attempt",
                    )
                )
                continue

            try:
                response = await with_retry(
                    func=_bind_send(adapter, entry.model, request),
                    is_retryable=adapter.is_retryable_error,
                )
            except Exception as exc:
                if breaker is not None:
                    breaker.record_failure()
                attempts.append(
                    ProviderAttempt(
                        provider=entry.provider,
                        model=entry.model,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
                continue

            if breaker is not None:
                breaker.record_success()

            return RoutedResponse(
                response=response,
                provider=entry.provider,
                model=entry.model,
                fallback_occurred=index > 0,
                attempts=attempts,
            )

        raise AllProvidersFailedError(alias=alias, attempts=attempts)


def _bind_send(adapter: ProviderAdapter, model: str, request: NormalizedRequest):
    """Capture (adapter, model, request) for this loop iteration so with_retry
    can call it repeatedly without a late-binding closure bug."""

    async def _call():
        return await adapter.send(model, request)

    return _call
