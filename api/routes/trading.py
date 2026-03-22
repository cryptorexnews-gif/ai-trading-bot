import logging

from flask import Blueprint, Response, jsonify, request

from api.auth import require_api_key
from api.rate_limit_utils import build_rate_limiter, rate_limited_response
from api.services.trade_history_service import (
    build_export_csv_for_wallet,
    build_performance_response_payload,
    build_trades_response_payload,
)
from api.services.wallet_service import get_wallet_address

logger = logging.getLogger(__name__)

trading_bp = Blueprint("trading", __name__)
_trading_rl = build_rate_limiter("api_trading_endpoints", max_tokens=80, tokens_per_second=3.0)


@trading_bp.route("/api/trades", methods=["GET"])
@require_api_key
def trades():
    rate_limit_resp = rate_limited_response(_trading_rl)
    if rate_limit_resp:
        return rate_limit_resp

    limit = request.args.get("limit", 50, type=int)
    if limit is None or limit < 1 or limit > 500:
        return jsonify({"error": "invalid_request"}), 400

    wallet = get_wallet_address()
    if not wallet:
        return jsonify({"error": "wallet_not_configured"}), 500

    try:
        return jsonify(build_trades_response_payload(wallet, limit))
    except Exception:
        logger.error("Trading trades endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@trading_bp.route("/api/trades/export", methods=["GET"])
@require_api_key
def export_trades():
    rate_limit_resp = rate_limited_response(_trading_rl)
    if rate_limit_resp:
        return rate_limit_resp

    wallet = get_wallet_address()
    if not wallet:
        return jsonify({"error": "wallet_not_configured"}), 500

    try:
        csv_text = build_export_csv_for_wallet(wallet)
        return Response(
            csv_text,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=hyperliquid_user_fills.csv"}
        )
    except Exception:
        logger.error("Trading export endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@trading_bp.route("/api/performance", methods=["GET"])
@require_api_key
def performance():
    rate_limit_resp = rate_limited_response(_trading_rl)
    if rate_limit_resp:
        return rate_limit_resp

    wallet = get_wallet_address()
    if not wallet:
        return jsonify({"error": "wallet_not_configured"}), 500

    try:
        return jsonify(build_performance_response_payload(wallet))
    except Exception:
        logger.error("Trading performance endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500