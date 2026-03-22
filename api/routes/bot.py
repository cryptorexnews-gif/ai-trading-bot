"""
Bot status, portfolio, positions, and configuration endpoints.
"""

import logging
import os
import time
from decimal import Decimal

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
from utils.hyperliquid_state import get_account_balances, get_open_positions
from utils.rate_limiter import get_all_rate_limiter_stats, get_rate_limiter

logger = logging.getLogger(__name__)

bot_bp = Blueprint("bot", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)
_runtime_store = RuntimeConfigStore(
    RUNTIME_CONFIG_PATH,
    [p.strip().upper() for p in os.getenv("TRADING_PAIRS", "BTC,ETH,SOL").split(",") if p.strip()]
)
_bot_rl = get_rate_limiter("api_bot_endpoints", max_tokens=100, tokens_per_second=3.0)
_config_rl = get_rate_limiter("api_bot_config_endpoint", max_tokens=300, tokens_per_second=20.0)

_universe_cache = []
_universe_cache_at = 0.0
_UNIVERSE_CACHE_TTL_SEC = 300.0


def _rate_limited():
    if not _bot_rl.try_acquire(1):
        return jsonify({"error": "rate_limited"}), 429
    return None


def _config_rate_limited():
    if not _config_rl.try_acquire(1):
        return jsonify({"error": "rate_limited"}), 429
    return None


def _mask_wallet(wallet: str) -> str:
    if not wallet or len(wallet) < 12:
        return "invalid_wallet"
    return f"{wallet[:6]}...{wallet[-4:]}"


def _get_hyperliquid_account_snapshot():
    wallet = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()
    if not wallet:
        return {
            "wallet": "",
            "wallet_masked": "not_configured",
            "portfolio": {
                "total_balance": Decimal("0"),
                "available_balance": Decimal("0"),
                "margin_usage": Decimal("0"),
                "positions": {},
                "position_count": 0,
                "total_unrealized_pnl": Decimal("0"),
                "total_exposure": Decimal("0"),
                "open_orders_count": 0,
            },
            "margin_summary": {},
            "withdrawable": "0",
            "updated_at": time.time(),
        }

    try:
        user_state = post_hyperliquid_info({"type": "clearinghouseState", "user": wallet}, timeout=20)
        if not isinstance(user_state, dict):
            raise ValueError("Invalid user_state response")

        balances = get_account_balances(user_state)
        positions = get_open_positions(user_state)

        total_unrealized_pnl = Decimal("0")
        total_exposure = Decimal("0")
        for pos in positions.values():
            size = Decimal(str(pos.get("size", 0)))
            entry = Decimal(str(pos.get("entry_price", 0)))
            pnl = Decimal(str(pos.get("unrealized_pnl", 0)))
            total_unrealized_pnl += pnl
            total_exposure += abs(size * entry)

        open_orders = post_hyperliquid_info({"type": "openOrders", "user": wallet}, timeout=15)
        open_orders_count = len(open_orders) if isinstance(open_orders, list) else 0

        return {
            "wallet": wallet,
            "wallet_masked": _mask_wallet(wallet),
            "portfolio": {
                "total_balance": balances["total_balance"],
                "available_balance": balances["available_balance"],
                "margin_usage": balances["margin_usage"],
                "positions": positions,
                "position_count": len(positions),
                "total_unrealized_pnl": total_unrealized_pnl,
                "total_exposure": total_exposure,
                "open_orders_count": open_orders_count,
            },
            "margin_summary": user_state.get("marginSummary", {}),
            "withdrawable": user_state.get("withdrawable", "0"),
            "updated_at": time.time(),
        }
    except Exception as e:
        logger.error(f"Failed to get Hyperliquid account snapshot: {e}")
        return {
            "wallet": wallet,
            "wallet_masked": _mask_wallet(wallet),
            "portfolio": {
                "total_balance": Decimal("0"),
                "available_balance": Decimal("0"),
                "margin_usage": Decimal("0"),
                "positions": {},
                "position_count": 0,
                "total_unrealized_pnl": Decimal("0"),
                "total_exposure": Decimal("0"),
                "open_orders_count": 0,
            },
            "margin_summary": {},
            "withdrawable": "0",
            "updated_at": time.time(),
        }


def _fetch_hyperliquid_universe():
    data = post_hyperliquid_info({"type": "meta"}, timeout=20)
    if not isinstance(data, dict):
        return []

    universe = data.get("universe", [])
    parsed = []
    for asset in universe:
        coin = str(asset.get("name", "")).strip().upper()
        if coin and COIN_PATTERN.match(coin):
            parsed.append(coin)

    return sorted(set(parsed))


