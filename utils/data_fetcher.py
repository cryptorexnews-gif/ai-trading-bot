import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from utils.http import create_robust_session

logger = logging.getLogger(__name__)

HYPERLIQUID_BASE_URL = "https://api.hyperliquid.xyz"


class HyperliquidDataFetcher:
    """
    Fetches raw market data from Hyperliquid API.
    Handles connections, retries, and basic data validation.
    """

    def __init__(self, base_url: str = HYPERLIQUID_BASE_URL):
        self.base_url = base_url
        self.session = create_robust_session()
        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at: float = 0.0
        self._meta_cache_ttl: float = 120.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at: float = 0.0
        self._mids_cache_ttl: float = 15.0
        self._funding_cache: Optional[List[Dict[str, Any]]] = None
        self._funding_cache_at: float = 0.0
        self._funding_cache_ttl: float = 60.0

    def _d(self, value: Any) -> Decimal:
        """Convert to Decimal safely."""
        return Decimal(str(value)) if value is not None else Decimal("0")

    def _post_info(self, payload: Dict[str, Any], timeout: int = 15) -> Optional[Any]:
        """Make POST request to /info endpoint with error handling."""
        try:
            response = self.session.post(f"{self.base_url}/info", json=payload, timeout=timeout)
            if response.status_code != 200:
                logger.error(f"Hyperliquid /info error: status={response.status_code}, type={payload.get('type', 'unknown')}")
                return None
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Hyperliquid /info timeout for type={payload.get('type', 'unknown')}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Hyperliquid /info connection error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Hyperliquid /info request error: {e}")
            return None

    def get_all_mids(self, force_refresh: bool = False) -> Optional[Dict[str, str]]:
        """Get all mid prices."""
        now = time.time()
        if not force_refresh and self._mids_cache and (now - self._mids_cache_at) < self._mids_cache_ttl:
            return self._mids_cache
        result = self._post_info({"type": "allMids"})
        if result is not None:
            self._mids_cache = result
            self._mids_cache_at = now
        return self._mids_cache

    def get_meta(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get exchange metadata."""
        now = time.time()
        if not force_refresh and self._meta_cache and (now - self._meta_cache_at) < self._meta_cache_ttl:
            return self._meta_cache
        result = self._post_info({"type": "meta"})
        if result is not None:
            self._meta_cache = result
            self._meta_cache_at = now
        return self._meta_cache

    def _get_asset_ctxs(self, force_refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Get asset contexts (funding rates, open interest)."""
        now = time.time()
        if not force_refresh and self._funding_cache and (now - self._funding_cache_at) < self._funding_cache_ttl:
            return self._funding_cache
        result = self._post_info({"type": "metaAndAssetCtxs"})
        if result is not None and isinstance(result, list) and len(result) >= 2:
            self._funding_cache = result
            self._funding_cache_at = now
        return self._funding_cache

    def get_funding_for_coin(self, coin: str) -> Dict[str, Any]:
        """Get funding rate, open interest, and premium for a coin."""
        data = self._get_asset_ctxs()
        if not data or len(data) < 2:
            return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": 10}

        meta_part = data[0]
        ctx_part = data[1]
        universe = meta_part.get("universe", [])

        for i, asset in enumerate(universe):
            if asset.get("name") == coin:
                max_lev = int(asset.get("maxLeverage", 10))
                if i < len(ctx_part):
                    ctx = ctx_part[i]
                    return {
                        "funding_rate": str(ctx.get("funding", "0")),
                        "open_interest": str(ctx.get("openInterest", "0")),
                        "premium": str(ctx.get("premium", "0")),
                        "max_leverage": max_lev,
                    }
                return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": max_lev}

        return {"funding_rate": "0", "open_interest": "0", "premium": "0", "max_leverage": 10}

    def get_candle_snapshot(self, coin: str, interval: str = "5m", limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Get candle data for a coin."""
        now_ms = int(time.time() * 1000)
        interval_ms_map = {
            "1m": 60_000, "3m": 180_000, "5m": 300_000,
            "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
        }
        interval_ms = interval_ms_map.get(interval, 300_000)
        start_ms = now_ms - (interval_ms * limit)

        data = self._post_info({
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval, "startTime": start_ms, "endTime": now_ms}
        }, timeout=15)

        if data is None:
            return None
        if not isinstance(data, list):
            logger.error(f"Unexpected candle data format for {coin}: {type(data)}")
            return None

        candles = []
        for candle in data:
            candles.append({
                "open_time": candle.get("t", 0),
                "open": self._d(candle.get("o", "0")),
                "high": self._d(candle.get("h", "0")),
                "low": self._d(candle.get("l", "0")),
                "close": self._d(candle.get("c", "0")),
                "volume": self._d(candle.get("v", "0")),
            })
        return candles