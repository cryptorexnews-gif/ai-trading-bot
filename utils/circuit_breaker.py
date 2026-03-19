import logging
import time
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit breaker for external API calls.
    Prevents cascading failures by failing fast when a service is down.
    Transitions: CLOSED -> OPEN (after threshold failures)
                 OPEN -> HALF_OPEN (after recovery_timeout elapsed)
                 HALF_OPEN -> CLOSED (on success) or OPEN (on failure)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exception = expected_exception

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0

    def _maybe_transition_to_half_open(self) -> None:
        """Check if enough time has passed to try half-open."""
        if self.state != CircuitState.OPEN:
            return
        if self.last_failure_time is None:
            return
        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.recovery_timeout:
            logger.info(
                f"Circuit '{self.name}' transitioning OPEN -> HALF_OPEN "
                f"after {elapsed:.1f}s (timeout={self.recovery_timeout}s)"
            )
            self.state = CircuitState.HALF_OPEN
            self.half_open_calls = 0

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.

        Raises:
            CircuitBreakerOpenError: If circuit is open and recovery timeout not elapsed
            Exception: Any exception from the wrapped function
        """
        self._maybe_transition_to_half_open()

        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                f"Circuit '{self.name}' is OPEN. "
                f"Will retry after {self.recovery_timeout}s from last failure."
            )

        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitState.OPEN
                self.last_failure_time = time.time()
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' HALF_OPEN max calls ({self.half_open_max_calls}) exceeded, re-opening"
                )
            self.half_open_calls += 1

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit '{self.name}' recovered, HALF_OPEN -> CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    def _on_failure(self) -> None:
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit '{self.name}' CLOSED -> OPEN after {self.failure_count} consecutive failures"
            )
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit '{self.name}' failed in HALF_OPEN, re-opening")
            self.state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        logger.info(f"Circuit '{self.name}' manually reset to CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "half_open_calls": self.half_open_calls,
            "recovery_timeout": self.recovery_timeout,
            "failure_threshold": self.failure_threshold
        }


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


# Global registry of circuit breakers
_circuit_breakers: Dict[str, CircuitBreaker] = {}


def get_or_create_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    half_open_max_calls: int = 3,
    expected_exception: type = Exception
) -> CircuitBreaker:
    """
    Get or create a circuit breaker by name.
    Useful for sharing circuit breakers across modules.
    """
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            half_open_max_calls=half_open_max_calls,
            expected_exception=expected_exception
        )
    return _circuit_breakers[name]


def get_all_circuit_states() -> Dict[str, Dict[str, Any]]:
    """Get states of all circuit breakers."""
    return {name: cb.get_state() for name, cb in _circuit_breakers.items()}