#!/usr/bin/env python3
"""
Server API per Dashboard Bot Trading Hyperliquid.
"""

import csv
import io
import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict

from flask import Flask, Response, jsonify, request
from flask_cors import CORS

from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states
from utils.metrics import MetricsCollector
from utils.rate_limiter import get_all_rate_limiter_stats

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

STATE_PATH = "state/bot_state.json"
METRICS_PATH = "state/bot_metrics.json"
LIVE_STATUS_PATH = "state/bot_live_status.json"
MANAGED_POSITIONS_PATH = "state/managed_positions.json"

state_store = StateStore(STATE_PATH, METRICS_PATH)

# Metrics collector for Prometheus export
_metrics_collector = MetricsCollector()


from flask.json.provider import DefaultJSONProvider

class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)


def _read_json_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": time.time()})


@app.route("/api/status", methods=["GET"])
def bot_status():
    live_status = _read_json_file(LIVE_STATUS_PATH)
    state = state_store.load_state()
    metrics = state_store.load_metrics()

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


@app.route("/api/portfolio", methods=["GET"])
def portfolio():
    live_status = _read_json_file(LIVE_STATUS_PATH)
    return jsonify({
        "portfolio": live_status.get("portfolio", {}),
        "timestamp": time.time()
    })


@app.route("/api/positions", methods=["GET"])
def positions():
    live_status = _read_json_file(LIVE_STATUS_PATH)
    portfolio_data = live_status.get("portfolio", {})
    return jsonify({
        "positions": portfolio_data.get("positions", {}),
        "timestamp": time.time()
    })


@app.route("/api/managed-positions", methods=["GET"])
def managed_positions():
    """Ottieni posizioni gestite con info SL/TP/trailing stop/break-even."""
    data = _read_json_file(MANAGED_POSITIONS_PATH)
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


@app.route("/api/trades", methods=["GET"])
def trades():
    limit = request.args.get("limit", 50, type=int)
    state = state_store.load_state()
    history = state.get("trade_history", [])
    recent = list(reversed(history[-limit:]))
    return jsonify({
        "trades": recent,
        "total": len(history),
        "timestamp": time.time()
    })


