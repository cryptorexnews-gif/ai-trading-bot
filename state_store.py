import json
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional


# Security Fix #7: Restrictive file permissions
_FILE_PERMISSION = 0o600  # Owner read/write only
_DIR_PERMISSION = 0o700   # Owner read/write/execute only


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

    def _ensure_secure_directory(self, path: str) -> None:
        """Create directory with restrictive permissions if it doesn't exist."""
        dir_path = os.path.dirname(path) or "."
        if dir_path != ".":
            os.makedirs(dir_path, mode=_DIR_PERMISSION, exist_ok=True)
            # Also fix permissions if directory already existed with wrong perms
            try:
                os.chmod(dir_path, _DIR_PERMISSION)
            except OSError:
                pass  # May fail on some filesystems, non-critical

    def _atomic_write(self, path: str, data: Dict[str, Any]) -> None:
        """Write to temp file then rename for crash safety. Sets restrictive permissions."""
        self._ensure_secure_directory(path)
        tmp_path = path + ".tmp"

        # Create file with restrictive permissions using os.open + os.fdopen
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_PERMISSION)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
                json.dump(data, file_obj, ensure_ascii=False, indent=2)
                file_obj.flush()
                os.fsync(file_obj.fileno())
        except Exception:
            # fd is closed by os.fdopen even on error
            raise

        os.replace(tmp_path, path)
        # Ensure final file also has correct permissions
        try:
            os.chmod(path, _FILE_PERMISSION)
        except OSError:
            pass

    def load_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.state_path):
            return self._default_state()
        try:
            with open(self.state_path, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
                # Assicura che tutte le chiavi predefinite esistano (sicurezza migrazione)
                defaults = self._default_state()
                for key, value in defaults.items():
                    if key not in data:
                        data[key] = value
                return data
        except (json.JSONDecodeError, IOError):
            return self._default_state()

    def save_state(self, state: Dict[str, Any]) -> None:
        self._atomic_write(self.state_path, state)

    def load_metrics(self) -> Dict[str, Any]:
        if not os.path.exists(self.metrics_path):
            return self._default_metrics()
        try:
            with open(self.metrics_path, "r", encoding="utf-8") as file_obj:
                return json.load(file_obj)
        except (json.JSONDecodeError, IOError):
            return self._default_metrics()

    def save_metrics(self, metrics: Dict[str, Any]) -> None:
        self._atomic_write(self.metrics_path, metrics)

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

    def add_trade_record(
        self,
        state: Dict[str, Any],
        trade: Dict[str, Any]
    ) -> None:
        """Aggiungi record trade alla storia, mantieni ultimi 100 trade."""
        history = state.get("trade_history", [])
        history.append(trade)
        # Mantieni solo ultimi 100 trade per evitare crescita illimitata
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
        """
        Salva snapshot del valore portfolio per equity curve reale.
        Mantieni ultimi 500 snapshot (circa 8 ore con cicli da 60s).
        """
        snapshots = state.get("equity_snapshots", [])
        snapshots.append({
            "timestamp": time.time(),
            "balance": str(balance),
            "unrealized_pnl": str(unrealized_pnl),
            "total_value": str(balance + unrealized_pnl),
            "position_count": position_count,
            "margin_usage": str(margin_usage),
        })
        # Mantieni ultimi 500 snapshot
        if len(snapshots) > 500:
            snapshots = snapshots[-500:]
        state["equity_snapshots"] = snapshots

    def get_equity_snapshots(self, state: Dict[str, Any], limit: int = 200) -> List[Dict[str, Any]]:
        """Ottieni snapshot equity recenti."""
        snapshots = state.get("equity_snapshots", [])
        return snapshots[-limit:] if snapshots else []

    def get_recent_trades(self, state: Dict[str, Any], count: int = 5) -> List[Dict[str, Any]]:
        """Ottieni i trade più recenti."""
        history = state.get("trade_history", [])
        return history[-count:] if history else []

    def get_performance_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Calcola riepilogo performance dalla storia trade."""
        history = state.get("trade_history", [])
        if not history:
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": "0"}

        total = len(history)
        wins = sum(1 for t in history if t.get("success", False) and t.get("action") != "hold")
        losses = sum(1 for t in history if not t.get("success", True) and t.get("action") != "hold")
        holds = sum(1 for t in history if t.get("action") == "hold")
        actual_trades = total - holds

        return {
            "total_trades": actual_trades,
            "wins": wins,
            "losses": losses,
            "holds": holds,
            "win_rate": (wins / actual_trades * 100) if actual_trades > 0 else 0.0,
            "consecutive_losses": state.get("consecutive_losses", 0)
        }