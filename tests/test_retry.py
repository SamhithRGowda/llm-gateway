import pytest

from app.providers.errors import FatalProviderError, RetryableProviderError
from app.reliability.retry import MAX_ATTEMPTS, with_retry

pytestmark = pytest.mark.asyncio


async def _no_op_sleep(_seconds: float) -> None:
    return None


async def test_succeeds_without_retry_when_first_call_succeeds():
    calls = []

    async def func():
        calls.append(1)
        return "ok"

    result = await with_retry(func, is_retryable=lambda exc: True, sleep=_no_op_sleep)

    assert result == "ok"
    assert len(calls) == 1


async def test_retries_transient_failures_then_succeeds():
    attempts = {"count": 0}

    async def func():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RetryableProviderError("transient")
        return "recovered"

    result = await with_retry(
        func,
        is_retryable=lambda exc: isinstance(exc, RetryableProviderError),
        sleep=_no_op_sleep,
    )

    assert result == "recovered"
    assert attempts["count"] == 3  # exactly MAX_ATTEMPTS


async def test_raises_after_exhausting_max_attempts():
    attempts = {"count": 0}

    async def func():
        attempts["count"] += 1
        raise RetryableProviderError("always fails")

    with pytest.raises(RetryableProviderError):
        await with_retry(
            func,
            is_retryable=lambda exc: isinstance(exc, RetryableProviderError),
            sleep=_no_op_sleep,
        )

    assert attempts["count"] == MAX_ATTEMPTS


async def test_non_retryable_error_raised_immediately_without_extra_attempts():
    attempts = {"count": 0}

    async def func():
        attempts["count"] += 1
        raise FatalProviderError("bad request")

    with pytest.raises(FatalProviderError):
        await with_retry(
            func,
            is_retryable=lambda exc: isinstance(exc, RetryableProviderError),
            sleep=_no_op_sleep,
        )

    assert attempts["count"] == 1


async def test_sleep_is_called_between_retries_with_increasing_delay():
    sleeps = []

    async def record_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    attempts = {"count": 0}

    async def func():
        attempts["count"] += 1
        if attempts["count"] < MAX_ATTEMPTS:
            raise RetryableProviderError("transient")
        return "done"

    await with_retry(
        func,
        is_retryable=lambda exc: isinstance(exc, RetryableProviderError),
        sleep=record_sleep,
    )

    assert len(sleeps) == MAX_ATTEMPTS - 1
    # base 0.25s, multiplier 2, capped at 2s, plus up to 10% jitter
    assert 0.25 <= sleeps[0] < 0.275
    assert 0.5 <= sleeps[1] < 0.55
