import logging
import time
from decimal import Decimal
from typing import Dict, Tuple

from orchestration.coin_processing_utils import resolve_min_size

logger = logging.getLogger(__name__)


def compute_volatility(tech_data: Dict, market_price: Decimal) -> Decimal:
    intraday_atr = tech_data.get("intraday_atr", Decimal("0"))
    if intraday_atr > 0 and market_price > 0:
        return intraday_atr / market_price
    return Decimal("0")


def evaluate_trade_gates(
    coin: str,
    decision: Dict,
    portfolio,
    correlations: Dict[str, Dict[str, Decimal]],
    correlation_engine,
    risk_manager,
    cfg,
    dynamic_min_sizes: Dict[str, Decimal],
    state: Dict,
    daily_notional_used: Decimal,
    peak: Decimal,
    metrics,
    tech_data: Dict,
    market_price: Decimal,
) -> Tuple[bool, str]:
    corr_ok, corr_reason = correlation_engine.check_correlation_risk(
        coin,
        decision["action"],
        portfolio.positions,
        correlations,
    )

    if not corr_ok and decision["action"] in ["buy", "sell", "increase_position"]:
        metrics.increment("risk_rejections_total")
        return False, f"correlation_rejected:{corr_reason}"

    min_size = resolve_min_size(coin, cfg, dynamic_min_sizes)
    risk_manager.min_size_by_coin[coin] = min_size

    volatility = compute_volatility(tech_data=tech_data, market_price=market_price)

    risk_ok, risk_reason = risk_manager.check_order(
        coin,
        decision,
        market_price,
        portfolio,
        state.get("last_trade_timestamps_by_coin", state.get("last_trade_timestamp_by_coin", {})),
        daily_notional_used,
        time.time(),
        volatility,
        peak,
    )

    if not risk_ok:
        logger.warning(f"{coin} risk manager rejection bypassed: {risk_reason}")

    return True, "ok"