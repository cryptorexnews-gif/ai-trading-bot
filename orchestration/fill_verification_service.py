from decimal import Decimal
from typing import Any, Dict, Tuple

from orchestration.coin_processing_utils import late_confirm_fill


def verify_fill_after_execution(
    wallet_address: str,
    order_verifier,
    portfolio_service,
    coin: str,
    decision: Dict[str, Any],
    snapshot: Dict[str, Any],
    executed_size: Decimal,
    logger,
) -> Tuple[str, bool, str]:
    """
    Verify fill status after execution.

    Returns:
      - fill_status: status string
      - is_confirmed: whether execution should remain successful
      - failure_reason: reason to set if not confirmed
    """
    expected_side = "buy" if decision["action"] in ["buy", "increase_position"] else "sell"
    expected_size = Decimal(str(executed_size))

    verification = order_verifier.verify_fill(
        wallet_address,
        coin,
        expected_side,
        expected_size,
        snapshot,
    )
    fill_status = verification.get("fill_status", "unknown")

    if fill_status != "not_filled":
        return fill_status, True, ""

    late_confirmed, late_status = late_confirm_fill(
        coin=coin,
        snapshot=snapshot,
        expected_side=expected_side,
        expected_size=expected_size,
        portfolio_service=portfolio_service,
    )
    if late_confirmed:
        logger.info(f"{coin} late fill confirmation succeeded: {late_status}")
        return late_status, True, ""

    logger.warning(f"{coin} order NOT FILLED — marking as failed")
    return "not_filled", False, "order_not_filled"