def _get_hyperliquid_available_pairs():
    global _universe_cache, _universe_cache_at

    now = time.time()
    if _universe_cache and (now - _universe_cache_at) < _UNIVERSE_CACHE_TTL_SEC:
        return list(_universe_cache)

    fresh = _fetch_hyperliquid_universe()
    if fresh:
        _universe_cache = fresh
        _universe_cache_at = now
        return fresh

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
        account_snapshot = _get_hyperliquid_account_snapshot()

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
        account_snapshot = _get_hyperliquid_account_snapshot()
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
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
        account_snapshot = _get_hyperliquid_account_snapshot()
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
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
        account_snapshot = _get_hyperliquid_account_snapshot()
        exchange_positions = account_snapshot.get("portfolio", {}).get("positions", {}) or {}
        managed_data = read_json_file(MANAGED_POSITIONS_PATH) or {}

        default_sl_pct = Decimal(str(os.getenv("TREND_SL_PCT", "0.04")))
        default_tp_pct = Decimal(str(os.getenv("TREND_TP_PCT", "0.08")))
        default_be_activation_pct = Decimal(str(os.getenv("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02")))
        default_trailing_callback = Decimal(str(os.getenv("TREND_TRAILING_CALLBACK", "0.02")))

        positions_list = []

        for coin, ex_pos in exchange_positions.items():
            size = Decimal(str(ex_pos.get("size", "0")))
            if size == 0:
                continue

            is_long = size > 0
            abs_size = abs(size)
            entry_price = Decimal(str(ex_pos.get("entry_price", "0")))

            managed_raw = managed_data.get(coin, {})
            sl = managed_raw.get("stop_loss", {})
            tp = managed_raw.get("take_profit", {})
            ts = managed_raw.get("trailing_stop", {})
            be = managed_raw.get("break_even", {})

            sl_pct = Decimal(str(sl.get("percentage", default_sl_pct)))
            tp_pct = Decimal(str(tp.get("percentage", default_tp_pct)))

            sl_price_abs = sl.get("price")
            tp_price_abs = tp.get("price")

            break_even_activated = bool(be.get("activated", False))
            break_even_activation_pct = Decimal(str(be.get("activation_pct", default_be_activation_pct)))

            if break_even_activated and sl_price_abs is not None:
                sl_price = Decimal(str(sl_price_abs))
            elif sl_price_abs is not None:
                sl_price = Decimal(str(sl_price_abs))
            elif entry_price > 0:
                if is_long:
                    sl_price = entry_price * (Decimal("1") - sl_pct)
                else:
                    sl_price = entry_price * (Decimal("1") + sl_pct)
            else:
                sl_price = Decimal("0")

            if tp_price_abs is not None:
                tp_price = Decimal(str(tp_price_abs))
            elif entry_price > 0:
                if is_long:
                    tp_price = entry_price * (Decimal("1") + tp_pct)
                else:
                    tp_price = entry_price * (Decimal("1") - tp_pct)
            else:
                tp_price = Decimal("0")

            positions_list.append({
                "coin": coin,
                "side": "LONG" if is_long else "SHORT",
                "size": str(abs_size),
                "entry_price": str(entry_price),
                "stop_loss_price": str(sl_price),
                "stop_loss_pct": str(sl_pct),
                "take_profit_price": str(tp_price),
                "take_profit_pct": str(tp_pct),
                "trailing_enabled": bool(ts.get("enabled", False)),
                "trailing_callback": str(ts.get("callback_rate", default_trailing_callback)),
                "highest_tracked": ts.get("highest_price"),
                "lowest_tracked": ts.get("lowest_price"),
                "break_even_activated": break_even_activated,
                "break_even_activation_pct": str(break_even_activation_pct),
                "opened_at": managed_raw.get("opened_at", 0),
                "source": "managed" if coin in managed_data else "exchange_only",
            })

        positions_list.sort(key=lambda p: p["coin"])

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
    rate_limit_resp = _config_rate_limited()
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
            "llm_model": os.getenv("LLM_MODEL", "anthropic/claude-opus-4.6"),
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

    live_allowed = set(_fetch_hyperliquid_universe())

    normalized_pairs = []
    for coin in raw_pairs:
        c = str(coin).strip().upper()
        if not c:
            continue
        if not COIN_PATTERN.match(c):
            return jsonify({"error": f"invalid_coin_{c}"}), 400

        if live_allowed and c not in live_allowed:
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