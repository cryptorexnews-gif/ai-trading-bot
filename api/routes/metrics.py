"""
Prometheus metrics endpoint — exports bot metrics in text format.
"""

import time

from flask import Blueprint, Response

from api.auth import require_api_key
from api.config import LIVE_STATUS_PATH, STATE_PATH, METRICS_PATH
from api.helpers import read_json_file
from state_store import StateStore
from utils.circuit_breaker import get_all_circuit_states

metrics_bp = Blueprint("metrics", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)


@metrics_bp.route("/metrics", methods=["GET"])
@require_api_key
def prometheus_metrics():
    """Export bot metrics in Prometheus text format."""
    metrics_data = _state_store.load_metrics()
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
    live_status = read_json_file(LIVE_STATUS_PATH)
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

    state = _state_store.load_state()
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