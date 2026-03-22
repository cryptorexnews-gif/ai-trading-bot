import logging

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import COIN_PATTERN, KNOWN_TRADING_PAIRS
from api.helpers import post_hyperliquid_info
from api.rate_limit import rate_limited
from api.services.market_service import (
    candle_request_payload,
    serialize_candles_response,
    serialize_orderbook_debug,
    serialize_orderbook_response,
    validate_coin,
    validate_interval,
    validate_limit,
    validate_n_sig_figs,
)

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__)

_VALID_INTERVALS = {"1m", "3m", "5m", "15m", "1h", "4h", "1d"}


@market_bp.route("/api/candles", methods=["GET"])
@require_api_key
@rate_limited("api_market_endpoints", max_tokens=120, tokens_per_second=4.0)
def candles():
    coin = validate_coin(request.args.get("coin", ""), COIN_PATTERN, KNOWN_TRADING_PAIRS)
    if not coin:
        return jsonify({"error": "invalid_request"}), 400
    if coin not in KNOWN_TRADING_PAIRS:
        logger.info(f"Coin {coin} non presente in TRADING_PAIRS env, tentativo comunque consentito")

    interval = request.args.get("interval", "15m")
    if not validate_interval(interval, _VALID_INTERVALS):
        return jsonify({"error": "invalid_request"}), 400

    limit = request.args.get("limit", 100, type=int)
    if not validate_limit(limit):
        return jsonify({"error": "invalid_request"}), 400

    try:
        payload = candle_request_payload(coin=coin, interval=interval, limit=limit)
        data = post_hyperliquid_info(payload)
        return jsonify(serialize_candles_response(data=data, coin=coin, interval=interval))
    except Exception:
        logger.error("Market candles endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@market_bp.route("/api/orderbook", methods=["GET"])
@require_api_key
@rate_limited("api_market_endpoints", max_tokens=120, tokens_per_second=4.0)
def orderbook():
    coin = validate_coin(request.args.get("coin", ""), COIN_PATTERN, KNOWN_TRADING_PAIRS)
    if not coin:
        return jsonify({"error": "invalid_request"}), 400
    if coin not in KNOWN_TRADING_PAIRS:
        logger.info(f"Coin {coin} non presente in TRADING_PAIRS env, tentativo comunque consentito")

    n_sig_figs = request.args.get("nSigFigs", 5, type=int)
    if not validate_n_sig_figs(n_sig_figs):
        return jsonify({"error": "invalid_request"}), 400

    try:
        data = post_hyperliquid_info({
            "type": "l2Book",
            "coin": coin,
            "nSigFigs": n_sig_figs,
        })

        if data is None:
            return jsonify({
                "bids": [], "asks": [], "coin": coin,
                "spread": 0, "spread_pct": 0,
                "timestamp": 0
            })

        return jsonify(serialize_orderbook_response(data=data, coin=coin))
    except Exception:
        logger.error("Market orderbook endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@market_bp.route("/api/orderbook/debug", methods=["GET"])
@require_api_key
@rate_limited("api_market_endpoints", max_tokens=120, tokens_per_second=4.0)
def orderbook_debug():
    coin = validate_coin(request.args.get("coin", ""), COIN_PATTERN, KNOWN_TRADING_PAIRS)
    if not coin:
        return jsonify({"error": "invalid_request"}), 400
    if coin not in KNOWN_TRADING_PAIRS:
        logger.info(f"Coin {coin} non presente in TRADING_PAIRS env, tentativo comunque consentito")

    try:
        data = post_hyperliquid_info({
            "type": "l2Book",
            "coin": coin,
            "nSigFigs": 5,
        })

        if data is None:
            return jsonify({"error": "upstream_unavailable", "coin": coin}), 502

        return jsonify(serialize_orderbook_debug(data=data, coin=coin))
    except Exception:
        logger.error("Market orderbook debug endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500