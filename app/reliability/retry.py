"""Generic async retry-with-backoff helper, per PLAN.md Section 8:

    Retry policy: max 2 retries per provider (3 attempts total), exponential
    backoff with jitter: base 0.25s, multiplier 2, capped at 2s.

This is intentionally generic (not provider-specific) so it can wrap any
awaitable call. In Phase 3, the router will use this to wrap
`ProviderAdapter.send(...)` calls; for Phase 2 it is exercised directly in
tests against adapter calls to demonstrate the retry behavior end-to-end.
"""
import asyncio
import random
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

MAX_ATTEMPTS = 3  # 1 initial attempt + 2 retries
BASE_DELAY_SECONDS = 0.25
BACKOFF_MULTIPLIER = 2
MAX_DELAY_SECONDS = 2.0


def _delay_for_attempt(attempt: int) -> float:
    """attempt is 1-indexed (delay before the 2nd, 3rd, ... attempt)."""
    delay = min(BASE_DELAY_SECONDS * (BACKOFF_MULTIPLIER ** (attempt - 1)), MAX_DELAY_SECONDS)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


async def with_retry(
    func: Callable[[], Awaitable[T]],
    is_retryable: Callable[[Exception], bool],
    max_attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Call `func()`, retrying on retryable failures up to `max_attempts` total.

    `is_retryable(exc)` decides whether a given exception should be retried.
    Non-retryable exceptions propagate immediately without consuming a retry.
    If all attempts are exhausted, the last exception is re-raised.
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            return await func()
        except Exception as exc:
            if attempt >= max_attempts or not is_retryable(exc):
                raise
            await sleep(_delay_for_attempt(attempt))
