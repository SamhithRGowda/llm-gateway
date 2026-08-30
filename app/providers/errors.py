"""Provider error hierarchy.

Per PLAN.md Section 6 (Provider Abstraction) and Section 8 (Retry + Fallback
Semantics):

- RetryableProviderError: connection errors, timeouts, HTTP 5xx -- eligible
  for same-provider retry.
- ProviderRateLimitedError: HTTP 429 from the provider -- also retryable,
  but carries an optional Retry-After hint so callers can respect it.
- FatalProviderError: HTTP 400/401/403/404 -- not retryable within the same
  provider (retrying won't help a malformed request or an auth failure).
"""


class ProviderError(Exception):
    """Base class for all provider-adapter errors."""


class RetryableProviderError(ProviderError):
    """A transient failure (timeout, connection error, HTTP 5xx)."""


class ProviderRateLimitedError(RetryableProviderError):
    """The provider returned HTTP 429."""

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class FatalProviderError(ProviderError):
    """A non-retryable failure (HTTP 400/401/403/404)."""
