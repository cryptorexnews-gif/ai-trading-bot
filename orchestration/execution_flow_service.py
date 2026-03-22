from decimal import Decimal
from typing import Any, Dict

from orchestration.contracts import TradeExecutionOutcome
from orchestration.execution_result_service import normalize_executed_price_and_size
from orchestration.fill_verification_service import verify_fill_after_execution


def execute_and_verify_trade(
    cfg,
    execution_engine,
    order_verifier,
    portfolio_service,
    coin: str,
    decision_order: Dict,
    market_data,
    positions: Dict[str, Dict[str, Any]],
    logger,
) -> TradeExecutionOutcome:
    snapshot = None
    if cfg.execution_mode == "live" and cfg.enable_mainnet_trading:
        snapshot = order_verifier.snapshot_position(cfg.wallet_address, coin)

    result = execution_engine.execute(coin, decision_order, market_data, positions)

    executed_price, executed_size = normalize_executed_price_and_size(
        result=result,
        market_price=market_data.last_price,
        requested_size=Decimal(str(decision_order["size"])),
    )

    fill_status = "unknown"
    if snapshot and result["success"] and decision_order["action"] in ["buy", "sell", "increase_position"]:
        fill_status, fill_ok, failure_reason = verify_fill_after_execution(
            wallet_address=cfg.wallet_address,
            order_verifier=order_verifier,
            portfolio_service=portfolio_service,
            coin=coin,
            decision=decision_order,
            snapshot=snapshot,
            executed_size=executed_size,
            logger=logger,
        )
        if not fill_ok:
            result["success"] = False
            result["reason"] = failure_reason

    return TradeExecutionOutcome(
        raw_result=result,
        executed_price=executed_price,
        executed_size=executed_size,
        fill_status=fill_status,
    )