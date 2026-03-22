import time
from decimal import Decimal
from typing import Any, Dict, List

from utils.file_io import atomic_write_json, read_json_file


class StateStore:
    def __init__(self, state_path: str, metrics_path: str):
        self.state_path = state_path
        self.metrics_path = metrics_path

    def _default_state(self) -> Dict[str, Any]:
        return {
            "peak_portfolio_value": "0",
            "consecutive_failed_cycles": 0,
            "consecutive_losses": 0,
            "last_trade_timestamp_by_coin": {},
            "daily_notional_by_day": {},
            "trade_history": [],
            "equity_snapshots": [],
        }

    def _default_metrics(self) -> Dict[str, Any]:
        return {
            "started_at": int(time.time()),
            "cycles_total": 0,
            "cycles_failed": 0,
            "trades_executed_total": 0,
            "trades_won": 0,
            "trades_lost": 0,
            "holds_total": 0,
            "risk_rejections_total": 0,
            "execution_failures_total": 0,
            "daily_notional_total": "0"
        }

    def load_state(self) -> Dict[str, Any]:
        data = read_json_file(self.state_path, default=None)
        if data is None:
            return self._default_state()
        # Ensure all default keys exist (migration safety)
        defaults = self._default_state()
        for key, value in defaults.items():
            if key not in data:
                data[key] = value
        return data

    def save_state(self, state: Dict[str, Any]) -> None:
        atomic_write_json(self.state_path, state)

    def load_metrics(self) -> Dict[str, Any]:
        data = read_json_file(self.metrics_path, default=None)
        if data is None:
            return self._default_metrics()
        return data

    def save_metrics(self, metrics: Dict[str, Any]) -> None:
        atomic_write_json(self.metrics_path, metrics)

    def day_key(self, ts: float) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(ts))

    def add_daily_notional(
        self,
        daily_notional_by_day: Dict[str, str],
        ts: float,
        notional: Decimal
    ) -> Dict[str, str]:
        """Add notional to daily tracker. Ignores negative values."""
        if notional <= 0:
            return daily_notional_by_day

        key = self.day_key(ts)
        current = Decimal(str(daily_notional_by_day.get(key, "0")))
        daily_notional_by_day[key] = str(current + notional)

        # Keep only last 7 days
        keys_sorted = sorted(daily_notional_by_day.keys(), reverse=True)
        keep_keys = set(keys_sorted[:7])
        return {k: v for k, v in daily_notional_by_day.items() if k in keep_keys}

    def add_trade_record(
        self,
        state: Dict[str, Any],
        trade: Dict[str, Any]
    ) -> None:
        """Add trade record to history, keep last 100 trades."""
        history = state.get("trade_history", [])
        history.append(trade)
        if len(history) > 100:
            history = history[-100:]
        state["trade_history"] = history

    def add_equity_snapshot(
        self,
        state: Dict[str, Any],
        balance: Decimal,
        unrealized_pnl: Decimal,
        position_count: int,
        margin_usage: Decimal,
    ) -> None:
        """Save portfolio value snapshot for real equity curve. Keep last 500."""
        snapshots = state.get("equity_snapshots", [])
        snapshots.append({
            "timestamp": time.time(),
            "balance": str(balance),
            "unrealized_pnl": str(unrealized_pnl),
            "total_value": str(balance + unrealized_pnl),
            "position_count": position_count,
            "margin_usage": str(margin_usage),
        })
        if len(snapshots) > 500:
            snapshots = snapshots[-500:]
        state["equity_snapshots"] = snapshots

    def get_equity_snapshots(self, state: Dict[str, Any], limit: int = 200) -> List[Dict[str, Any]]:
        snapshots = state.get("equity_snapshots", [])
        return snapshots[-limit:] if snapshots else []

    def get_recent_trades(self, state: Dict[str, Any], count: int = 5) -> List[Dict[str, Any]]:
        history = state.get("trade_history", [])
        return history[-count:] if history else []

    def get_performance_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        history = state.get("trade_history", [])
        if not history:
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": "0", "wins": 0, "losses": 0, "holds": 0, "consecutive_losses": 0}

        trade_actions = {"buy", "sell", "close_position", "increase_position", "reduce_position"}
        hold_actions = {"hold", "no_trade", "skip"}

        wins = 0
        losses = 0
        holds = 0

        for t in history:
            action = str(t.get("action", "")).strip().lower()
            success = bool(t.get("success", False))

            if action in hold_actions or action not in trade_actions:
                holds += 1
                continue

            if success:
                wins += 1
            else:
                losses += 1

        actual_trades = wins + losses

        return {
            "total_trades": actual_trades,
            "wins": wins,
            "losses": losses,
            "holds": holds,
            "win_rate": (wins / actual_trades * 100) if actual_trades > 0 else 0.0,
            "consecutive_losses": state.get("consecutive_losses", 0)
        }