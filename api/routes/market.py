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
    """Get L2 order book from Hyperliquid."""
    coin = request.args.get("coin", "BTC").upper()
    nlevels = request.args.get("levels", 30, type=int)
    nlevels = min(nlevels, 50)

    data = post_hyperliquid_info({
        "type": "l2Book",
        "coin": coin
    })

    if data is None:
        return jsonify({"bids": [], "asks": [], "coin": coin, "timestamp": time.time()})

    levels = data.get("levels", [[], []])
    bids_raw = levels[0] if len(levels) > 0 else []
    asks_raw = levels[1] if len(levels) > 1 else []

    bids = []
    for b in bids_raw[:nlevels]:
        bids.append({
            "price": float(b.get("px", 0)),
            "size": float(b.get("sz", 0)),
            "orders": int(b.get("n", 0)),
        })

    asks = []
    for a in asks_raw[:nlevels]:
        asks.append({
            "price": float(a.get("px", 0)),
            "size": float(a.get("sz", 0)),
            "orders": int(a.get("n", 0)),
        })

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
        "timestamp": time.time()
    })