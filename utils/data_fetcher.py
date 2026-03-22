import logging
import time
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
        self._meta_cache_ttl: float = 86400.0  # 1 giorno (24 ore)

        # Mids: cache molto corta per evitare dati stantii in trading live
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at: float = 0.0
        self._mids_cache_ttl: float = 5.0  # 5 secondi

        # Funding/OI: dati meno sensibili al secondo, ma più freschi di prima
        self._funding_cache: Optional[List[Dict[str, Any]]] = None
        self._funding_cache_at: float = 0.0
        self._funding_cache_ttl: float = 60.0  # 60 secondi

        # Candle cache per ridurre carico API e latenza ciclo
        self._candles_cache: Dict[str, Dict[str, Any]] = {}
        self._candle_cache_ttl_by_interval: Dict[str, float] = {
            "1m": 10.0,
            "3m": 15.0,
            "5m": 20.0,
            "15m": 30.0,
            "1h": 60.0,
            "4h": 120.0,
            "1d": 300.0,
        }

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

    def get_batch_info(self, requests_payload: List[Dict[str, Any]], timeout: int = 15) -> List[Any]:
        """Batch helper for Hyperliquid /info endpoint."""
        if not requests_payload:
            return []
        result = self._post_info({"type": "batch", "requests": requests_payload}, timeout=timeout)
        return result if isinstance(result, list) else []

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

    def get_multiple_mids(self, coins: List[str], force_refresh: bool = False) -> Dict[str, Decimal]:
        """
        Get mid prices for a subset of coins using one allMids call + local filtering.
        """
        mids = self.get_all_mids(force_refresh=force_refresh)
        if not isinstance(mids, dict):
            return {}

        result: Dict[str, Decimal] = {}
        for coin in coins:
            normalized = str(coin or "").strip().upper()
            if not normalized or normalized not in mids:
                continue
            result[normalized] = self._d(mids[normalized])

        return result

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

    def _candle_cache_key(self, coin: str, interval: str, limit: int) -> str:
        return f"{coin.upper()}:{interval}:{int(limit)}"

    def _candle_cache_ttl(self, interval: str) -> float:
        return self._candle_cache_ttl_by_interval.get(interval, 20.0)

    def get_candle_snapshot(self, coin: str, interval: str = "5m", limit: int = 100) -> Optional[List[Dict[str, Any]]]:
        """Get candle data for a coin."""
        cache_key = self._candle_cache_key(coin, interval, limit)
        now = time.time()
        ttl = self._candle_cache_ttl(interval)

        cached = self._candles_cache.get(cache_key)
        if cached and (now - float(cached.get("at", 0.0))) < ttl:
            candles = cached.get("data")
            if isinstance(candles, list):
                return [dict(c) for c in candles]

        now_ms = int(now * 1000)
        interval_ms_map = {
            "1m": 60_000,
            "3m": 180_000,
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000
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

        self._candles_cache[cache_key] = {
            "at": now,
            "data": candles,
        }

        return [dict(c) for c in candles]