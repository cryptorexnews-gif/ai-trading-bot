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


# Global rate limiters
_rate_limiters: Dict[str, TokenBucketRateLimiter] = {}


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


def get_all_rate_limiter_stats() -> Dict[str, Dict[str, float]]:
    """Get stats for all rate limiters."""
    return {name: rl.get_stats() for name, rl in _rate_limiters.items()}