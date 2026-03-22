import time
from typing import Callable, List, Set


class AvailablePairsService:
    """Caches and filters available Hyperliquid pairs for API routes."""

    def __init__(
        self,
        fetch_universe_fn: Callable[[], List[str]],
        coin_pattern,
        fallback_pairs: Set[str],
        cache_ttl_sec: float = 300.0,
    ):
        self._fetch_universe_fn = fetch_universe_fn
        self._coin_pattern = coin_pattern
        self._fallback_pairs = set(fallback_pairs)
        self._cache_ttl_sec = float(cache_ttl_sec)

        self._cache: List[str] = []
        self._cache_at: float = 0.0

    def get_available_pairs(self) -> List[str]:
        now = time.time()

        if self._cache and (now - self._cache_at) < self._cache_ttl_sec:
            return list(self._cache)

        fresh = [coin for coin in self._fetch_universe_fn() if self._coin_pattern.match(coin)]
        if fresh:
            self._cache = fresh
            self._cache_at = now
            return list(self._cache)

        if self._cache:
            return list(self._cache)

        return sorted(self._fallback_pairs)

    def get_live_allowed_pairs_set(self) -> Set[str]:
        return set(self.get_available_pairs())