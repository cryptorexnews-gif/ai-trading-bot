import logging

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import COIN_PATTERN, KNOWN_TRADING_PAIRS
from api.rate_limit_utils import build_rate_limiter, rate_limited_response
from api.services.market_service import (
    fetch_candles_response,
    fetch_orderbook_debug_response,
    fetch_orderbook_response,
    validate_coin,
    validate_interval,
    validate_limit,
    validate_n_sig_figs,
)

logger = logging.getLogger(__name__)

market_bp = Blueprint("market", __name__)

_VALID_INTERVALS = {"1m", "3m", "5m", "15m", "1h", "4h", "1d"}
_market_rl = build_rate_limiter("api_market_endpoints", max_tokens=120, tokens_per_second=4.0)


@market_bp.route("/api/candles", methods=["GET"])
@require_api_key
def candles():
    rate_limit_resp = rate_limited_response(_market_rl)
    if rate_limit_resp:
        return rate_limit_resp

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
        return jsonify(fetch_candles_response(coin=coin, interval=interval, limit=limit))
    except Exception:
        logger.error("Market candles endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@market_bp.route("/api/orderbook", methods=["GET"])
@require_api_key
def orderbook():
    rate_limit_resp = rate_limited_response(_market_rl)
    if rate_limit_resp:
        return rate_limit_resp

    coin = validate_coin(request.args.get("coin", ""), COIN_PATTERN, KNOWN_TRADING_PAIRS)
    if not coin:
        return jsonify({"error": "invalid_request"}), 400
    if coin not in KNOWN_TRADING_PAIRS:
        logger.info(f"Coin {coin} non presente in TRADING_PAIRS env, tentativo comunque consentito")

    n_sig_figs = request.args.get("nSigFigs", 5, type=int)
    if not validate_n_sig_figs(n_sig_figs):
        return jsonify({"error": "invalid_request"}), 400

    try:
        return jsonify(fetch_orderbook_response(coin=coin, n_sig_figs=n_sig_figs))
    except Exception:
        logger.error("Market orderbook endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@market_bp.route("/api/orderbook/debug", methods=["GET"])
@require_api_key
def orderbook_debug():
    rate_limit_resp = rate_limited_response(_market_rl)
    if rate_limit_resp:
        return rate_limit_resp

    coin = validate_coin(request.args.get("coin", ""), COIN_PATTERN, KNOWN_TRADING_PAIRS)
    if not coin:
        return jsonify({"error": "invalid_request"}), 400
    if coin not in KNOWN_TRADING_PAIRS:
        logger.info(f"Coin {coin} non presente in TRADING_PAIRS env, tentativo comunque consentito")

    try:
        debug_payload = fetch_orderbook_debug_response(coin=coin)
        if "error" in debug_payload:
            return jsonify(debug_payload), 502
        return jsonify(debug_payload)
    except Exception:
        logger.error("Market orderbook debug endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500