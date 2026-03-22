import time
from typing import Any, Callable, Dict, List, Optional

from exchange.transport import post_exchange_with_circuit_breaker, post_json_with_circuit_breaker


class ExchangeAPIClient:
    """Thin API client for Hyperliquid /info and /exchange with single-source cache ownership."""

    def __init__(self, session, base_url, info_timeout, exchange_timeout, info_cb, exchange_cb, meta_cache_ttl_sec=120):
        self.session = session
        self.base_url = base_url
        self.info_timeout = info_timeout
        self.exchange_timeout = exchange_timeout
        self.info_cb = info_cb
        self.exchange_cb = exchange_cb
        self.meta_cache_ttl_sec = meta_cache_ttl_sec

        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at = 0.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at = 0.0
        self._mids_cache_ttl = 30.0
        self._open_orders_cache_by_user: Dict[str, Dict[str, Any]] = {}
        self._open_orders_cache_ttl_sec = 2.0

    def post_info(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        return post_json_with_circuit_breaker(
            session=self.session,
            url=f"{self.base_url}/info",
            payload=payload,
            timeout=timeout or self.info_timeout,
            circuit_breaker=self.info_cb,
            endpoint_label=f"/info type={payload.get('type', 'unknown')}",
        )

    def post_exchange(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        return post_exchange_with_circuit_breaker(
            session=self.session,
            url=f"{self.base_url}/exchange",
            payload=payload,
            timeout=timeout or self.exchange_timeout,
            circuit_breaker=self.exchange_cb,
            endpoint_label="/exchange",
        )

    def get_batch_info(self, requests_payload: List[Dict[str, Any]], timeout: Optional[int] = None) -> List[Any]:
        if not requests_payload:
            return []
        result = self.post_info({"type": "batch", "requests": requests_payload}, timeout=timeout)
        return result if isinstance(result, list) else []

    def get_meta(
        self,
        force_refresh: bool = False,
        fetcher: Optional[Callable[[Dict[str, Any], Optional[int]], Optional[Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        if not force_refresh and self._meta_cache and (now - self._meta_cache_at) < self.meta_cache_ttl_sec:
            return self._meta_cache

        effective_fetcher = fetcher if fetcher is not None else self.post_info
        meta = effective_fetcher({"type": "meta"}, None)
        if meta is not None:
            self._meta_cache = meta
            self._meta_cache_at = now
        return self._meta_cache

    def get_all_mids(
        self,
        force_refresh: bool = False,
        fetcher: Optional[Callable[[Dict[str, Any], Optional[int]], Optional[Any]]] = None,
    ) -> Optional[Dict[str, str]]:
        now = time.time()
        if not force_refresh and self._mids_cache and (now - self._mids_cache_at) < self._mids_cache_ttl:
            return self._mids_cache

        effective_fetcher = fetcher if fetcher is not None else self.post_info
        mids = effective_fetcher({"type": "allMids"}, None)
        if mids is not None:
            self._mids_cache = mids
            self._mids_cache_at = now
        return self._mids_cache

    def get_user_state(
        self,
        user: str,
        fetcher: Optional[Callable[[Dict[str, Any], Optional[int]], Optional[Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        effective_fetcher = fetcher if fetcher is not None else self.post_info
        return effective_fetcher({"type": "clearinghouseState", "user": user}, None)

    def get_open_orders(
        self,
        user: str,
        force_refresh: bool = False,
        fetcher: Optional[Callable[[Dict[str, Any], Optional[int]], Optional[Any]]] = None,
    ) -> List[Dict[str, Any]]:
        effective_user = str(user or "").strip()
        now = time.time()

        cached = self._open_orders_cache_by_user.get(effective_user)
        if not force_refresh and cached and (now - float(cached.get("at", 0.0))) < self._open_orders_cache_ttl_sec:
            data = cached.get("data", [])
            return data if isinstance(data, list) else []

        effective_fetcher = fetcher if fetcher is not None else self.post_info
        data = effective_fetcher({"type": "openOrders", "user": effective_user}, None)
        orders = data if isinstance(data, list) else []
        self._open_orders_cache_by_user[effective_user] = {"at": now, "data": orders}
        return orders