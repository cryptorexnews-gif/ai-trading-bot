import csv
import io
import os
import time
from decimal import Decimal
from typing import Any, Dict, List

from api.helpers import post_hyperliquid_info


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def normalize_timestamp_seconds(raw_time: Any) -> float:
    ts = float(raw_time or 0)
    if ts <= 0:
        return 0.0
    if ts > 1e12:
        return ts / 1000.0
    return ts


def infer_action(fill: Dict[str, Any]) -> str:
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


def wallet_address() -> str:
    return os.getenv("HYPERLIQUID_WALLET_ADDRESS", "").strip()


def fetch_user_fills(wallet: str) -> List[Dict[str, Any]]:
    if not wallet:
        return []

    data = post_hyperliquid_info({"type": "userFills", "user": wallet}, timeout=20)
    if not isinstance(data, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for fill in data:
        coin = str(fill.get("coin", "")).strip().upper()
        price = to_decimal(fill.get("px", "0"))
        size = to_decimal(fill.get("sz", "0"))
        closed_pnl = to_decimal(fill.get("closedPnl", "0"))
        fee = to_decimal(fill.get("fee", "0"))
        timestamp = normalize_timestamp_seconds(fill.get("time", 0))
        action = infer_action(fill)
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


def build_daily_notional(fills: List[Dict[str, Any]]) -> Dict[str, str]:
    by_day: Dict[str, Decimal] = {}
    for fill in fills:
        ts = float(fill.get("timestamp", 0))
        if ts <= 0:
            continue
        day = time.strftime("%Y-%m-%d", time.gmtime(ts))
        by_day[day] = by_day.get(day, Decimal("0")) + to_decimal(fill.get("notional", "0"))
    return {k: str(v) for k, v in by_day.items()}


def build_performance_summary(fills: List[Dict[str, Any]]) -> Dict[str, Any]:
    wins = 0
    losses = 0
    total_realized_pnl = Decimal("0")

    for fill in fills:
        pnl = to_decimal(fill.get("closed_pnl", "0"))
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


def serialize_trades_payload(fills: List[Dict[str, Any]], limit: int) -> Dict[str, Any]:
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

    return {
        "trades": trades_payload,
        "total": len(fills),
        "source": "hyperliquid_user_fills",
        "timestamp": time.time(),
    }


def build_export_csv(fills: List[Dict[str, Any]]) -> str:
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
    return output.getvalue()


def build_equity_curve(fills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    curve = []
    for fill in fills:
        curve.append({
            "timestamp": fill.get("timestamp", 0),
            "notional": str(fill.get("notional", "0")),
            "action": fill.get("action", ""),
            "coin": fill.get("coin", ""),
            "success": True,
            "trigger": "exchange_fill",
            "closed_pnl": str(fill.get("closed_pnl", "0")),
            "fee": str(fill.get("fee", "0")),
        })
    return curve


def build_trades_response_payload(wallet: str, limit: int) -> Dict[str, Any]:
    fills = fetch_user_fills(wallet)
    return serialize_trades_payload(fills, limit)


def build_performance_response_payload(wallet: str) -> Dict[str, Any]:
    fills = fetch_user_fills(wallet)
    summary = build_performance_summary(fills)
    daily_notional = build_daily_notional(fills)
    equity_curve = build_equity_curve(fills)

    return {
        "summary": summary,
        "equity_curve": equity_curve,
        "equity_snapshots": [],
        "daily_notional": daily_notional,
        "source": "hyperliquid_user_fills",
        "timestamp": time.time(),
    }


def build_export_csv_for_wallet(wallet: str) -> str:
    fills = fetch_user_fills(wallet)
    return build_export_csv(fills)