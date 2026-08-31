"""Per-provider circuit breaker, per PLAN.md Section 8.

Simple in-process 3-state machine, one instance per provider:

  CLOSED     Normal operation. Requests pass through. Consecutive failures
             are counted; reaching `failure_threshold` trips the breaker OPEN.

  OPEN       Calls are skipped entirely (no network attempt) for
             `cooldown_seconds`. After the cooldown elapses, the breaker
             transitions to HALF_OPEN on the next state check.

  HALF_OPEN  Exactly one trial request is allowed through. Success closes
             the breaker (state -> CLOSED, failure count reset). Failure
             reopens it and the cooldown restarts.

This mirrors PLAN.md's description precisely: "after N consecutive failures
... trip to OPEN for a cooldown period ... after cooldown, allow exactly one
trial request through; success -> CLOSED, failure -> OPEN again (reset
cooldown)."
"""
import time
from enum import Enum


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: float):
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    @property
    def state(self) -> CircuitState:
        """Current state, lazily transitioning OPEN -> HALF_OPEN once the
        cooldown has elapsed."""
        self._maybe_expire_cooldown()
        return self._state

    def allow_request(self) -> bool:
        """Whether a call should be attempted right now.

        CLOSED always allows. OPEN never allows (until cooldown expires, at
        which point the state check below flips it to HALF_OPEN). HALF_OPEN
        allows exactly one in-flight probe at a time.
        """
        state = self.state  # triggers OPEN -> HALF_OPEN transition if due
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.OPEN:
            return False

        # HALF_OPEN: only one trial request at a time.
        if self._half_open_probe_in_flight:
            return False
        self._half_open_probe_in_flight = True
        return True

    def record_success(self) -> None:
        """A request succeeded: close the breaker and reset failure tracking."""
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        self._half_open_probe_in_flight = False

    def record_failure(self) -> None:
        """A request failed. In HALF_OPEN, this immediately reopens the
        breaker. In CLOSED, this counts toward the failure threshold."""
        if self._state == CircuitState.HALF_OPEN:
            self._trip_open()
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._trip_open()

    def _maybe_expire_cooldown(self) -> None:
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            if time.monotonic() - self._opened_at >= self._cooldown_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_probe_in_flight = False

    def _trip_open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_probe_in_flight = False
