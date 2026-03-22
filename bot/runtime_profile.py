from decimal import Decimal
from typing import Any, Dict


def _to_decimal(value: Any, default: Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _to_percent_decimal(value: Any, default: Decimal) -> Decimal:
    dec = _to_decimal(value, default)
    if dec > Decimal("1"):
        return dec / Decimal("100")
    return dec


def _to_int(value: Any, default: int) -> int:
    try:
        return int(str(value))
    except Exception:
        return default


def _sync_risk_runtime(cfg, risk_manager, position_manager) -> None:
    risk_manager.hard_max_leverage = cfg.hard_max_leverage
    risk_manager.min_confidence_open = cfg.min_confidence_open
    risk_manager.min_confidence_manage = cfg.min_confidence_manage
    risk_manager.max_order_margin_pct = cfg.max_order_margin_pct
    risk_manager.trade_cooldown_sec = cfg.trade_cooldown_sec
    risk_manager.daily_notional_limit_usd = cfg.daily_notional_limit_usd
    risk_manager.max_drawdown_pct = cfg.max_drawdown_pct
    risk_manager.max_single_asset_pct = cfg.max_single_asset_pct
    risk_manager.emergency_margin_threshold = cfg.emergency_margin_threshold

    position_manager.default_sl_pct = cfg.trend_sl_pct
    position_manager.default_tp_pct = cfg.trend_tp_pct
    position_manager.default_trailing_callback = cfg.trend_trailing_callback
    position_manager.trailing_activation_pct = cfg.trend_trailing_activation_pct
    position_manager.break_even_activation_pct = cfg.trend_break_even_activation_pct


def apply_strategy_profile(cfg, risk_manager, position_manager, base_profile: Dict[str, Any], strategy_mode: str) -> None:
    if strategy_mode == "scalping":
        cfg.default_cycle_sec = cfg.scalping_default_cycle_sec
        cfg.min_cycle_sec = cfg.scalping_min_cycle_sec
        cfg.max_cycle_sec = cfg.scalping_max_cycle_sec
        cfg.max_trades_per_cycle = cfg.scalping_max_trades_per_cycle

        cfg.hard_max_leverage = cfg.scalping_hard_max_leverage
        cfg.min_confidence_open = cfg.scalping_min_confidence_open
        cfg.min_confidence_manage = cfg.scalping_min_confidence_manage
        cfg.max_order_margin_pct = cfg.scalping_max_order_margin_pct
        cfg.trade_cooldown_sec = cfg.scalping_trade_cooldown_sec
        cfg.daily_notional_limit_usd = cfg.scalping_daily_notional_limit_usd
        cfg.max_drawdown_pct = cfg.scalping_max_drawdown_pct
        cfg.max_single_asset_pct = cfg.scalping_max_single_asset_pct
        cfg.emergency_margin_threshold = cfg.scalping_emergency_margin_threshold
        cfg.trend_position_size_pct = cfg.scalping_position_size_pct
        cfg.volume_confirmation_threshold = cfg.scalping_volume_confirmation_threshold
        cfg.trend_sl_pct = cfg.scalping_sl_pct
        cfg.trend_tp_pct = cfg.scalping_tp_pct
        cfg.trend_break_even_activation_pct = cfg.scalping_break_even_activation_pct
        cfg.trend_trailing_activation_pct = cfg.scalping_trailing_activation_pct
        cfg.trend_trailing_callback = cfg.scalping_trailing_callback
    else:
        cfg.default_cycle_sec = base_profile["default_cycle_sec"]
        cfg.min_cycle_sec = base_profile["min_cycle_sec"]
        cfg.max_cycle_sec = base_profile["max_cycle_sec"]
        cfg.max_trades_per_cycle = base_profile["max_trades_per_cycle"]

        cfg.hard_max_leverage = base_profile["hard_max_leverage"]
        cfg.min_confidence_open = base_profile["min_confidence_open"]
        cfg.min_confidence_manage = base_profile["min_confidence_manage"]
        cfg.max_order_margin_pct = base_profile["max_order_margin_pct"]
        cfg.trade_cooldown_sec = base_profile["trade_cooldown_sec"]
        cfg.daily_notional_limit_usd = base_profile["daily_notional_limit_usd"]
        cfg.max_drawdown_pct = base_profile["max_drawdown_pct"]
        cfg.max_single_asset_pct = base_profile["max_single_asset_pct"]
        cfg.emergency_margin_threshold = base_profile["emergency_margin_threshold"]
        cfg.trend_position_size_pct = base_profile["trend_position_size_pct"]
        cfg.volume_confirmation_threshold = base_profile["volume_confirmation_threshold"]
        cfg.trend_sl_pct = base_profile["trend_sl_pct"]
        cfg.trend_tp_pct = base_profile["trend_tp_pct"]
        cfg.trend_break_even_activation_pct = base_profile["trend_break_even_activation_pct"]
        cfg.trend_trailing_activation_pct = base_profile["trend_trailing_activation_pct"]
        cfg.trend_trailing_callback = base_profile["trend_trailing_callback"]

    _sync_risk_runtime(cfg, risk_manager, position_manager)


def apply_runtime_param_overrides(cfg, risk_manager, position_manager, params: Dict[str, Any]) -> None:
    if not isinstance(params, dict):
        return

    cfg.default_cycle_sec = _to_int(params.get("cycle_sec", cfg.default_cycle_sec), cfg.default_cycle_sec)
    cfg.min_cycle_sec = _to_int(params.get("min_cycle_sec", cfg.min_cycle_sec), cfg.min_cycle_sec)
    cfg.max_cycle_sec = _to_int(params.get("max_cycle_sec", cfg.max_cycle_sec), cfg.max_cycle_sec)
    cfg.max_trades_per_cycle = _to_int(params.get("max_trades_per_cycle", cfg.max_trades_per_cycle), cfg.max_trades_per_cycle)

    cfg.hard_max_leverage = _to_decimal(params.get("hard_max_leverage", cfg.hard_max_leverage), cfg.hard_max_leverage)

    cfg.min_confidence_open = _to_percent_decimal(params.get("min_confidence_open", cfg.min_confidence_open), cfg.min_confidence_open)
    cfg.min_confidence_manage = _to_percent_decimal(params.get("min_confidence_manage", cfg.min_confidence_manage), cfg.min_confidence_manage)
    cfg.max_order_margin_pct = _to_percent_decimal(params.get("max_order_margin_pct", cfg.max_order_margin_pct), cfg.max_order_margin_pct)

    cfg.trade_cooldown_sec = _to_int(params.get("trade_cooldown_sec", cfg.trade_cooldown_sec), cfg.trade_cooldown_sec)
    cfg.daily_notional_limit_usd = _to_decimal(params.get("daily_notional_limit_usd", cfg.daily_notional_limit_usd), cfg.daily_notional_limit_usd)

    cfg.max_drawdown_pct = _to_percent_decimal(params.get("max_drawdown_pct", cfg.max_drawdown_pct), cfg.max_drawdown_pct)
    cfg.max_single_asset_pct = _to_percent_decimal(params.get("max_single_asset_pct", cfg.max_single_asset_pct), cfg.max_single_asset_pct)
    cfg.emergency_margin_threshold = _to_percent_decimal(params.get("emergency_margin_threshold", cfg.emergency_margin_threshold), cfg.emergency_margin_threshold)

    cfg.trend_position_size_pct = _to_percent_decimal(params.get("position_size_pct", cfg.trend_position_size_pct), cfg.trend_position_size_pct)
    cfg.volume_confirmation_threshold = _to_decimal(params.get("volume_confirmation_threshold", cfg.volume_confirmation_threshold), cfg.volume_confirmation_threshold)
    cfg.trend_sl_pct = _to_percent_decimal(params.get("sl_pct", cfg.trend_sl_pct), cfg.trend_sl_pct)
    cfg.trend_tp_pct = _to_percent_decimal(params.get("tp_pct", cfg.trend_tp_pct), cfg.trend_tp_pct)
    cfg.trend_break_even_activation_pct = _to_percent_decimal(
        params.get("break_even_activation_pct", cfg.trend_break_even_activation_pct),
        cfg.trend_break_even_activation_pct
    )
    cfg.trend_trailing_activation_pct = _to_percent_decimal(
        params.get("trailing_activation_pct", cfg.trend_trailing_activation_pct),
        cfg.trend_trailing_activation_pct
    )
    cfg.trend_trailing_callback = _to_percent_decimal(
        params.get("trailing_callback", cfg.trend_trailing_callback),
        cfg.trend_trailing_callback
    )

    if cfg.min_cycle_sec > cfg.max_cycle_sec:
        cfg.max_cycle_sec = cfg.min_cycle_sec
    if cfg.default_cycle_sec < cfg.min_cycle_sec:
        cfg.default_cycle_sec = cfg.min_cycle_sec
    if cfg.default_cycle_sec > cfg.max_cycle_sec:
        cfg.default_cycle_sec = cfg.max_cycle_sec

    _sync_risk_runtime(cfg, risk_manager, position_manager)