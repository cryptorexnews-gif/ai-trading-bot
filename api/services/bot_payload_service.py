import os
import time
from typing import Any, Dict


def build_status_payload(
    live_status: Dict[str, Any],
    state: Dict[str, Any],
    metrics: Dict[str, Any],
    account_snapshot: Dict[str, Any],
    circuit_breakers: Dict[str, Any],
    rate_limiters: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "bot": live_status,
        "account": account_snapshot,
        "state": {
            "peak_portfolio_value": state.get("peak_portfolio_value", "0"),
            "consecutive_failed_cycles": state.get("consecutive_failed_cycles", 0),
            "consecutive_losses": state.get("consecutive_losses", 0),
        },
        "metrics": metrics,
        "circuit_breakers": circuit_breakers,
        "rate_limiters": rate_limiters,
        "timestamp": time.time(),
    }


def build_config_payload(runtime_cfg: Dict[str, Any]) -> Dict[str, Any]:
    env_pairs_raw = os.getenv(
        "TRADING_PAIRS",
        "BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI,ARB,OP,NEAR,WIF,PEPE,INJ,TIA,SEI,RENDER,FET"
    )
    env_pairs = [p.strip().upper() for p in env_pairs_raw.split(",") if p.strip()]

    runtime_pairs = [str(p).strip().upper() for p in runtime_cfg.get("trading_pairs", []) if str(p).strip()]
    strategy_mode = str(runtime_cfg.get("strategy_mode", "trend")).strip().lower()

    trading_pairs = runtime_pairs if runtime_pairs else env_pairs
    source = "runtime_config" if runtime_pairs else "env_default"

    return {
        "execution_mode": os.getenv("EXECUTION_MODE", "paper"),
        "enable_mainnet_trading": os.getenv("ENABLE_MAINNET_TRADING", "false"),
        "llm_model": os.getenv("LLM_MODEL", "deepseek/deepseek-v3.2"),
        "max_leverage": os.getenv("HARD_MAX_LEVERAGE", "10"),
        "max_drawdown_pct": os.getenv("MAX_DRAWDOWN_PCT", "0.15"),
        "default_sl_pct": os.getenv("TREND_SL_PCT", "0.04"),
        "default_tp_pct": os.getenv("TREND_TP_PCT", "0.08"),
        "enable_trailing_stop": os.getenv("ENABLE_TRAILING_STOP", "true"),
        "break_even_activation_pct": os.getenv("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02"),
        "max_order_notional_usd": os.getenv("MAX_ORDER_NOTIONAL_USD", "0"),
        "min_confidence_open": os.getenv("MIN_CONFIDENCE_OPEN", "0.72"),
        "min_confidence_manage": os.getenv("MIN_CONFIDENCE_MANAGE", "0.50"),
        "strategy_mode": strategy_mode,
        "trading_pairs": trading_pairs,
        "trading_pairs_count": len(trading_pairs),
        "trading_pairs_source": source,
        "timestamp": time.time(),
    }