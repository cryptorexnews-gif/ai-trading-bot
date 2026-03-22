"""
Account and bot data endpoints:
- /api/status
- /api/portfolio
- /api/positions
- /api/managed-positions
- /api/config
"""

import logging
import os

from flask import Blueprint, jsonify

from api.auth import require_api_key
from api.config import (
    LIVE_STATUS_PATH,
    MANAGED_POSITIONS_PATH,
    STATE_PATH,
    METRICS_PATH,
    RUNTIME_CONFIG_PATH,
)
from api.rate_limit import rate_limited
from api.services.account_route_service import (
    build_account_config_response,
    build_managed_positions_response,
    build_portfolio_response,
    build_positions_response,
)
from api.services.account_status_service import build_account_status_response
from api.services.wallet_service import get_wallet_address
from runtime_config_store import RuntimeConfigStore
from state_store import StateStore

logger = logging.getLogger(__name__)

account_bp = Blueprint("account", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)
_runtime_store = RuntimeConfigStore(
    RUNTIME_CONFIG_PATH,
    [p.strip().upper() for p in os.getenv("TRADING_PAIRS", "BTC,ETH,SOL").split(",") if p.strip()],
    default_strategy_mode=os.getenv("DEFAULT_STRATEGY_MODE", "trend"),
)


@account_bp.route("/api/status", methods=["GET"])
@require_api_key
@rate_limited("api_account_endpoints", max_tokens=100, tokens_per_second=3.0)
def bot_status():
    try:
        wallet = get_wallet_address()
        return jsonify(build_account_status_response(_state_store, LIVE_STATUS_PATH, wallet))
    except Exception:
        logger.error("Account status endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@account_bp.route("/api/portfolio", methods=["GET"])
@require_api_key
@rate_limited("api_account_endpoints", max_tokens=100, tokens_per_second=3.0)
def portfolio():
    try:
        wallet = get_wallet_address()
        return jsonify(build_portfolio_response(wallet))
    except Exception:
        logger.error("Account portfolio endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@account_bp.route("/api/positions", methods=["GET"])
@require_api_key
@rate_limited("api_account_endpoints", max_tokens=100, tokens_per_second=3.0)
def positions():
    try:
        wallet = get_wallet_address()
        return jsonify(build_positions_response(wallet))
    except Exception:
        logger.error("Account positions endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@account_bp.route("/api/managed-positions", methods=["GET"])
@require_api_key
@rate_limited("api_account_endpoints", max_tokens=100, tokens_per_second=3.0)
def managed_positions():
    try:
        wallet = get_wallet_address()
        return jsonify(build_managed_positions_response(wallet, MANAGED_POSITIONS_PATH))
    except Exception:
        logger.error("Account managed-positions endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@account_bp.route("/api/config", methods=["GET"])
@require_api_key
@rate_limited("api_account_config_endpoint", max_tokens=300, tokens_per_second=20.0)
def config():
    try:
        return jsonify(build_account_config_response(_runtime_store))
    except Exception:
        logger.error("Account config endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500