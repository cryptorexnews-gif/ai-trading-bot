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
    
    Requests multiple nSigFigs levels (2,3,4,5) and merges them
    to get both precision near the spread and depth far from it.
    
    Query params:
      - coin: asset symbol (default: BTC)
      - depth_pct: max distance from mid price as percentage (default: 50)
    """
    coin = request.args.get("coin", "BTC").upper()
    depth_pct = request.args.get("depth_pct", 50, type=float)
    depth_pct = min(max(depth_pct, 1), 50)  # Clamp 1-50%

    def parse_levels(raw_levels):
        result = []
        for level in (raw_levels or []):
            px = float(level.get("px", 0))
            sz = float(level.get("sz", 0))
            n = int(level.get("n", 0))
            if sz > 0:
                result.append({"price": px, "size": sz, "orders": n})
        return result

    # Request multiple aggregation levels for maximum depth
    all_bids = {}
    all_asks = {}

    for sig_figs in [2, 3, 4, 5]:
        data = post_hyperliquid_info({
            "type": "l2Book",
            "coin": coin,
            "nSigFigs": sig_figs,
        })
        if data is None:
            continue

        levels = data.get("levels", [[], []])
        raw_bids = parse_levels(levels[0] if len(levels) > 0 else [])
        raw_asks = parse_levels(levels[1] if len(levels) > 1 else [])

        # Higher nSigFigs = more precise = takes priority for same price
        for b in raw_bids:
            px = b["price"]
            if px not in all_bids or sig_figs >= 4:
                all_bids[px] = b

        for a in raw_asks:
            px = a["price"]
            if px not in all_asks or sig_figs >= 4:
                all_asks[px] = a

    # Sort: bids descending, asks ascending
    bids_sorted = sorted(all_bids.values(), key=lambda x: x["price"], reverse=True)
    asks_sorted = sorted(all_asks.values(), key=lambda x: x["price"])

    # Calculate mid price for depth filtering
    mid_price = 0
    if bids_sorted and asks_sorted:
        mid_price = (bids_sorted[0]["price"] + asks_sorted[0]["price"]) / 2
    elif bids_sorted:
        mid_price = bids_sorted[0]["price"]
    elif asks_sorted:
        mid_price = asks_sorted[0]["price"]

    # Filter by depth percentage from mid price
    if mid_price > 0:
        lower_bound = mid_price * (1 - depth_pct / 100)
        upper_bound = mid_price * (1 + depth_pct / 100)
        bids_sorted = [b for b in bids_sorted if b["price"] >= lower_bound]
        asks_sorted = [a for a in asks_sorted if a["price"] <= upper_bound]

    # Calculate spread
    spread = 0
    spread_pct = 0
    if bids_sorted and asks_sorted:
        best_bid = bids_sorted[0]["price"]
        best_ask = asks_sorted[0]["price"]
        spread = best_ask - best_bid
        mid = (best_ask + best_bid) / 2
        spread_pct = (spread / mid * 100) if mid > 0 else 0

    return jsonify({
        "bids": bids_sorted,
        "asks": asks_sorted,
        "coin": coin,
        "spread": round(spread, 6),
        "spread_pct": round(spread_pct, 4),
        "bid_levels": len(bids_sorted),
        "ask_levels": len(asks_sorted),
        "mid_price": round(mid_price, 2),
        "depth_pct": depth_pct,
        "timestamp": time.time()
    })