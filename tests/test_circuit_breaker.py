import time

from app.reliability.circuit_breaker import CircuitBreaker, CircuitState


def make_breaker(failure_threshold: int = 3, cooldown_seconds: float = 0.2) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds)


def test_closed_breaker_allows_requests():
    breaker = make_breaker()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_failures_below_threshold_stay_closed():
    breaker = make_breaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_reaching_failure_threshold_trips_open():
    breaker = make_breaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN


def test_open_breaker_skips_requests():
    breaker = make_breaker(failure_threshold=1)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_success_resets_failure_count_while_closed():
    breaker = make_breaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    # Two more failures should not trip it (count was reset), only a third would.
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED


def test_cooldown_transitions_open_to_half_open():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=0.05)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    time.sleep(0.06)
    assert breaker.state == CircuitState.HALF_OPEN


def test_half_open_allows_exactly_one_probe():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=0.05)
    breaker.record_failure()
    time.sleep(0.06)
    assert breaker.state == CircuitState.HALF_OPEN

    assert breaker.allow_request() is True  # the one probe
    assert breaker.allow_request() is False  # no second concurrent probe


def test_successful_half_open_probe_closes_circuit():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=0.05)
    breaker.record_failure()
    time.sleep(0.06)
    assert breaker.state == CircuitState.HALF_OPEN

    assert breaker.allow_request() is True
    breaker.record_success()

    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_failed_half_open_probe_reopens_circuit():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=0.05)
    breaker.record_failure()
    time.sleep(0.06)
    assert breaker.state == CircuitState.HALF_OPEN

    assert breaker.allow_request() is True
    breaker.record_failure()

    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_reopening_restarts_the_cooldown():
    breaker = make_breaker(failure_threshold=1, cooldown_seconds=0.1)
    breaker.record_failure()
    time.sleep(0.11)
    assert breaker.state == CircuitState.HALF_OPEN

    breaker.allow_request()
    breaker.record_failure()  # reopens, cooldown restarts
    assert breaker.state == CircuitState.OPEN

    # Not yet elapsed since the *second* trip -- should still be OPEN even
    # though it's been longer than the cooldown since the *first* trip.
    time.sleep(0.02)
    assert breaker.state == CircuitState.OPEN
