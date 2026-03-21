"""
Portfolio service — fetches and constructs PortfolioState from Hyperliquid.
Extracted from the main bot to enable independent testing.
"""

import logging

from exchange_client import HyperliquidExchangeClient
from models import PortfolioState
from utils.hyperliquid_state import get_account_balances, get_open_positions

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
            raise RuntimeError("portfolio_state_unavailable_from_exchange")

        balances = get_account_balances(user_state)
        positions = get_open_positions(user_state)

        return PortfolioState(
            total_balance=balances["total_balance"],
            available_balance=balances["available_balance"],
            margin_usage=balances["margin_usage"],
            positions=positions
        )