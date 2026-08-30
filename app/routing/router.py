"""Routing engine, per PLAN.md Section 7 (Phase 3 scope).

For a given model alias, resolves the configured provider/model chain and,
for each entry in order:
  - calls the provider via the generic retry wrapper (app.reliability.retry),
  - on success, returns immediately (marking fallback_occurred if this was
    not the first entry tried),
  - on exhausted retries, records the failure and moves to the next entry.

If every entry in the chain fails, raises AllProvidersFailedError with the
full attempt history.

Explicitly NOT in scope for Phase 3 (per PLAN.md): circuit-breaker-based
skipping of unhealthy providers (Phase 6), and metrics/logging of fallback
events (Phase 7).
"""
from dataclasses import dataclass, field

from app.providers.base import NormalizedRequest, NormalizedResponse, ProviderAdapter
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
    per-provider retry + fallback across that chain."""

    def __init__(self, adapters: dict[str, ProviderAdapter]):
        self._adapters = adapters

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

            try:
                response = await with_retry(
                    func=_bind_send(adapter, entry.model, request),
                    is_retryable=adapter.is_retryable_error,
                )
            except Exception as exc:
                attempts.append(
                    ProviderAttempt(
                        provider=entry.provider,
                        model=entry.model,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
                continue

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
