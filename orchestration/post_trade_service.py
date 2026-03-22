from decimal import Decimal
from typing import Any, Dict

from orchestration.contracts import TradeDecision, TradeExecutionOutcome


def handle_successful_execution(
    coin: str,
    decision: TradeDecision,
    execution: TradeExecutionOutcome,
    state: Dict[str, Any],
    metrics,
    position_manager,
    sync_exchange_protective_orders,
    cancel_exchange_protective_orders,
    notifier,
    trade_record: Dict[str, Any],
    logger,
) -> Dict[str, Any]:
    notional = execution.notional

    if notional > 0:
        state.setdefault("last_trade_timestamp_by_coin", {})[coin] = trade_record.get("timestamp")
        metrics.increment("trades_executed_total")

        if decision.action in ["buy", "sell", "increase_position"]:
            is_long = decision.action in ["buy", "increase_position"]

            position_manager.register_position(
                coin=coin,
                size=execution.executed_size,
                entry_price=execution.executed_price,
                is_long=is_long,
                leverage=decision.leverage,
                sl_pct=decision.stop_loss_pct if isinstance(decision.stop_loss_pct, Decimal) else None,
                tp_pct=decision.take_profit_pct if isinstance(decision.take_profit_pct, Decimal) else None,
            )
            sync_exchange_protective_orders(coin)

        elif decision.action == "close_position":
            cancel_exchange_protective_orders(coin)
            position_manager.remove_position(coin)

        elif decision.action == "reduce_position":
            sync_exchange_protective_orders(coin)

        notifier.notify_trade(trade_record)
        logger.info(f"{coin} executed: reason={execution.reason}, notional=${notional}")
        return {"trades": 1, "notional": notional, "failed": False}

    metrics.increment("holds_total")
    logger.info(f"{coin}: hold (no trade)")
    return {"trades": 0, "notional": Decimal("0"), "failed": False}