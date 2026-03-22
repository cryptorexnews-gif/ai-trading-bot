import csv
import io
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List

from flask import Blueprint, Response, jsonify, request

from api.auth import require_api_key
from api.helpers import post_hyperliquid_info
from utils.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)

trading_bp = Blueprint("trading", __name__)
_trading_rl = get_rate_limiter("api_trading_endpoints", max_tokens=80, tokens_per_second=3.0)


def _rate_limited():
    if not _trading_rl.try_acquire(1):
        return jsonify({"error": "rate_limited"}), 429
    return None


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _normalize_timestamp_seconds(raw_time: Any) -> float:
    ts = float(raw_time or 0)
    if ts <= 0:
        return 0.0
    if ts > 1e12:
        return ts / 1000.0
    return ts


def _infer_action(fill: Dict[str, Any]) -> str:
    side = str(fill.get("side", "")).strip().lower()
    direction = str(fill.get("dir", "")).strip().lower()

    if side in {"b", "buy"}:
        return "buy"
    if side in {"a", "s", "sell"}:
        return "sell"

    if "buy" in direction or "long" in direction:
        return "buy"
    if "sell" in direction or "short" in direction:
        return "sell"

    return "buy"


def _wallet_address() -> str:
    return os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()


def _fetch_user_fills() -> List[Dict[str, Any]]:
    wallet = _wallet_address()
    if not wallet:
        return []

    data = post_hyperliquid_info({"type": "userFills", "user": wallet}, timeout=20)
    if not isinstance(data, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for fill in data:
        coin = str(fill.get("coin", "")).strip().upper()
        price = _to_decimal(fill.get("px", "0"))
        size = _to_decimal(fill.get("sz", "0"))
        closed_pnl = _to_decimal(fill.get("closedPnl", "0"))
        fee = _to_decimal(fill.get("fee", "0"))
        timestamp = _normalize_timestamp_seconds(fill.get("time", 0))
        action = _infer_action(fill)
        notional = abs(price * size)

        normalized.append({
            "timestamp": timestamp,
            "coin": coin,
            "action": action,
            "size": size,
            "price": price,
            "notional": notional,
            "closed_pnl": closed_pnl,
            "fee": fee,
            "side_raw": fill.get("side", ""),
            "dir": fill.get("dir", ""),
            "start_position": fill.get("startPosition", ""),
            "hash": fill.get("hash", ""),
            "oid": fill.get("oid", ""),
            "tid": fill.get("tid", ""),
        })

    normalized.sort(key=lambda x: x["timestamp"])
    return normalized


def _build_daily_notional(fills: List[Dict[str, Any]]) -> Dict[str, str]:
    by_day: Dict[str, Decimal] = {}
    for f in fills:
        ts = float(f.get("timestamp", 0))
        if ts <= 0:
            continue
        day = time.strftime("%Y-%m-%d", time.gmtime(ts))
        by_day[day] = by_day.get(day, Decimal("0")) + _to_decimal(f.get("notional", "0"))

    return {k: str(v) for k, v in by_day.items()}


def _build_performance_summary(fills: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = 0
    losses = 0
    total_realized_pnl = Decimal("0")

    for fill in fills:
        pnl = _to_decimal(fill.get("closed_pnl", "0"))
        if pnl > 0:
            wins += 1
            total_realized_pnl += pnl
        elif pnl < 0:
            losses += 1
            total_realized_pnl += pnl

    classified = wins + losses
    win_rate = (wins / classified * 100.0) if classified > 0 else 0.0

    return {
        "total_trades": classified,
        "wins": wins,
        "losses": losses,
        "holds": 0,
        "failed_executions": 0,
        "executed_trades": len(fills),
        "classified_trades": classified,
        "win_rate": win_rate,
        "total_realized_pnl": str(total_realized_pnl),
        "consecutive_losses": 0,
    }


@trading_bp.route("/api/trades", methods=["GET"])
@require_api_key
def trades():
    rate_limit_resp = _rate_limited()
    if rate_limit_resp:
        return rate_limit_resp

    limit = request.args.get("limit", 50, type=int)
    if limit is None or limit < 1 or limit > 500:
        return jsonify({"error": "invalid_request"}), 400

    wallet = _wallet_address()
    if not wallet:
        return jsonify({"error": "wallet_not_configured"}), 500

    try:
        fills = _fetch_user_fills()
        recent = list(reversed(fills[-limit:]))

        trades_payload = []
        for fill in recent:
            trades_payload.append({
                "timestamp": fill["timestamp"],
                "coin": fill["coin"],
                "action": fill["action"],
                "size": str(fill["size"]),
                "price": str(fill["price"]),
                "notional": str(fill["notional"]),
                "leverage": 1,
                "confidence": 1.0,
                "reasoning": f"Hyperliquid fill ({fill.get('dir', '')})",
                "success": True,
                "mode": "live",
                "trigger": "exchange_fill",
                "order_status": "filled",
                "closed_pnl": str(fill["closed_pnl"]),
                "fee": str(fill["fee"]),
                "hash": fill.get("hash", ""),
                "oid": fill.get("oid", ""),
                "tid": fill.get("tid", ""),
            })

        return jsonify({
            "trades": trades_payload,
            "total": len(fills),
            "source": "hyperliquid_user_fills",
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

    wallet = _wallet_address()
    if not wallet:
        return jsonify({"error": "wallet_not_configured"}), 500

    try:
        fills = _fetch_user_fills()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "timestamp",
            "datetime_utc",
            "coin",
            "action",
            "side_raw",
            "dir",
            "size",
            "price",
            "notional",
            "closed_pnl",
            "fee",
            "start_position",
            "oid",
            "tid",
            "hash",
        ])

        for fill in fills:
            ts = fill.get("timestamp", 0)
            dt = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)) if ts else ""
            writer.writerow([
                ts,
                dt,
                fill.get("coin", ""),
                fill.get("action", ""),
                fill.get("side_raw", ""),
                fill.get("dir", ""),
                str(fill.get("size", "0")),
                str(fill.get("price", "0")),
                str(fill.get("notional", "0")),
                str(fill.get("closed_pnl", "0")),
                str(fill.get("fee", "0")),
                fill.get("start_position", ""),
                fill.get("oid", ""),
                fill.get("tid", ""),
                fill.get("hash", ""),
            ])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=hyperliquid_user_fills.csv"}
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

    wallet = _wallet_address()
    if not wallet:
        return jsonify({"error": "wallet_not_configured"}), 500

    try:
        fills = _fetch_user_fills()
        summary = _build_performance_summary(fills)
        daily_notional = _build_daily_notional(fills)

        equity_curve = []
        for fill in fills:
            equity_curve.append({
                "timestamp": fill.get("timestamp", 0),
                "notional": str(fill.get("notional", "0")),
                "action": fill.get("action", ""),
                "coin": fill.get("coin", ""),
                "success": True,
                "trigger": "exchange_fill",
                "closed_pnl": str(fill.get("closed_pnl", "0")),
                "fee": str(fill.get("fee", "0")),
            })

        return jsonify({
            "summary": summary,
            "equity_curve": equity_curve,
            "equity_snapshots": [],
            "daily_notional": daily_notional,
            "source": "hyperliquid_user_fills",
            "timestamp": time.time()
        })
    except Exception:
        logger.error("Trading performance endpoint failed", exc_info=True)
        return jsonify({"error": "internal_error"}), 500