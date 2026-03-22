import logging

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import COIN_PATTERN, KNOWN_TRADING_PAIRS
from api.helpers import post_hyperliquid_info
from api.rate_limit_utils import build_rate_limiter, rate_limited_response
from api.services.market_service import (
    candle_request_payload,
    serialize_candles_response,
    serialize_orderbook_debug,
    serialize_orderbook_response,
)

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__)

_VALID_INTERVALS = {"1m", "3m", "5m", "15m", "1h", "4h", "1d"}
_market_rl = build_rate_limiter("api_market_endpoints", max_tokens=120, tokens_per_second=4.0)


def _validate_coin(coin_raw: str) -> str:
    coin = (coin_raw or "").strip().upper()
    if not COIN_PATTERN.match(coin):
        return ""
    if coin not in KNOWN_TRADING_PAIRS:
        logger.info(f"Coin {coin} non presente in TRADING_PAIRS env, tentativo comunque consentito")
    return coin


@market_bp.route("/api/candles", methods=["GET"])
@require_api_key
def candles():
    rate_limit_resp = rate_limited_response(_market_rl)
    if rate_limit_resp:
        return rate_limit_resp

    coin = _validate_coin(request.args.get("coin", ""))
    if not coin:
        return jsonify({"error": "invalid_request"}), 400

    interval = request.args.get("interval", "15m")
    if interval not in _VALID_INTERVALS:
        return jsonify({"error": "invalid_request"}), 400

    limit = request.args.get("limit", 100, type=int)
    if limit is None or limit < 1 or limit > 500:
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
def orderbook():
    rate_limit_resp = rate_limited_response(_market_rl)
    if rate_limit_resp:
        return rate_limit_resp

    coin = _validate_coin(request.args.get("coin", ""))
    if not coin:
        return jsonify({"error": "invalid_request"}), 400

    n_sig_figs = request.args.get("nSigFigs", 5, type=int)
    if n_sig_figs is None or n_sig_figs < 2 or n_sig_figs > 5:
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
def orderbook_debug():
    rate_limit_resp = rate_limited_response(_market_rl)
    if rate_limit_resp:
        return rate_limit_resp

    coin = _validate_coin(request.args.get("coin", ""))
    if not coin:
        return jsonify({"error": "invalid_request"}), 400

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