from decimal import Decimal
from typing import Any, Dict, Tuple


def strategy_presets() -> Dict[str, Dict[str, str]]:
    return {
        "trend": {
            "cycle_sec": "1800",
            "min_cycle_sec": "900",
            "max_cycle_sec": "3600",
            "max_trades_per_cycle": "2",
            "hard_max_leverage": "6",
            "min_confidence_open": "0.72",
            "min_confidence_manage": "0.50",
            "max_order_margin_pct": "0.08",
            "trade_cooldown_sec": "600",
            "daily_notional_limit_usd": "1500",
            "max_drawdown_pct": "0.12",
            "max_single_asset_pct": "0.30",
            "emergency_margin_threshold": "0.85",
            "position_size_pct": "0.02",
            "volume_confirmation_threshold": "1.6",
            "sl_pct": "0.04",
            "tp_pct": "0.10",
            "break_even_activation_pct": "0.02",
            "trailing_activation_pct": "0.03",
            "trailing_callback": "0.015",
        },
        "scalping": {
            "cycle_sec": "300",
            "min_cycle_sec": "120",
            "max_cycle_sec": "900",
            "max_trades_per_cycle": "3",
            "hard_max_leverage": "3",
            "min_confidence_open": "0.68",
            "min_confidence_manage": "0.50",
            "max_order_margin_pct": "0.04",
            "trade_cooldown_sec": "90",
            "daily_notional_limit_usd": "500",
            "max_drawdown_pct": "0.07",
            "max_single_asset_pct": "0.20",
            "emergency_margin_threshold": "0.78",
            "position_size_pct": "0.01",
            "volume_confirmation_threshold": "1.3",
            "sl_pct": "0.015",
            "tp_pct": "0.03",
            "break_even_activation_pct": "0.008",
            "trailing_activation_pct": "0.012",
            "trailing_callback": "0.008",
        },
    }


def default_strategy_params(strategy_mode: str) -> Dict[str, str]:
    mode = str(strategy_mode or "trend").strip().lower()
    presets = strategy_presets()
    return presets["scalping"] if mode == "scalping" else presets["trend"]


def normalize_strategy_params(raw_params: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    if not isinstance(raw_params, dict):
        return {}, "invalid_strategy_params"

    int_keys = {
        "cycle_sec": (1, 86400),
        "min_cycle_sec": (1, 86400),
        "max_cycle_sec": (1, 86400),
        "max_trades_per_cycle": (1, 50),
        "trade_cooldown_sec": (0, 86400),
    }

    decimal_keys = {
        "hard_max_leverage": (Decimal("1"), Decimal("100")),
        "min_confidence_open": (Decimal("0"), Decimal("1")),
        "min_confidence_manage": (Decimal("0"), Decimal("1")),
        "max_order_margin_pct": (Decimal("0"), Decimal("1")),
        "daily_notional_limit_usd": (Decimal("0"), None),
        "max_drawdown_pct": (Decimal("0"), Decimal("1")),
        "max_single_asset_pct": (Decimal("0"), Decimal("1")),
        "emergency_margin_threshold": (Decimal("0"), Decimal("1")),
        "position_size_pct": (Decimal("0"), Decimal("1")),
        "volume_confirmation_threshold": (Decimal("0"), Decimal("20")),
        "sl_pct": (Decimal("0"), Decimal("1")),
        "tp_pct": (Decimal("0"), Decimal("2")),
        "break_even_activation_pct": (Decimal("0"), Decimal("1")),
        "trailing_activation_pct": (Decimal("0"), Decimal("1")),
        "trailing_callback": (Decimal("0"), Decimal("1")),
    }

    percent_keys = {
        "min_confidence_open",
        "min_confidence_manage",
        "max_order_margin_pct",
        "max_drawdown_pct",
        "max_single_asset_pct",
        "emergency_margin_threshold",
        "position_size_pct",
        "sl_pct",
        "tp_pct",
        "break_even_activation_pct",
        "trailing_activation_pct",
        "trailing_callback",
    }

    normalized: Dict[str, Any] = {}

    for key, value in raw_params.items():
        if key in int_keys:
            try:
                parsed = int(str(value))
            except Exception:
                return {}, f"invalid_param_{key}"
            min_val, max_val = int_keys[key]
            if parsed < min_val or parsed > max_val:
                return {}, f"out_of_range_{key}"
            normalized[key] = parsed
            continue

        if key in decimal_keys:
            try:
                parsed = Decimal(str(value))
            except Exception:
                return {}, f"invalid_param_{key}"

            if key in percent_keys and parsed > Decimal("1"):
                parsed = parsed / Decimal("100")

            min_val, max_val = decimal_keys[key]
            if parsed < min_val:
                return {}, f"out_of_range_{key}"
            if max_val is not None and parsed > max_val:
                return {}, f"out_of_range_{key}"

            normalized[key] = str(parsed)
            continue

    return normalized, ""