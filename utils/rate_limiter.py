import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """
    Token bucket rate limiter.
    Allows burst up to max_tokens, refills at rate tokens_per_second.
    Thread-safe.
    """

    def __init__(
        self,
        name: str,
        max_tokens: int = 20,
        tokens_per_second: float = 2.0
    ):
        self.name = name
        self.max_tokens = max(1, int(max_tokens))
        self.tokens_per_second = max(0.01, float(tokens_per_second))
        self._tokens = float(self.max_tokens)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()
        self._total_waits = 0
        self._total_wait_time = 0.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.max_tokens,
            self._tokens + elapsed * self.tokens_per_second
        )
        self._last_refill = now

    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        Acquire tokens, blocking until available or timeout.
        If timeout is None, waits indefinitely.
        Returns True if acquired, False if timed out.
        """
        tokens = max(1, int(tokens))
        deadline = None if timeout is None else (time.monotonic() + max(0.0, timeout))
        waited = False
        wait_start = time.monotonic()

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    if waited:
                        wait_duration = time.monotonic() - wait_start
                        self._total_waits += 1
                        self._total_wait_time += wait_duration
                        logger.debug(
                            f"Rate limiter '{self.name}': waited {wait_duration:.2f}s"
                        )
                    return True

            if deadline is not None and time.monotonic() >= deadline:
                logger.warning(
                    f"Rate limiter '{self.name}': timeout after {timeout}s"
                )
                return False

            waited = True
            missing_tokens = max(0.0, tokens - self._tokens)
            sleep_time = min(0.1, max(0.01, missing_tokens / self.tokens_per_second))
            time.sleep(sleep_time)

    def try_acquire(self, tokens: int = 1) -> bool:
        """Non-blocking acquire. Returns True if tokens available."""
        tokens = max(1, int(tokens))
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def get_stats(self) -> Dict[str, float]:
        with self._lock:
            self._refill()
            return {
                "name": self.name,
                "available_tokens": self._tokens,
                "max_tokens": self.max_tokens,
                "tokens_per_second": self.tokens_per_second,
                "total_waits": self._total_waits,
                "total_wait_time": round(self._total_wait_time, 3),
            }


class AdaptiveRateLimiter:
    """
    Adaptive limiter: aggiusta automaticamente il rate in base ai tempi di risposta.
    Mantiene un token bucket interno e aggiorna il refill rate periodicamente.
    """

    def __init__(
        self,
        name: str,
        initial_rate: float = 10.0,
        min_rate: float = 2.0,
        max_rate: float = 50.0,
        max_tokens: int = 30
    ):
        self.name = name
        self.min_rate = max(0.1, float(min_rate))
        self.max_rate = max(self.min_rate, float(max_rate))
        self._rate = min(self.max_rate, max(self.min_rate, float(initial_rate)))

        self.max_tokens = max(1, int(max_tokens))
        self._tokens = float(self.max_tokens)
        self._last_refill = time.monotonic()

        self._response_times: list[float] = []
        self._last_adjustment = time.monotonic()
        self._adjust_every_n = 10
        self._adjust_every_sec = 60.0

        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.max_tokens, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        tokens = max(1, int(tokens))
        deadline = None if timeout is None else (time.monotonic() + max(0.0, timeout))

        while True:
            with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True

            if deadline is not None and time.monotonic() >= deadline:
                return False

            time.sleep(0.02)

    def try_acquire(self, tokens: int = 1) -> bool:
        tokens = max(1, int(tokens))
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def adjust_based_on_response_time(self, response_time: float) -> None:
        """
        Aggiorna il rate in modo semplice:
        - se media > 2.0s, riduce del 20%
        - se media < 0.5s, aumenta del 20%
        """
        if response_time <= 0:
            return

        with self._lock:
            self._response_times.append(float(response_time))
            if len(self._response_times) > self._adjust_every_n:
                self._response_times = self._response_times[-self._adjust_every_n:]

            now = time.monotonic()
            should_adjust = (
                len(self._response_times) >= self._adjust_every_n
                or (now - self._last_adjustment) >= self._adjust_every_sec
            )
            if not should_adjust:
                return

            avg_response = sum(self._response_times) / len(self._response_times)
            old_rate = self._rate

            if avg_response > 2.0:
                self._rate = max(self.min_rate, self._rate * 0.8)
            elif avg_response < 0.5:
                self._rate = min(self.max_rate, self._rate * 1.2)

            self._last_adjustment = now
            self._response_times.clear()

            if self._rate != old_rate:
                logger.info(
                    f"Adaptive limiter '{self.name}' rate adjusted: {old_rate:.2f} -> {self._rate:.2f} "
                    f"(avg_response={avg_response:.3f}s)"
                )

    def get_stats(self) -> Dict[str, float]:
        with self._lock:
            self._refill()
            return {
                "name": self.name,
                "available_tokens": self._tokens,
                "max_tokens": float(self.max_tokens),
                "current_rate": self._rate,
                "min_rate": self.min_rate,
                "max_rate": self.max_rate,
            }


# Global rate limiters
_rate_limiters: Dict[str, TokenBucketRateLimiter] = {}
_adaptive_rate_limiters: Dict[str, AdaptiveRateLimiter] = {}


def get_rate_limiter(
    name: str,
    max_tokens: int = 20,
    tokens_per_second: float = 2.0
) -> TokenBucketRateLimiter:
    """Get or create a named rate limiter."""
    if name not in _rate_limiters:
        _rate_limiters[name] = TokenBucketRateLimiter(
            name=name,
            max_tokens=max_tokens,
            tokens_per_second=tokens_per_second
        )
    return _rate_limiters[name]


def get_adaptive_rate_limiter(
    name: str,
    initial_rate: float = 10.0,
    min_rate: float = 2.0,
    max_rate: float = 50.0,
    max_tokens: int = 30
) -> AdaptiveRateLimiter:
    """Get or create a named adaptive rate limiter."""
    if name not in _adaptive_rate_limiters:
        _adaptive_rate_limiters[name] = AdaptiveRateLimiter(
            name=name,
            initial_rate=initial_rate,
            min_rate=min_rate,
            max_rate=max_rate,
            max_tokens=max_tokens,
        )
    return _adaptive_rate_limiters[name]


def get_all_rate_limiter_stats() -> Dict[str, Dict[str, float]]:
    """Get stats for all rate limiters."""
    stats: Dict[str, Dict[str, float]] = {}
    for name, rl in _rate_limiters.items():
        stats[name] = rl.get_stats()
    for name, rl in _adaptive_rate_limiters.items():
        stats[f"{name}_adaptive"] = rl.get_stats()
    return stats