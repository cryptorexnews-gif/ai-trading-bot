from typing import Any, Dict, List


def normalize_strategy_mode(raw_mode: Any, default_mode: str) -> str:
    mode = str(raw_mode or default_mode).strip().lower()
    return mode if mode in {"trend", "scalping"} else default_mode


def normalize_trading_pairs(raw_pairs: Any, fallback_pairs: List[str]) -> List[str]:
    if not isinstance(raw_pairs, list):
        return list(fallback_pairs)

    pairs = [str(p).strip().upper() for p in raw_pairs if str(p).strip()]
    return pairs if pairs else list(fallback_pairs)


def normalize_runtime_params(raw_params: Any) -> Dict[str, Any]:
    return raw_params if isinstance(raw_params, dict) else {}


def load_runtime_config_payload(runtime_store, cfg) -> Dict[str, Any]:
    runtime = runtime_store.load()
    strategy_mode = normalize_strategy_mode(runtime.get("strategy_mode"), cfg.default_strategy_mode)
    trading_pairs = normalize_trading_pairs(runtime.get("trading_pairs"), list(cfg.trading_pairs))
    strategy_params = normalize_runtime_params(runtime.get("strategy_params"))

    return {
        "strategy_mode": strategy_mode,
        "trading_pairs": trading_pairs,
        "strategy_params": strategy_params,
    }


def runtime_has_changes(
    payload: Dict[str, Any],
    active_mode: str,
    active_pairs: List[str],
    active_params: Dict[str, Any]
) -> bool:
    return (
        payload.get("strategy_mode") != active_mode
        or payload.get("trading_pairs") != active_pairs
        or payload.get("strategy_params") != active_params
    )