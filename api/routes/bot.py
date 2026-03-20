"""
Bot status, portfolio, positions, and configuration endpoints.
"""

import os
import time
from decimal import Decimal

from flask import Blueprint, jsonify

from api.auth import require_api_key
from api.config import LIVE_STATUS_PATH, MANAGED_POSITIONS_PATH, STATE_PATH, METRICS_PATH
from api.helpers import read_json_file
from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states
from utils.rate_limiter import get_all_rate_limiter_stats

bot_bp = Blueprint("bot", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)


@bot_bp.route("/api/status", methods=["GET"])
@require_api_key
def bot_status():
    live_status = read_json_file(LIVE_STATUS_PATH)
    state = _state_store.load_state()
    metrics = _state_store.load_metrics()

    return jsonify({
        "bot": live_status,
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


@bot_bp.route("/api/portfolio", methods=["GET"])
@require_api_key
def portfolio():
    live_status = read_json_file(LIVE_STATUS_PATH)
    return jsonify({
        "portfolio": live_status.get("portfolio", {}),
        "timestamp": time.time()
    })


@bot_bp.route("/api/positions", methods=["GET"])
@require_api_key
def positions():
    live_status = read_json_file(LIVE_STATUS_PATH)
    portfolio_data = live_status.get("portfolio", {})
    return jsonify({
        "positions": portfolio_data.get("positions", {}),
        "timestamp": time.time()
    })


@bot_bp.route("/api/managed-positions", methods=["GET"])
@require_api_key
def managed_positions():
    data = read_json_file(MANAGED_POSITIONS_PATH)
    positions_list = []
    for coin, pos_data in data.items():
        sl = pos_data.get("stop_loss", {})
        tp = pos_data.get("take_profit", {})
        ts = pos_data.get("trailing_stop", {})
        be = pos_data.get("break_even", {})

        entry_price = Decimal(str(pos_data.get("entry_price", "0")))
        is_long = pos_data.get("is_long", True)
        sl_pct = Decimal(str(sl.get("percentage", "0.03")))
        tp_pct = Decimal(str(tp.get("percentage", "0.05")))

        if be.get("activated", False) and sl.get("price"):
            sl_price = Decimal(str(sl["price"]))
        elif is_long:
            sl_price = entry_price * (Decimal("1") - sl_pct)
        else:
            sl_price = entry_price * (Decimal("1") + sl_pct)

        if is_long:
            tp_price = entry_price * (Decimal("1") + tp_pct)
        else:
            tp_price = entry_price * (Decimal("1") - tp_pct)

        positions_list.append({
            "coin": coin,
            "side": "LONG" if is_long else "SHORT",
            "size": pos_data.get("size", "0"),
            "entry_price": str(entry_price),
            "stop_loss_price": str(sl_price),
            "stop_loss_pct": str(sl_pct),
            "take_profit_price": str(tp_price),
            "take_profit_pct": str(tp_pct),
            "trailing_enabled": ts.get("enabled", False),
            "trailing_callback": ts.get("callback_rate", "0.02"),
            "highest_tracked": ts.get("highest_price"),
            "lowest_tracked": ts.get("lowest_price"),
            "break_even_activated": be.get("activated", False),
            "break_even_activation_pct": be.get("activation_pct", "0.015"),
            "opened_at": pos_data.get("opened_at", 0),
        })

    return jsonify({
        "managed_positions": positions_list,
        "timestamp": time.time()
    })


@bot_bp.route("/api/config", methods=["GET"])
@require_api_key
def config():
    """Return minimal bot configuration. Never returns secret env vars."""
    return jsonify({
        "execution_mode": os.getenv("EXECUTION_MODE", "paper"),
        "enable_mainnet_trading": os.getenv("ENABLE_MAINNET_TRADING", "false"),
        "llm_model": os.getenv("LLM_MODEL", "anthropic/claude-opus-4.6"),
        "max_leverage": os.getenv("HARD_MAX_LEVERAGE", "10"),
        "max_drawdown_pct": os.getenv("MAX_DRAWDOWN_PCT", "0.15"),
        "timestamp": time.time()
    })