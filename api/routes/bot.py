"""
Bot status, portfolio, positions, and configuration endpoints.
"""

import logging
import os
import time
from decimal import Decimal

from flask import Blueprint, jsonify

from api.auth import require_api_key
from api.config import (
    LIVE_STATUS_PATH,
    MANAGED_POSITIONS_PATH,
    STATE_PATH,
    METRICS_PATH,
    RUNTIME_CONFIG_PATH,
)
from api.helpers import read_json_file
from api.rate_limit_utils import build_rate_limiter, rate_limited_response
from api.services.account_snapshot_service import get_hyperliquid_account_snapshot
from api.services.managed_positions_service import build_managed_positions_payload
from runtime_config_store import RuntimeConfigStore
from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states
from utils.rate_limiter import get_all_rate_limiter_stats

logger = logging.getLogger(__name__)

bot_bp = Blueprint("bot", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)
_runtime_store = RuntimeConfigStore(
    RUNTIME_CONFIG_PATH,
    [p.strip().upper() for p in os.getenv("TRADING_PAIRS", "BTC,ETH,SOL").split(",") if p.strip()],
    default_strategy_mode=os.getenv("DEFAULT_STRATEGY_MODE", "trend"),
)
_bot_rl = build_rate_limiter("api_bot_endpoints", max_tokens=100, tokens_per_second=3.0)
_config_rl = build_rate_limiter("api_bot_config_endpoint", max_tokens=300, tokens_per_second=20.0)


@bot_bp.route("/api/status", methods=["GET"])
@require_api_key
def bot_status():
    rate_limit_resp = rate_limited_response(_bot_rl)
    if rate_limit_resp:
        return rate_limit_resp

    try:
        live_status = read_json_file(LIVE_STATUS_PATH)
        state = _state_store.load_state()
        metrics = _state_store.load_metrics()
        wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()
        account_snapshot = get_hyperliquid_account_snapshot(wallet)

        return jsonify({
            "bot": live_status,
            "account": account_snapshot,
            "state": {
                "peak_portfolio_value": state.get("peak_portfolio_value", "0"),
                "consecutive_failed_cycles": state.get("consecutive_failed_cycles", 0),
                "consecutive_losses": state.get("consecutive_losses", 0),
            },
            "metrics": metrics,
            "circuit_breakers": get_all_circuit_states(),
            "rate_limiters": get_all_rate_limiter_stats(),
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot status endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/portfolio", methods=["GET"])
@require_api_key
def portfolio():
    rate_limit_resp = rate_limited_response(_bot_rl)
    if rate_limit_resp:
        return rate_limit_resp

    try:
        wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()
        account_snapshot = get_hyperliquid_account_snapshot(wallet)
        return jsonify({
            "portfolio": account_snapshot.get("portfolio", {}),
            "source": "hyperliquid_account",
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot portfolio endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/positions", methods=["GET"])
@require_api_key
def positions():
    rate_limit_resp = rate_limited_response(_bot_rl)
    if rate_limit_resp:
        return rate_limit_resp

    try:
        wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()
        account_snapshot = get_hyperliquid_account_snapshot(wallet)
        return jsonify({
            "positions": account_snapshot.get("portfolio", {}).get("positions", {}),
            "source": "hyperliquid_account",
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot positions endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/managed-positions", methods=["GET"])
@require_api_key
def managed_positions():
    rate_limit_resp = rate_limited_response(_bot_rl)
    if rate_limit_resp:
        return rate_limit_resp

    try:
        wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()
        account_snapshot = get_hyperliquid_account_snapshot(wallet)
        exchange_positions = account_snapshot.get("portfolio", {}).get("positions", {}) or {}
        managed_data = read_json_file(MANAGED_POSITIONS_PATH) or {}

        default_sl_pct = Decimal(str(os.getenv("TREND_SL_PCT", "0.04")))
        default_tp_pct = Decimal(str(os.getenv("TREND_TP_PCT", "0.08")))
        default_be_activation_pct = Decimal(str(os.getenv("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02")))
        default_trailing_callback = Decimal(str(os.getenv("TREND_TRAILING_CALLBACK", "0.02")))

        positions_list = build_managed_positions_payload(
            exchange_positions=exchange_positions,
            managed_data=managed_data,
            default_sl_pct=default_sl_pct,
            default_tp_pct=default_tp_pct,
            default_be_activation_pct=default_be_activation_pct,
            default_trailing_callback=default_trailing_callback,
        )

        return jsonify({
            "managed_positions": positions_list,
            "source": "hyperliquid_account_with_managed_overlays",
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot managed-positions endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/config", methods=["GET"])
@require_api_key
def config():
    rate_limit_resp = rate_limited_response(_config_rl)
    if rate_limit_resp:
        return rate_limit_resp

    try:
        env_pairs_raw = os.getenv(
            "TRADING_PAIRS",
            "BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI,ARB,OP,NEAR,WIF,PEPE,INJ,TIA,SEI,RENDER,FET"
        )
        env_pairs = [p.strip().upper() for p in env_pairs_raw.split(",") if p.strip()]

        runtime_cfg = _runtime_store.load()
        runtime_pairs = [str(p).strip().upper() for p in runtime_cfg.get("trading_pairs", []) if str(p).strip()]
        strategy_mode = str(runtime_cfg.get("strategy_mode", "trend")).strip().lower()

        trading_pairs = runtime_pairs if runtime_pairs else env_pairs
        source = "runtime_config" if runtime_pairs else "env_default"

        return jsonify({
            "execution_mode": os.getenv("EXECUTION_MODE", "paper"),
            "enable_mainnet_trading": os.getenv("ENABLE_MAINNET_TRADING", "false"),
            "llm_model": os.getenv("LLM_MODEL", "deepseek/deepseek-v3.2"),
            "max_leverage": os.getenv("HARD_MAX_LEVERAGE", "10"),
            "max_drawdown_pct": os.getenv("MAX_DRAWDOWN_PCT", "0.15"),
            "default_sl_pct": os.getenv("TREND_SL_PCT", "0.04"),
            "default_tp_pct": os.getenv("TREND_TP_PCT", "0.08"),
            "enable_trailing_stop": os.getenv("ENABLE_TRAILING_STOP", "true"),
            "break_even_activation_pct": os.getenv("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02"),
            "max_order_notional_usd": os.getenv("MAX_ORDER_NOTIONAL_USD", "0"),
            "min_confidence_open": os.getenv("MIN_CONFIDENCE_OPEN", "0.72"),
            "min_confidence_manage": os.getenv("MIN_CONFIDENCE_MANAGE", "0.50"),
            "strategy_mode": strategy_mode,
            "trading_pairs": trading_pairs,
            "trading_pairs_count": len(trading_pairs),
            "trading_pairs_source": source,
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot config endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500