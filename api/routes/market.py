"""
Market data endpoints — proxies Hyperliquid API for candles and order book.
"""

import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.helpers import post_hyperliquid_info

market_bp = Blueprint("market", __name__)


@market_bp.route("/api/candles", methods=["GET"])
@require_api_key
def candles():
    """Get candlestick data from Hyperliquid for price chart."""
    coin = request.args.get("coin", "BTC").upper()
    interval = request.args.get("interval", "15m")
    limit = request.args.get("limit", 100, type=int)
    limit = min(limit, 500)

    interval_ms_map = {
        "1m": 60_000, "5m": 300_000, "15m": 900_000,
        "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
    }
    interval_ms = interval_ms_map.get(interval, 900_000)
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (interval_ms * limit)

    data = post_hyperliquid_info({
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": start_ms,
            "endTime": now_ms
        }
    })

    if data is None or not isinstance(data, list):
        return jsonify({"candles": [], "coin": coin, "interval": interval, "timestamp": time.time()})

    candles_list = []
    for c in data:
        candles_list.append({
            "time": c.get("t", 0),
            "open": float(c.get("o", 0)),
            "high": float(c.get("h", 0)),
            "low": float(c.get("l", 0)),
            "close": float(c.get("c", 0)),
            "volume": float(c.get("v", 0)),
        })

    return jsonify({
        "candles": candles_list,
        "coin": coin,
        "interval": interval,
        "timestamp": time.time()
    })


@market_bp.route("/api/orderbook", methods=["GET"])
@require_api_key
def orderbook():
    """
    Get L2 order book from Hyperliquid with maximum depth.
    
    Hyperliquid l2Book returns limited levels by default.
    Using nSigFigs=5 gives us the most granular price levels.
    We also try nSigFigs=2 for aggregated deep levels.
    The two are merged to give both precision near the spread
    and depth far from it.
    """
    coin = request.args.get("coin", "BTC").upper()

    # Request 1: High precision near the spread (nSigFigs=5)
    data_precise = post_hyperliquid_info({
        "type": "l2Book",
        "coin": coin,
        "nSigFigs": 5,
    })

    # Request 2: Aggregated deep levels (nSigFigs=2) for wider view
    data_deep = post_hyperliquid_info({
        "type": "l2Book",
        "coin": coin,
        "nSigFigs": 2,
    })

    if data_precise is None and data_deep is None:
        return jsonify({"bids": [], "asks": [], "coin": coin, "timestamp": time.time()})

    # Merge levels: use precise data as base, add deep levels not already present
    def parse_levels(raw_levels):
        result = []
        for level in (raw_levels or []):
            px = float(level.get("px", 0))
            sz = float(level.get("sz", 0))
            n = int(level.get("n", 0))
            if sz > 0:
                result.append({"price": px, "size": sz, "orders": n})
        return result

    # Parse precise levels
    precise_levels = data_precise.get("levels", [[], []]) if data_precise else [[], []]
    bids_precise = parse_levels(precise_levels[0] if len(precise_levels) > 0 else [])
    asks_precise = parse_levels(precise_levels[1] if len(precise_levels) > 1 else [])

    # Parse deep levels
    deep_levels = data_deep.get("levels", [[], []]) if data_deep else [[], []]
    bids_deep = parse_levels(deep_levels[0] if len(deep_levels) > 0 else [])
    asks_deep = parse_levels(deep_levels[1] if len(deep_levels) > 1 else [])

    # Merge: precise levels take priority, add deep levels for prices not in precise
    def merge_levels(precise, deep, sort_desc=True):
        prices_seen = {level["price"] for level in precise}
        merged = list(precise)
        for level in deep:
            if level["price"] not in prices_seen:
                merged.append(level)
                prices_seen.add(level["price"])
        merged.sort(key=lambda x: x["price"], reverse=sort_desc)
        return merged

    bids = merge_levels(bids_precise, bids_deep, sort_desc=True)
    asks = merge_levels(asks_precise, asks_deep, sort_desc=False)

    # Calculate spread
    spread = 0
    spread_pct = 0
    if bids and asks:
        best_bid = bids[0]["price"]
        best_ask = asks[0]["price"]
        spread = best_ask - best_bid
        mid = (best_ask + best_bid) / 2
        spread_pct = (spread / mid * 100) if mid > 0 else 0

    return jsonify({
        "bids": bids,
        "asks": asks,
        "coin": coin,
        "spread": round(spread, 6),
        "spread_pct": round(spread_pct, 4),
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "timestamp": time.time()
    })