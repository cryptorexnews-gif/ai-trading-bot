"""
Portfolio service — fetches and constructs PortfolioState from Hyperliquid.
Extracted from the main bot to enable independent testing.
"""

import logging
from decimal import Decimal
from typing import Any, Dict

from exchange_client import HyperliquidExchangeClient
from models import PortfolioState

logger = logging.getLogger(__name__)


class PortfolioService:
    """Fetches portfolio state from Hyperliquid exchange."""

    def __init__(self, exchange_client: HyperliquidExchangeClient, wallet_address: str):
        self.exchange_client = exchange_client
        self.wallet_address = wallet_address

    def get_portfolio_state(self) -> PortfolioState:
        """Fetch current portfolio state from exchange."""
        user_state = self.exchange_client.get_user_state(self.wallet_address)
        if not user_state:
            logger.warning("Failed to get user state, returning empty portfolio")
            return PortfolioState(
                total_balance=Decimal("0"),
                available_balance=Decimal("0"),
                margin_usage=Decimal("0"),
                positions={}
            )

        margin_summary = user_state.get("marginSummary", {})
        total_balance = Decimal(str(margin_summary.get("accountValue", "0")))
        available_balance = Decimal(str(margin_summary.get("withdrawable", "0")))
        total_margin_used = Decimal(str(margin_summary.get("totalMarginUsed", "0")))
        margin_usage = (total_margin_used / total_balance) if total_balance > 0 else Decimal("0")

        positions: Dict[str, Dict[str, Any]] = {}
        for pos_wrapper in user_state.get("assetPositions", []):
            pos = pos_wrapper.get("position", {})
            coin = pos.get("coin", "")
            size = Decimal(str(pos.get("szi", "0")))
            if size != 0 and coin:
                positions[coin] = {
                    "size": size,
                    "entry_price": Decimal(str(pos.get("entryPx", "0"))),
                    "unrealized_pnl": Decimal(str(pos.get("unrealizedPnl", "0"))),
                    "margin_used": Decimal(str(pos.get("marginUsed", "0"))),
                }

        return PortfolioState(
            total_balance=total_balance,
            available_balance=available_balance,
            margin_usage=margin_usage,
            positions=positions
        )