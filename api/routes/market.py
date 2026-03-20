"""
Market data endpoints — proxies Hyperliquid API for candles and order book.
All coin parameters are validated against known patterns.
"""

import logging
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import COIN_PATTERN, KNOWN_TRADING_PAIRS
from api.helpers import post_hyperliquid_info

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__)

# Allowed candle intervals
_VALID_INTERVALS = {"1m", "3m", "5m", "15m", "1h", "4h", "1d"}


def _validate_coin(coin_raw: str) -> str:
    """Validate and sanitize coin parameter. Returns uppercased coin or empty string if invalid."""
    coin = coin_raw.strip().upper()
    if not COIN_PATTERN.match(coin):
        return ""
    return coin


@market_bp.route("/api/candles", methods=["GET"])
@require_api_key
def candles():
    """Get candlestick data from Hyperliquid for price chart."""
    coin = _validate_coin(request.args.get("coin", "BTC"))
    if not coin:
        return jsonify({"error": "invalid coin parameter"}), 400

    interval = request.args.get("interval", "15m")
    if interval not in _VALID_INTERVALS:
        return jsonify({"error": f"invalid interval, must be one of: {', '.join(sorted(_VALID_INTERVALS))}"}), 400

    limit = request.args.get("limit", 100, type=int)
    limit = max(1, min(limit, 500))

    interval_ms_map = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
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
    Get L2 order book from Hyperliquid.
    Uses nSigFigs for price grouping (2-5, matching Hyperliquid UI).
    """
    coin = _validate_coin(request.args.get("coin", "BTC"))
    if not coin:
        return jsonify({"error": "invalid coin parameter"}), 400

    n_sig_figs = request.args.get("nSigFigs", 5, type=int)
    n_sig_figs = max(2, min(5, n_sig_figs))

    logger.info(f"Fetching order book for {coin} with nSigFigs={n_sig_figs}")

    data = post_hyperliquid_info({
        "type": "l2Book",
        "coin": coin,
        "nSigFigs": n_sig_figs,
    })

    if data is None:
        logger.warning(f"Order book request returned None for {coin}")
        return jsonify({
            "bids": [], "asks": [], "coin": coin,
            "spread": 0, "spread_pct": 0,
            "timestamp": time.time()
        })

    # Hyperliquid returns {"levels": [[bids], [asks]]}
    levels = data.get("levels", [[], []])

    if not levels or len(levels) < 2:
        logger.warning(f"Order book has unexpected structure for {coin}: keys={list(data.keys())}")
        return jsonify({
            "bids": [], "asks": [], "coin": coin,
            "spread": 0, "spread_pct": 0,
            "timestamp": time.time()
        })

    raw_bids = levels[0] if len(levels) > 0 else []
    raw_asks = levels[1] if len(levels) > 1 else []

    def parse_levels(raw):
        result = []
        for level in (raw or []):
            px = float(level.get("px", 0))
            sz = float(level.get("sz", 0))
            n = int(level.get("n", 0))
            if sz > 0:
                result.append({"px": px, "sz": sz, "n": n})
        return result

    bids = parse_levels(raw_bids)
    asks = parse_levels(raw_asks)

    logger.info(f"Order book {coin}: {len(bids)} bids, {len(asks)} asks")

    # Calculate spread
    spread = 0.0
    spread_pct = 0.0
    if bids and asks:
        best_bid = bids[0]["px"]
        best_ask = asks[0]["px"]
        spread = best_ask - best_bid
        mid = (best_ask + best_bid) / 2
        spread_pct = (spread / mid * 100) if mid > 0 else 0

    return jsonify({
        "bids": bids,
        "asks": asks,
        "coin": coin,
        "spread": round(spread, 8),
        "spread_pct": round(spread_pct, 6),
        "timestamp": time.time()
    })


@market_bp.route("/api/orderbook/debug", methods=["GET"])
@require_api_key
def orderbook_debug():
    """Debug endpoint — returns raw Hyperliquid L2 response. Requires API key."""
    coin = _validate_coin(request.args.get("coin", "BTC"))
    if not coin:
        return jsonify({"error": "invalid coin parameter"}), 400

    data = post_hyperliquid_info({
        "type": "l2Book",
        "coin": coin,
        "nSigFigs": 5,
    })

    if data is None:
        return jsonify({"error": "Hyperliquid returned None", "coin": coin})

    return jsonify({
        "raw_keys": list(data.keys()) if isinstance(data, dict) else str(type(data)),
        "raw_data_preview": str(data)[:2000],
        "coin": coin,
        "timestamp": time.time()
    })