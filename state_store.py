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
        if notional <= 0:
            return daily_notional_by_day

        key = self.day_key(ts)
        current = Decimal(str(daily_notional_by_day.get(key, "0")))
        daily_notional_by_day[key] = str(current + notional)

        keys_sorted = sorted(daily_notional_by_day.keys(), reverse=True)
        keep_keys = set(keys_sorted[:7])
        return {k: v for k, v in daily_notional_by_day.items() if k in keep_keys}

    def add_trade_record(
        self,
        state: Dict[str, Any],
        trade: Dict[str, Any]
    ) -> None:
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

    @staticmethod
    def _is_failed_transaction(trade: Dict[str, Any]) -> bool:
        if not bool(trade.get("success", False)):
            return True

        order_status = str(trade.get("order_status", "")).strip().lower()
        if order_status in {"not_filled", "rejected", "status_error", "exchange_rejected", "http_error"}:
            return True

        reason = str(trade.get("reason", "")).strip().lower()
        if reason in {"set_leverage_failed", "order_not_filled", "exchange_rejected", "http_error", "status_error"}:
            return True

        return False

    def get_performance_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        history = state.get("trade_history", [])
        if not history:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "total_pnl": "0",
                "wins": 0,
                "losses": 0,
                "holds": 0,
                "failed_executions": 0,
                "executed_trades": 0,
                "classified_trades": 0,
                "consecutive_losses": 0
            }

        trade_actions = {"buy", "sell", "close_position", "increase_position", "reduce_position"}
        hold_actions = {"hold", "no_trade", "skip"}

        wins = 0
        losses = 0
        holds = 0
        failed_executions = 0
        executed_trades = 0

        for t in history:
            action = str(t.get("action", "")).strip().lower()
            trigger = str(t.get("trigger", "")).strip().lower()

            if self._is_failed_transaction(t):
                failed_executions += 1
                continue

            if action in hold_actions or action not in trade_actions:
                holds += 1
                continue

            executed_trades += 1

            if "realized_pnl" in t:
                realized = Decimal(str(t.get("realized_pnl", "0")))
                if realized > 0:
                    wins += 1
                elif realized < 0:
                    losses += 1
                continue

            if action == "close_position":
                if trigger in {"take_profit", "trailing_stop"}:
                    wins += 1
                elif trigger in {"stop_loss", "break_even_stop", "emergency"}:
                    losses += 1

        classified_trades = wins + losses
        win_rate = (wins / classified_trades * 100) if classified_trades > 0 else 0.0

        return {
            "total_trades": classified_trades,
            "wins": wins,
            "losses": losses,
            "holds": holds,
            "failed_executions": failed_executions,
            "executed_trades": executed_trades,
            "classified_trades": classified_trades,
            "win_rate": win_rate,
            "consecutive_losses": state.get("consecutive_losses", 0)
        }