@app.route("/api/trades/export", methods=["GET"])
def export_trades():
    """Esporta storia trade come CSV."""
    state = state_store.load_state()
    history = state.get("trade_history", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "datetime", "coin", "action", "size", "price",
        "notional", "leverage", "confidence", "success", "mode",
        "trigger", "order_status", "reasoning"
    ])

    for trade in history:
        ts = trade.get("timestamp", 0)
        dt = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)) if ts else ""
        writer.writerow([
            ts, dt, trade.get("coin", ""),
            trade.get("action", ""), trade.get("size", ""),
            trade.get("price", ""), trade.get("notional", ""),
            trade.get("leverage", ""), trade.get("confidence", ""),
            trade.get("success", ""), trade.get("mode", ""),
            trade.get("trigger", ""), trade.get("order_status", ""),
            trade.get("reasoning", "")[:200],
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=trade_history.csv"}
    )


@app.route("/api/performance", methods=["GET"])
def performance():
    state = state_store.load_state()
    summary = state_store.get_performance_summary(state)

    # Trade-based activity points (legacy)
    history = state.get("trade_history", [])
    equity_points = []
    for trade in history:
        equity_points.append({
            "timestamp": trade.get("timestamp", 0),
            "notional": trade.get("notional", "0"),
            "action": trade.get("action", ""),
            "coin": trade.get("coin", ""),
            "success": trade.get("success", False),
            "trigger": trade.get("trigger", "ai"),
        })

    # Real equity snapshots (portfolio value over time)
    equity_snapshots = state_store.get_equity_snapshots(state, limit=200)

    return jsonify({
        "summary": summary,
        "equity_curve": equity_points,
        "equity_snapshots": equity_snapshots,
        "daily_notional": state.get("daily_notional_by_day", {}),
        "timestamp": time.time()
    })


@app.route("/api/config", methods=["GET"])
def config():
    trading_pairs_str = os.getenv(
        "TRADING_PAIRS",
        "BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI,ARB,OP,NEAR,WIF,PEPE,INJ,TIA,SEI,RENDER,FET"
    )
    trading_pairs = [p.strip().upper() for p in trading_pairs_str.split(",") if p.strip()]

    return jsonify({
        "execution_mode": os.getenv("EXECUTION_MODE", "paper"),
        "enable_mainnet_trading": os.getenv("ENABLE_MAINNET_TRADING", "false"),
        "llm_model": os.getenv("LLM_MODEL", "anthropic/claude-opus-4.6"),
        "trading_pairs": trading_pairs,
        "trading_pairs_count": len(trading_pairs),
        "max_leverage": os.getenv("HARD_MAX_LEVERAGE", "10"),
        "max_margin_usage": os.getenv("MAX_MARGIN_USAGE", "0.8"),
        "max_drawdown_pct": os.getenv("MAX_DRAWDOWN_PCT", "0.15"),
        "trade_cooldown_sec": os.getenv("TRADE_COOLDOWN_SEC", "300"),
        "daily_notional_limit": os.getenv("DAILY_NOTIONAL_LIMIT_USD", "1000"),
        "safe_fallback_mode": os.getenv("SAFE_FALLBACK_MODE", "de_risk"),
        "default_sl_pct": os.getenv("DEFAULT_SL_PCT", "0.03"),
        "default_tp_pct": os.getenv("DEFAULT_TP_PCT", "0.05"),
        "enable_trailing_stop": os.getenv("ENABLE_TRAILING_STOP", "true"),
        "trailing_callback": os.getenv("DEFAULT_TRAILING_CALLBACK", "0.02"),
        "break_even_activation_pct": os.getenv("BREAK_EVEN_ACTIVATION_PCT", "0.015"),
        "enable_adaptive_cycle": os.getenv("ENABLE_ADAPTIVE_CYCLE", "true"),
        "correlation_threshold": os.getenv("CORRELATION_THRESHOLD", "0.7"),
        "timestamp": time.time()
    })


@app.route("/api/logs", methods=["GET"])
def logs():
    limit = request.args.get("limit", 100, type=int)
    log_file = os.getenv("LOG_FILE", "logs/hyperliquid_bot.log")

    if not os.path.exists(log_file):
        return jsonify({"logs": [], "timestamp": time.time()})

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        recent_lines = lines[-limit:]
        log_entries = []
        for line in recent_lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                log_entries.append(entry)
            except json.JSONDecodeError:
                log_entries.append({"message": line, "level": "INFO"})

        return jsonify({
            "logs": list(reversed(log_entries)),
            "total_lines": len(lines),
            "timestamp": time.time()
        })
    except IOError:
        return jsonify({"logs": [], "timestamp": time.time()})


@app.route("/metrics", methods=["GET"])
def prometheus_metrics():
    """Endpoint Prometheus per metriche in formato testo."""
    metrics_data = state_store.load_metrics()

    lines = []

    # Counters
    counters = [
        ("bot_cycles_total", "Total trading cycles", metrics_data.get("cycles_total", 0)),
        ("bot_cycles_failed_total", "Total failed cycles", metrics_data.get("cycles_failed", 0)),
        ("bot_trades_executed_total", "Total trades executed", metrics_data.get("trades_executed_total", 0)),
        ("bot_holds_total", "Total hold decisions", metrics_data.get("holds_total", 0)),
        ("bot_risk_rejections_total", "Total risk rejections", metrics_data.get("risk_rejections_total", 0)),
        ("bot_execution_failures_total", "Total execution failures", metrics_data.get("execution_failures_total", 0)),
    ]

    for name, help_text, value in counters:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")

    # Gauges from live status
    live_status = _read_json_file(LIVE_STATUS_PATH)
    portfolio_data = live_status.get("portfolio", {})

    gauges = [
        ("bot_balance_usd", "Current balance in USD", portfolio_data.get("total_balance", 0)),
        ("bot_available_balance_usd", "Available balance in USD", portfolio_data.get("available_balance", 0)),
        ("bot_margin_usage_ratio", "Current margin usage ratio", portfolio_data.get("margin_usage", 0)),
        ("bot_open_positions_count", "Number of open positions", portfolio_data.get("position_count", 0)),
        ("bot_unrealized_pnl_usd", "Total unrealized PnL in USD", portfolio_data.get("total_unrealized_pnl", 0)),
        ("bot_is_running", "Whether bot is running (1=yes, 0=no)", 1 if live_status.get("is_running") else 0),
        ("bot_cycle_count", "Current cycle count", live_status.get("cycle_count", 0)),
        ("bot_last_cycle_duration_seconds", "Last cycle duration", live_status.get("last_cycle_duration", 0)),
    ]

    state = state_store.load_state()
    gauges.append(("bot_peak_portfolio_value_usd", "Peak portfolio value", float(state.get("peak_portfolio_value", 0))))
    gauges.append(("bot_consecutive_losses", "Consecutive losing trades", state.get("consecutive_losses", 0)))
    gauges.append(("bot_consecutive_failed_cycles", "Consecutive failed cycles", state.get("consecutive_failed_cycles", 0)))

    for name, help_text, value in gauges:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {float(value)}")

    # Circuit breaker states
    cb_states = get_all_circuit_states()
    for cb_name, cb_state in cb_states.items():
        state_val = {"closed": 0, "open": 1, "half_open": 2}.get(cb_state.get("state", "closed"), 0)
        safe_name = cb_name.replace("-", "_").replace(" ", "_")
        lines.append(f"# HELP bot_circuit_breaker_{safe_name}_state Circuit breaker state (0=closed, 1=open, 2=half_open)")
        lines.append(f"# TYPE bot_circuit_breaker_{safe_name}_state gauge")
        lines.append(f"bot_circuit_breaker_{safe_name}_state {state_val}")
        lines.append(f"bot_circuit_breaker_{safe_name}_failures {cb_state.get('failure_count', 0)}")

    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain; version=0.0.4; charset=utf-8"
    )


def run_api_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    logger.info(f"Avvio server API su {host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    from utils.logging_config import setup_logging
    setup_logging(log_level="INFO", json_format=False, console_output=True)

    port = int(os.getenv("API_SERVER_PORT", "5000"))
    run_api_server(port=port, debug=True)