#!/usr/bin/env python3
"""
API Server for Hyperliquid Trading Bot Dashboard.
Lightweight Flask server that exposes bot state, metrics, and controls.
Runs alongside the main bot process.
"""

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict

from flask import Flask, jsonify, request
from flask_cors import CORS

from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Shared state paths (same as main bot)
STATE_PATH = "state/bot_state.json"
METRICS_PATH = "state/bot_metrics.json"
LIVE_STATUS_PATH = "state/bot_live_status.json"

state_store = StateStore(STATE_PATH, METRICS_PATH)


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


# Use the modern Flask JSON provider approach
from flask.json.provider import DefaultJSONProvider

class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)

app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)


def _read_json_file(path: str) -> Dict[str, Any]:
    """Safely read a JSON file."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "timestamp": time.time()})


@app.route("/api/status", methods=["GET"])
def bot_status():
    """Get current bot status including live data."""
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
        "timestamp": time.time()
    })


@app.route("/api/portfolio", methods=["GET"])
def portfolio():
    """Get current portfolio state."""
    live_status = _read_json_file(LIVE_STATUS_PATH)
    return jsonify({
        "portfolio": live_status.get("portfolio", {}),
        "timestamp": time.time()
    })


@app.route("/api/positions", methods=["GET"])
def positions():
    """Get current open positions."""
    live_status = _read_json_file(LIVE_STATUS_PATH)
    portfolio_data = live_status.get("portfolio", {})
    return jsonify({
        "positions": portfolio_data.get("positions", {}),
        "timestamp": time.time()
    })


@app.route("/api/trades", methods=["GET"])
def trades():
    """Get trade history with optional limit."""
    limit = request.args.get("limit", 50, type=int)
    state = state_store.load_state()
    history = state.get("trade_history", [])
    recent = list(reversed(history[-limit:]))
    return jsonify({
        "trades": recent,
        "total": len(history),
        "timestamp": time.time()
    })


@app.route("/api/performance", methods=["GET"])
def performance():
    """Get performance summary."""
    state = state_store.load_state()
    summary = state_store.get_performance_summary(state)

    history = state.get("trade_history", [])
    equity_points = []
    for trade in history:
        equity_points.append({
            "timestamp": trade.get("timestamp", 0),
            "notional": trade.get("notional", "0"),
            "action": trade.get("action", ""),
            "coin": trade.get("coin", ""),
            "success": trade.get("success", False)
        })

    return jsonify({
        "summary": summary,
        "equity_curve": equity_points,
        "daily_notional": state.get("daily_notional_by_day", {}),
        "timestamp": time.time()
    })


@app.route("/api/config", methods=["GET"])
def config():
    """Get current bot configuration (non-sensitive)."""
    return jsonify({
        "execution_mode": os.getenv("EXECUTION_MODE", "paper"),
        "enable_mainnet_trading": os.getenv("ENABLE_MAINNET_TRADING", "false"),
        "llm_model": os.getenv("LLM_MODEL", "anthropic/claude-opus-4.6"),
        "trading_pairs": ["BTC", "ETH", "SOL", "BNB", "ADA"],
        "max_leverage": os.getenv("HARD_MAX_LEVERAGE", "10"),
        "max_margin_usage": os.getenv("MAX_MARGIN_USAGE", "0.8"),
        "max_drawdown_pct": os.getenv("MAX_DRAWDOWN_PCT", "0.15"),
        "trade_cooldown_sec": os.getenv("TRADE_COOLDOWN_SEC", "300"),
        "daily_notional_limit": os.getenv("DAILY_NOTIONAL_LIMIT_USD", "1000"),
        "safe_fallback_mode": os.getenv("SAFE_FALLBACK_MODE", "de_risk"),
        "timestamp": time.time()
    })


@app.route("/api/logs", methods=["GET"])
def logs():
    """Get recent log entries."""
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


def run_api_server(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Start the API server."""
    logger.info(f"Starting API server on {host}:{port}")
    app.run(host=host, port=port, debug=debug, use_reloader=False)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    from utils.logging_config import setup_logging
    setup_logging(log_level="INFO", json_format=False, console_output=True)

    port = int(os.getenv("API_SERVER_PORT", "5000"))
    run_api_server(port=port, debug=True)