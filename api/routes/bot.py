"""
Bot status, portfolio, positions, and configuration endpoints.
"""

import logging
import os
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.bot_process_manager import bot_process_manager
from api.config import (
    LIVE_STATUS_PATH,
    MANAGED_POSITIONS_PATH,
    STATE_PATH,
    METRICS_PATH,
    RUNTIME_CONFIG_PATH,
    COIN_PATTERN,
    KNOWN_TRADING_PAIRS,
)
from api.helpers import post_hyperliquid_info, read_json_file
from runtime_config_store import RuntimeConfigStore
from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states
from utils.rate_limiter import get_all_rate_limiter_stats, get_rate_limiter

logger = logging.getLogger(__name__)

bot_bp = Blueprint("bot", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)
_runtime_store = RuntimeConfigStore(
    RUNTIME_CONFIG_PATH,
    [p.strip().upper() for p in os.getenv("TRADING_PAIRS", "BTC,ETH,SOL").split(",") if p.strip()]
)
_bot_rl = get_rate_limiter("api_bot_endpoints", max_tokens=100, tokens_per_second=3.0)

_universe_cache = []
_universe_cache_at = 0.0
_UNIVERSE_CACHE_TTL_SEC = 300.0


def _rate_limited():
    if not _bot_rl.try_acquire(1):
        return jsonify({"error": "rate_limited"}), 429
    return None


def _get_hyperliquid_available_pairs():
    global _universe_cache, _universe_cache_at

    now = time.time()
    if _universe_cache and (now - _universe_cache_at) < _UNIVERSE_CACHE_TTL_SEC:
        return list(_universe_cache)

    data = post_hyperliquid_info({"type": "meta"}, timeout=15)
    if isinstance(data, dict):
        universe = data.get("universe", [])
        parsed = []
        for asset in universe:
            coin = str(asset.get("name", "")).strip().upper()
            if coin and COIN_PATTERN.match(coin):
                parsed.append(coin)
        parsed = sorted(set(parsed))
        if parsed:
            _universe_cache = parsed
            _universe_cache_at = now
            return parsed

    if _universe_cache:
        return list(_universe_cache)

    return sorted(KNOWN_TRADING_PAIRS)


