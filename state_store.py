import json
import os
import time
from decimal import Decimal
from typing import Any, Dict


class StateStore:
    def __init__(self, state_path: str, metrics_path: str):
        self.state_path = state_path
        self.metrics_path = metrics_path

    def _default_state(self) -> Dict[str, Any]:
        return {
            "peak_portfolio_value": "0",
            "consecutive_failed_cycles": 0,
            "last_trade_timestamp_by_coin": {},
            "daily_notional_by_day": {}
        }

    def _default_metrics(self) -> Dict[str, Any]:
        return {
            "started_at": int(time.time()),
            "cycles_total": 0,
            "cycles_failed": 0,
            "trades_executed_total": 0,
            "holds_total": 0,
            "risk_rejections_total": 0,
            "execution_failures_total": 0,
            "daily_notional_total": "0"
        }

    def load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_path):
            return self._default_state()
        with open(self.state_path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def save_state(self, state: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as file_obj:
            json.dump(state, file_obj, ensure_ascii=False, indent=2)

    def load_metrics(self) -> Dict[str, Any]:
        if not os.path.exists(self.metrics_path):
            return self._default_metrics()
        with open(self.metrics_path, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)

    def save_metrics(self, metrics: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.metrics_path) or ".", exist_ok=True)
        with open(self.metrics_path, "w", encoding="utf-8") as file_obj:
            json.dump(metrics, file_obj, ensure_ascii=False, indent=2)

    def day_key(self, ts: float) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(ts))

    def add_daily_notional(
        self,
        daily_notional_by_day: Dict[str, str],
        ts: float,
        notional: Decimal
    ) -> Dict[str, str]:
        key = self.day_key(ts)
        current = Decimal(str(daily_notional_by_day.get(key, "0")))
        daily_notional_by_day[key] = str(current + notional)

        keys_sorted = sorted(daily_notional_by_day.keys(), reverse=True)
        keep_keys = set(keys_sorted[:7])
        return {k: v for k, v in daily_notional_by_day.items() if k in keep_keys}