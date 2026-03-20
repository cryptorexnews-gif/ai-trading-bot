import csv
import io
import time

from flask import Blueprint, Response, jsonify, request

from api.auth import require_api_key
from api.config import STATE_PATH, METRICS_PATH
from state_store import StateStore

trading_bp = Blueprint("trading", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)


@trading_bp.route("/api/trades", methods=["GET"])
@require_api_key
def trades():
    limit = request.args.get("limit", 50, type=int)
    if limit < 1 or limit > 500:
        return jsonify({"error": "limit must be between 1 and 500"}), 400
    state = _state_store.load_state()
    history = state.get("trade_history", [])
    recent = list(reversed(history[-limit:]))
    return jsonify({
        "trades": recent,
        "total": len(history),
        "timestamp": time.time()
    })


@trading_bp.route("/api/trades/export", methods=["GET"])
@require_api_key
def export_trades():
    """Export trade history as CSV file."""
    state = _state_store.load_state()
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


@trading_bp.route("/api/performance", methods=["GET"])
@require_api_key
def performance():
    state = _state_store.load_state()
    summary = _state_store.get_performance_summary(state)

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

    equity_snapshots = _state_store.get_equity_snapshots(state, limit=200)

    return jsonify({
        "summary": summary,
        "equity_curve": equity_points,
        "equity_snapshots": equity_snapshots,
        "daily_notional": state.get("daily_notional_by_day", {}),
        "timestamp": time.time()
    })