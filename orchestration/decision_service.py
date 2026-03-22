from decimal import Decimal
from typing import Any, Dict, List, Optional

from orchestration.contracts import TradeDecision
from orchestration.order_context_builder import (
    build_managed_position_context,
    extract_protective_orders_for_coin,
    has_both_tp_sl,
)


def build_fallback_decision() -> TradeDecision:
    return TradeDecision(
        action="hold",
        size=Decimal("0"),
        leverage=1,
        confidence=0.0,
        stop_loss_pct=None,
        take_profit_pct=None,
        reasoning="LLM unavailable — safe fallback to hold",
    )


def get_decision_for_coin(
    coin: str,
    market_data,
    portfolio,
    tech_data: Dict[str, Any],
    all_mids: Optional[Dict[str, str]],
    funding_data: Optional[Dict[str, Any]],
    recent_trades: List[Dict[str, Any]],
    peak: Decimal,
    consecutive_losses: int,
    llm_engine,
    llm_rate_limiter,
    metrics,
    position_manager,
    exchange_client,
    sync_exchange_protective_orders,
    logger,
) -> TradeDecision:
    if llm_engine:
        llm_rate_limiter.acquire(1)
        metrics.increment("llm_calls_total")

        managed_position = build_managed_position_context(position_manager, coin)
        protective_orders = extract_protective_orders_for_coin(exchange_client, coin)

        has_open_position = coin in portfolio.positions and Decimal(str(portfolio.positions[coin].get("size", 0))) != 0
        if has_open_position and not has_both_tp_sl(protective_orders):
            logger.warning(f"{coin} missing TP/SL protective orders before LLM call, forcing sync")
            sync_exchange_protective_orders(coin)
            protective_orders = extract_protective_orders_for_coin(exchange_client, coin)

        decision_dict = llm_engine.get_trading_decision(
            market_data=market_data,
            portfolio_state=portfolio,
            technical_data=tech_data,
            all_mids=all_mids,
            funding_data=funding_data,
            recent_trades=recent_trades,
            peak_portfolio_value=peak,
            consecutive_losses=consecutive_losses,
            managed_position=managed_position,
            protective_orders=protective_orders,
        )
        if not decision_dict:
            metrics.increment("llm_errors_total")
            logger.warning(f"LLM failed for {coin}, using fallback")
            return build_fallback_decision()

        return TradeDecision.from_order_dict(decision_dict)

    return build_fallback_decision()