@bot_bp.route("/api/status", methods=["GET"])
@require_api_key
def bot_status():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
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
            "controller": bot_process_manager.status(),
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot status endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/portfolio", methods=["GET"])
@require_api_key
def portfolio():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
        live_status = read_json_file(LIVE_STATUS_PATH)
        return jsonify({
            "portfolio": live_status.get("portfolio", {}),
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot portfolio endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/positions", methods=["GET"])
@require_api_key
def positions():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
        live_status = read_json_file(LIVE_STATUS_PATH)
        portfolio_data = live_status.get("portfolio", {})
        return jsonify({
            "positions": portfolio_data.get("positions", {}),
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot positions endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/managed-positions", methods=["GET"])
@require_api_key
def managed_positions():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
        data = read_json_file(MANAGED_POSITIONS_PATH)
        positions_list = []
        for coin, pos_data in data.items():
            sl = pos_data.get("stop_loss", {})
            tp = pos_data.get("take_profit", {})
            ts = pos_data.get("trailing_stop", {})
            be = pos_data.get("break_even", {})

            entry_price = float(pos_data.get("entry_price", "0"))
            is_long = pos_data.get("is_long", True)
            sl_pct = float(sl.get("percentage", "0.03"))
            tp_pct = float(tp.get("percentage", "0.05"))

            if be.get("activated", False) and sl.get("price"):
                sl_price = float(sl["price"])
            elif is_long:
                sl_price = entry_price * (1 - sl_pct)
            else:
                sl_price = entry_price * (1 + sl_pct)

            if is_long:
                tp_price = entry_price * (1 + tp_pct)
            else:
                tp_price = entry_price * (1 - tp_pct)

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
    except Exception:
        logger.error("Bot managed-positions endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/config", methods=["GET"])
@require_api_key
def config():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
        trading_pairs_raw = os.getenv(
            "TRADING_PAIRS",
            "BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI,ARB,OP,NEAR,WIF,PEPE,INJ,TIA,SEI,RENDER,FET"
        )
        trading_pairs = [p.strip().upper() for p in trading_pairs_raw.split(",") if p.strip()]

        return jsonify({
            "execution_mode": os.getenv("EXECUTION_MODE", "paper"),
            "enable_mainnet_trading": os.getenv("ENABLE_MAINNET_TRADING", "false"),
            "llm_model": os.getenv("LLM_MODEL", "anthropic/claude-opus-4.6"),
            "max_leverage": os.getenv("HARD_MAX_LEVERAGE", "10"),
            "max_drawdown_pct": os.getenv("MAX_DRAWDOWN_PCT", "0.15"),
            "default_sl_pct": os.getenv("TREND_SL_PCT", "0.04"),
            "default_tp_pct": os.getenv("TREND_TP_PCT", "0.08"),
            "enable_trailing_stop": os.getenv("ENABLE_TRAILING_STOP", "true"),
            "break_even_activation_pct": os.getenv("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02"),
            "max_order_notional_usd": os.getenv("MAX_ORDER_NOTIONAL_USD", "0"),
            "trading_pairs": trading_pairs,
            "trading_pairs_count": len(trading_pairs),
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Bot config endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@bot_bp.route("/api/runtime-config", methods=["GET"])
@require_api_key
def runtime_config():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    runtime = _runtime_store.load()
    return jsonify({
        "runtime_config": runtime,
        "available_pairs": _get_hyperliquid_available_pairs(),
        "timestamp": time.time()
    })


@bot_bp.route("/api/runtime-config", methods=["POST"])
@require_api_key
def update_runtime_config():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    payload = request.get_json(silent=True) or {}
    strategy_mode = str(payload.get("strategy_mode", "trend")).strip().lower()
    if strategy_mode not in {"trend", "scalping"}:
        return jsonify({"error": "invalid_strategy_mode"}), 400

    raw_pairs = payload.get("trading_pairs", [])
    if not isinstance(raw_pairs, list):
        return jsonify({"error": "invalid_trading_pairs"}), 400

    allowed_pairs = set(_get_hyperliquid_available_pairs())

    normalized_pairs = []
    for coin in raw_pairs:
        c = str(coin).strip().upper()
        if not c:
            continue
        if not COIN_PATTERN.match(c):
            return jsonify({"error": f"invalid_coin_{c}"}), 400
        if c not in allowed_pairs:
            return jsonify({"error": f"coin_not_available_on_hyperliquid_{c}"}), 400
        if c not in normalized_pairs:
            normalized_pairs.append(c)

    if len(normalized_pairs) == 0:
        return jsonify({"error": "at_least_one_coin_required"}), 400
    if len(normalized_pairs) > 20:
        return jsonify({"error": "too_many_coins_max_20"}), 400

    saved = _runtime_store.save({
        "strategy_mode": strategy_mode,
        "trading_pairs": normalized_pairs
    })

    return jsonify({
        "ok": True,
        "runtime_config": saved,
        "message": "runtime_config_updated"
    })


@bot_bp.route("/api/bot-control/status", methods=["GET"])
@require_api_key
def bot_control_status():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp
    return jsonify({"controller": bot_process_manager.status(), "timestamp": time.time()})


@bot_bp.route("/api/bot-control/start", methods=["POST"])
@require_api_key
def bot_control_start():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    result = bot_process_manager.start()
    if result.get("ok"):
        return jsonify({"ok": True, "controller": bot_process_manager.status(), "message": "bot_started"})
    if result.get("reason") == "already_running":
        return jsonify({"ok": False, "error": "already_running"}), 409
    return jsonify({"ok": False, "error": "start_failed"}), 500


@bot_bp.route("/api/bot-control/stop", methods=["POST"])
@require_api_key
def bot_control_stop():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    result = bot_process_manager.stop()
    if result.get("ok"):
        return jsonify({"ok": True, "controller": bot_process_manager.status(), "message": "bot_stopped"})
    if result.get("reason") == "not_running":
        return jsonify({"ok": False, "error": "not_running"}), 409
    return jsonify({"ok": False, "error": "stop_failed"}), 500