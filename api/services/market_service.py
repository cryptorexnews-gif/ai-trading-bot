import time
from typing import Any, Dict, List, Set

from api.helpers import post_hyperliquid_info


_VALID_INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def validate_coin(coin_raw: str, coin_pattern, known_pairs: Set[str]) -> str:
    coin = (coin_raw or "").strip().upper()
    if not coin_pattern.match(coin):
        return ""
    if coin not in known_pairs:
        # Allowed, but route may choose to log informational message
        return coin
    return coin


def validate_interval(interval: str, allowed_intervals: Set[str]) -> bool:
    return interval in allowed_intervals


def validate_limit(limit: int, min_limit: int = 1, max_limit: int = 500) -> bool:
    return limit is not None and min_limit <= int(limit) <= max_limit


def validate_n_sig_figs(n_sig_figs: int, min_val: int = 2, max_val: int = 5) -> bool:
    return n_sig_figs is not None and min_val <= int(n_sig_figs) <= max_val


def candle_request_payload(coin: str, interval: str, limit: int, now_ms: int = 0) -> Dict[str, Any]:
    current_ms = now_ms if now_ms > 0 else int(time.time() * 1000)
    interval_ms = _VALID_INTERVAL_MS.get(interval, 900_000)
    start_ms = current_ms - (interval_ms * limit)

    return {
        "type": "candleSnapshot",
        "req": {"coin": coin, "interval": interval, "startTime": start_ms, "endTime": current_ms},
    }


def serialize_candles_response(data: Any, coin: str, interval: str) -> Dict[str, Any]:
    if data is None or not isinstance(data, list):
        return {"candles": [], "coin": coin, "interval": interval, "timestamp": time.time()}

    candles_list: List[Dict[str, Any]] = []
    for c in data:
        candles_list.append({
            "time": c.get("t", 0),
            "open": float(c.get("o", 0)),
            "high": float(c.get("h", 0)),
            "low": float(c.get("l", 0)),
            "close": float(c.get("c", 0)),
            "volume": float(c.get("v", 0)),
        })

    return {
        "candles": candles_list,
        "coin": coin,
        "interval": interval,
        "timestamp": time.time(),
    }


def _parse_levels(raw: Any) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return result

    for level in raw:
        if not isinstance(level, dict):
            continue
        px = float(level.get("px", 0))
        sz = float(level.get("sz", 0))
        n = int(level.get("n", 0))
        if sz > 0:
            result.append({"px": px, "sz": sz, "n": n})

    return result


def serialize_orderbook_response(data: Any, coin: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {
            "bids": [],
            "asks": [],
            "coin": coin,
            "spread": 0,
            "spread_pct": 0,
            "timestamp": time.time(),
        }

    levels = data.get("levels", [[], []])
    if not levels or len(levels) < 2:
        return {
            "bids": [],
            "asks": [],
            "coin": coin,
            "spread": 0,
            "spread_pct": 0,
            "timestamp": time.time(),
        }

    raw_bids = levels[0] if len(levels) > 0 else []
    raw_asks = levels[1] if len(levels) > 1 else []

    bids = _parse_levels(raw_bids)
    asks = _parse_levels(raw_asks)

    spread = 0.0
    spread_pct = 0.0
    if bids and asks:
        best_bid = bids[0]["px"]
        best_ask = asks[0]["px"]
        spread = best_ask - best_bid
        mid = (best_ask + best_bid) / 2
        spread_pct = (spread / mid * 100) if mid > 0 else 0.0

    return {
        "bids": bids,
        "asks": asks,
        "coin": coin,
        "spread": round(spread, 8),
        "spread_pct": round(spread_pct, 6),
        "timestamp": time.time(),
    }


def serialize_orderbook_debug(data: Any, coin: str) -> Dict[str, Any]:
    return {
        "raw_keys": list(data.keys()) if isinstance(data, dict) else str(type(data)),
        "raw_data_preview": str(data)[:500],
        "coin": coin,
        "timestamp": time.time(),
    }


def fetch_candles_response(coin: str, interval: str, limit: int) -> Dict[str, Any]:
    payload = candle_request_payload(coin=coin, interval=interval, limit=limit)
    data = post_hyperliquid_info(payload)
    return serialize_candles_response(data=data, coin=coin, interval=interval)


def fetch_orderbook_response(coin: str, n_sig_figs: int) -> Dict[str, Any]:
    data = post_hyperliquid_info({
        "type": "l2Book",
        "coin": coin,
        "nSigFigs": n_sig_figs,
    })

    if data is None:
        return {
            "bids": [],
            "asks": [],
            "coin": coin,
            "spread": 0,
            "spread_pct": 0,
            "timestamp": 0,
        }

    return serialize_orderbook_response(data=data, coin=coin)


def fetch_orderbook_debug_response(coin: str) -> Dict[str, Any]:
    data = post_hyperliquid_info({
        "type": "l2Book",
        "coin": coin,
        "nSigFigs": 5,
    })

    if data is None:
        return {"error": "upstream_unavailable", "coin": coin}

    return serialize_orderbook_debug(data=data, coin=coin)