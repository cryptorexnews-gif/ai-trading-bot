"""
Hyperliquid proxy endpoint — forwards market data requests from frontend to Hyperliquid API.
Prevents direct client access to Hyperliquid API.
"""

import logging
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.helpers import post_hyperliquid_info

hyperliquid_bp = Blueprint("hyperliquid", __name__)

logger = logging.getLogger(__name__)


@hyperliquid_bp.route("/api/hyperliquid/info", methods=["POST"])
@require_api_key
def hyperliquid_info():
    """
    Proxy for Hyperliquid /info endpoint.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "invalid_request", "message": "No JSON data provided"}), 400

    # Validate request type
    allowed_types = {
        "meta", "allMids", "metaAndAssetCtxs", "clearinghouseState",
        "candleSnapshot", "l2Book", "userFills", "userFunding"
    }
    
    request_type = data.get("type", "")
    if request_type not in allowed_types:
        return jsonify({
            "error": "invalid_request_type",
            "message": f"Invalid type '{request_type}'. Allowed: {', '.join(sorted(allowed_types))}"
        }), 400

    # Add rate limiting for specific endpoints
    if request_type in ["candleSnapshot", "l2Book"]:
        # These are more expensive calls
        time.sleep(0.1)  # Small delay to prevent abuse

    # Forward to Hyperliquid
    result = post_hyperliquid_info(data)
    
    if result is None:
        return jsonify({
            "error": "hyperliquid_error",
            "message": "Hyperliquid API request failed"
        }), 502

    return jsonify(result)


@hyperliquid_bp.route("/api/hyperliquid/mids", methods=["GET"])
@require_api_key
def hyperliquid_mids():
    """
    Get all mid prices from Hyperliquid.
    """
    result = post_hyperliquid_info({"type": "allMids"})
    
    if result is None:
        return jsonify({
            "error": "hyperliquid_error",
            "message": "Failed to fetch mid prices"
        }), 502

    # Filter to only include top coins for security
    top_coins = {
        "BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "AVAX",
        "LINK", "SUI", "ARB", "OP", "NEAR", "WIF", "PEPE", "INJ",
        "TIA", "SEI", "RENDER", "FET"
    }
    
    filtered_result = {coin: result[coin] for coin in top_coins if coin in result}
    
    return jsonify(filtered_result)


@hyperliquid_bp.route("/api/hyperliquid/candles", methods=["GET"])
@require_api_key
def hyperliquid_candles_proxy():
    """
    Get candle data from Hyperliquid with validation.
    """
    coin = request.args.get("coin", "BTC").upper()
    interval = request.args.get("interval", "15m")
    limit = int(request.args.get("limit", 100))
    
    # Validate parameters
    if limit > 500:
        limit = 500
    
    allowed_intervals = {"1m", "3m", "5m", "15m", "1h", "4h", "1d"}
    if interval not in allowed_intervals:
        interval = "15m"
    
    # Calculate time range
    now_ms = int(time.time() * 1000)
    interval_ms_map = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000,
        "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000
    }
    interval_ms = interval_ms_map.get(interval, 900_000)
    start_ms = now_ms - (interval_ms * limit)
    
    result = post_hyperliquid_info({
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": start_ms,
            "endTime": now_ms
        }
    })
    
    if result is None or not isinstance(result, list):
        return jsonify({"candles": [], "coin": coin, "interval": interval}), 200
    
    # Format candles
    candles = []
    for candle in result:
        candles.append({
            "time": candle.get("t", 0),
            "open": float(candle.get("o", 0)),
            "high": float(candle.get("h", 0)),
            "low": float(candle.get("l", 0)),
            "close": float(candle.get("c", 0)),
            "volume": float(candle.get("v", 0)),
        })
    
    return jsonify({
        "candles": candles,
        "coin": coin,
        "interval": interval,
        "count": len(candles)
    })