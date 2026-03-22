import csv
import io
import logging
import time

from flask import Blueprint, Response, jsonify, request

from api.auth import require_api_key
from api.config import STATE_PATH, METRICS_PATH
from state_store import StateStore
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

trading_bp = Blueprint("trading", __name__)

_state_store = StateStore(STATE_PATH, METRICS_PATH)
_trading_rl = get_rate_limiter("api_trading_endpoints", max_tokens=80, tokens_per_second=3.0)


def _rate_limited():
    if not _trading_rl.try_acquire(1):
        return jsonify({"error": "rate_limited"}), 429
    return None


@trading_bp.route("/api/trades", methods=["GET"])
@require_api_key
def trades():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    limit = request.args.get("limit", 50, type=int)
    if limit is None or limit < 1 or limit > 500:
        return jsonify({"error": "invalid_request"}), 400

    try:
        state = _state_store.load_state()
        history = state.get("trade_history", [])
        successful_history = [t for t in history if bool(t.get("success", False))]
        recent = list(reversed(successful_history[-limit:]))
        return jsonify({
            "trades": recent,
            "total": len(successful_history),
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Trading trades endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@trading_bp.route("/api/trades/export", methods=["GET"])
@require_api_key
def export_trades():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
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
    except Exception:
        logger.error("Trading export endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500


@trading_bp.route("/api/performance", methods=["GET"])
@require_api_key
def performance():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    try:
        state = _state_store.load_state()
        summary = _state_store.get_performance_summary(state)

        history = state.get("trade_history", [])
        successful_history = [t for t in history if bool(t.get("success", False))]

        equity_points = []
        for trade in successful_history:
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
    except Exception:
        logger.error("Trading performance endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500