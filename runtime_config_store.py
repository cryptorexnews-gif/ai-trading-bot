import time
from typing import Any, Dict, List

from utils.file_io import atomic_write_json, read_json_file


class RuntimeConfigStore:
    """Persiste la configurazione runtime modificabile dal frontend."""

    def __init__(self, path: str, default_trading_pairs: List[str], default_strategy_mode: str = "trend"):
        self.path = path
        self.default_trading_pairs = [p.strip().upper() for p in default_trading_pairs if p.strip()]
        normalized_mode = str(default_strategy_mode or "trend").strip().lower()
        self.default_strategy_mode = normalized_mode if normalized_mode in {"trend", "scalping"} else "trend"

    def _default(self) -> Dict[str, Any]:
        return {
            "strategy_mode": self.default_strategy_mode,
            "trading_pairs": self.default_trading_pairs or ["BTC", "ETH"],
            "strategy_params": {},
            "updated_at": time.time(),
        }

    def load(self) -> Dict[str, Any]:
        data = read_json_file(self.path, default=None)
        if data is None or not isinstance(data, dict):
            return self._default()

        defaults = self._default()
        for key, value in defaults.items():
            if key not in data:
                data[key] = value

        mode = str(data.get("strategy_mode", self.default_strategy_mode)).strip().lower()
        data["strategy_mode"] = mode if mode in {"trend", "scalping"} else self.default_strategy_mode
        data["trading_pairs"] = [
            str(p).strip().upper() for p in data.get("trading_pairs", []) if str(p).strip()
        ] or defaults["trading_pairs"]

        strategy_params = data.get("strategy_params", {})
        data["strategy_params"] = strategy_params if isinstance(strategy_params, dict) else {}

        return data

    def save(self, config: Dict[str, Any]) -> Dict[str, Any]:
        mode = str(config.get("strategy_mode", self.default_strategy_mode)).strip().lower()
        strategy_params = config.get("strategy_params", {})
        payload = {
            "strategy_mode": mode if mode in {"trend", "scalping"} else self.default_strategy_mode,
            "trading_pairs": [
                str(p).strip().upper() for p in config.get("trading_pairs", []) if str(p).strip()
            ] or self._default()["trading_pairs"],
            "strategy_params": strategy_params if isinstance(strategy_params, dict) else {},
            "updated_at": time.time(),
        }
        atomic_write_json(self.path, payload)
        return payload