import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models import PortfolioState, TradingAction

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manages trading risk: position sizing, leverage, drawdown, margin, correlation.
    Ultra-conservative for trend trading strategy.
    """

    def __init__(
        self,
        min_size_by_coin: Dict[str, Decimal],
        hard_max_leverage: Decimal = Decimal("10"),
        min_confidence_open: Decimal = Decimal("0.72"),
        min_confidence_manage: Decimal = Decimal("0.50"),
        max_margin_usage: Decimal = Decimal("0.8"),
        max_order_margin_pct: Decimal = Decimal("0.1"),
        trade_cooldown_sec: int = 300,
        daily_notional_limit_usd: Decimal = Decimal("1000"),
        volatility_multiplier: Decimal = Decimal("1.2"),
        max_drawdown_pct: Decimal = Decimal("0.15"),
        max_single_asset_pct: Decimal = Decimal("0.35"),
        emergency_margin_threshold: Decimal = Decimal("0.88"),
    ):
        self.min_size_by_coin = min_size_by_coin
        self.hard_max_leverage = hard_max_leverage
        self.min_confidence_open = min_confidence_open
        self.min_confidence_manage = min_confidence_manage
        self.max_margin_usage = max_margin_usage
        self.max_order_margin_pct = max_order_margin_pct
        self.trade_cooldown_sec = trade_cooldown_sec
        self.daily_notional_limit_usd = daily_notional_limit_usd
        self.volatility_multiplier = volatility_multiplier
        self.max_drawdown_pct = max_drawdown_pct
        self.max_single_asset_pct = max_single_asset_pct
        self.emergency_margin_threshold = emergency_margin_threshold

    def check_order(
        self,
        coin: str,
        order: Dict[str, Any],
        current_price: Decimal,
        portfolio: PortfolioState,
        last_trade_timestamps: Dict[str, float],
        daily_notional_used: Decimal,
        current_time: float,
        volatility_pct: Optional[Decimal] = None,
        peak_portfolio_value: Optional[Decimal] = None,
    ) -> Tuple[bool, str]:
        """
        Comprehensive risk check for an order.
        Returns (is_safe, reason).
        """
        action = str(order.get("action", "")).strip().lower()
        size = Decimal(str(order.get("size", 0)))
        leverage = Decimal(str(order.get("leverage", 1)))
        confidence = Decimal(str(order.get("confidence", 0)))

        # Unknown action
        if action not in {a.value for a in TradingAction}:
            return False, "unknown_action"

        # HOLD always passes
        if action == TradingAction.HOLD.value:
            return True, "hold"

        # Confidence thresholds
        if action in [TradingAction.BUY.value, TradingAction.SELL.value, TradingAction.INCREASE_POSITION.value]:
            if confidence < self.min_confidence_open:
                return False, "confidence_open_too_low"
        elif confidence < self.min_confidence_manage:
            return False, "confidence_manage_too_low"

        # Leverage bounds
        if leverage < 1 or leverage > self.hard_max_leverage:
            return False, "leverage_out_of_bounds"

        # Size validation
        if size <= 0:
            return False, "size_zero_or_negative"

        min_size = self.min_size_by_coin.get(coin, Decimal("0.001"))
        if size < min_size:
            return False, f"size_below_minimum_{min_size}"

        # Position conflict checks
        if action in [TradingAction.BUY.value, TradingAction.SELL.value]:
            if self._would_conflict_with_existing_position(coin, action, portfolio):
                return False, f"conflict_{action}_while_position_exists"

        # Margin usage check
        if self._would_exceed_margin_usage(coin, size, current_price, leverage, portfolio):
            return False, "margin_usage_too_high"

        # Single asset exposure
        if self._would_exceed_single_asset_limit(coin, size, current_price, leverage, portfolio):
            return False, "single_asset_exposure_too_high"

        # Drawdown protection
        if peak_portfolio_value and portfolio.total_balance > 0:
            drawdown = (peak_portfolio_value - portfolio.total_balance) / peak_portfolio_value
            if drawdown >= self.max_drawdown_pct:
                return False, "max_drawdown_breached"
            if drawdown >= self.max_drawdown_pct * Decimal("0.66"):
                logger.info(
                    f"Drawdown warning: {float(drawdown) * 100:.1f}% "
                    f"approaching limit of {float(self.max_drawdown_pct) * 100:.1f}%"
                )

        # Trade cooldown
        if coin in last_trade_timestamps:
            time_since_last = current_time - last_trade_timestamps[coin]
            if time_since_last < self.trade_cooldown_sec:
                return False, "cooldown_active"

        # Daily notional limit
        notional = size * current_price
        if daily_notional_used + notional > self.daily_notional_limit_usd:
            return False, "daily_notional_cap_exceeded"

        # Volatility adjustment
        if volatility_pct and volatility_pct > Decimal("0.02"):  # 2% ATR
            adjusted_size = size * (Decimal("0.02") / volatility_pct)
            if adjusted_size < min_size:
                return False, "volatility_too_high_for_min_size"
            order["size"] = adjusted_size  # Modify order in place

        return True, "ok"

    def check_emergency_derisk(self, portfolio: PortfolioState) -> bool:
        """Check if emergency de-risk is needed (margin usage too high)."""
        return portfolio.margin_usage >= self.emergency_margin_threshold

    def get_emergency_close_coin(self, portfolio: PortfolioState) -> Optional[str]:
        """Get coin with worst PnL for emergency closing."""
        if not portfolio.positions:
            return None

        worst_coin = None
        worst_pnl = Decimal("0")

        for coin, pos in portfolio.positions.items():
            pnl = Decimal(str(pos.get("unrealized_pnl", 0)))
            if pnl < worst_pnl:
                worst_pnl = pnl
                worst_coin = coin

        return worst_coin

    def _would_conflict_with_existing_position(
        self, coin: str, action: str, portfolio: PortfolioState
    ) -> bool:
        """Check if order would conflict with existing position."""
        if coin not in portfolio.positions:
            return False

        existing_size = Decimal(str(portfolio.positions[coin]["size"]))
        is_long = existing_size > 0

        if action == TradingAction.BUY.value and is_long:
            return True  # Can't buy while long
        if action == TradingAction.SELL.value and not is_long:
            return True  # Can't sell while short

        return False

    def _would_exceed_margin_usage(
        self, coin: str, size: Decimal, price: Decimal, leverage: Decimal, portfolio: PortfolioState
    ) -> bool:
        """Check if order would exceed max margin usage."""
        notional = size * price
        margin_needed = notional / leverage

        # Subtract existing margin for this coin if position exists
        existing_margin = Decimal("0")
        if coin in portfolio.positions:
            pos = portfolio.positions[coin]
            existing_size = abs(Decimal(str(pos["size"])))
            existing_price = Decimal(str(pos.get("entry_price", price)))
            existing_margin = (existing_size * existing_price) / Decimal(str(pos.get("leverage", 1)))

        new_margin_usage = (portfolio.margin_usage * portfolio.total_balance + margin_needed - existing_margin) / portfolio.total_balance

        return new_margin_usage > self.max_margin_usage

    def _would_exceed_single_asset_limit(
        self, coin: str, size: Decimal, price: Decimal, leverage: Decimal, portfolio: PortfolioState
    ) -> bool:
        """Check if order would exceed single asset exposure limit."""
        notional = size * price

        # Add to existing exposure
        existing_exposure = Decimal("0")
        if coin in portfolio.positions:
            pos = portfolio.positions[coin]
            existing_size = abs(Decimal(str(pos["size"])))
            existing_price = Decimal(str(pos.get("entry_price", price)))
            existing_exposure = existing_size * existing_price

        total_exposure = existing_exposure + notional
        portfolio_value = portfolio.total_balance + portfolio.get_total_unrealized_pnl()

        if portfolio_value <= 0:
            return True

        exposure_pct = total_exposure / portfolio_value
        return exposure_pct > self.max_single_asset_pct

    def calculate_position_size(
        self,
        coin: str,
        confidence: Decimal,
        current_price: Decimal,
        portfolio: PortfolioState,
        is_trend_trade: bool = False,
        volatility_pct: Optional[Decimal] = None,
    ) -> Decimal:
        """
        Calculate safe position size based on risk parameters.
        For trend trades: ultra-conservative sizing.
        """
        if current_price <= 0 or portfolio.total_balance <= 0:
            return Decimal("0")

        # Base size: 1% of portfolio for regular trades, 2% for trend trades
        base_pct = Decimal("0.02") if is_trend_trade else Decimal("0.01")
        base_size_usd = portfolio.total_balance * base_pct

        # Confidence multiplier (0.5-1.5x)
        confidence_multiplier = Decimal("0.5") + (confidence * Decimal("1.0"))

        # Volatility adjustment
        volatility_multiplier = Decimal("1.0")
        if volatility_pct and volatility_pct > Decimal("0.01"):
            volatility_multiplier = Decimal("0.01") / volatility_pct
            volatility_multiplier = max(Decimal("0.1"), min(Decimal("1.0"), volatility_multiplier))

        # Available margin consideration
        available_margin = portfolio.available_balance
        margin_pct = min(Decimal("0.1"), available_margin / portfolio.total_balance)  # Max 10% of portfolio

        # Calculate size
        size_usd = base_size_usd * confidence_multiplier * volatility_multiplier * margin_pct
        size_coin = size_usd / current_price

        # Apply min/max bounds
        min_size = self.min_size_by_coin.get(coin, Decimal("0.001"))
        size_coin = max(min_size, size_coin)

        # Ensure doesn't exceed single asset limit
        max_size_coin = (portfolio.total_balance * self.max_single_asset_pct) / current_price
        size_coin = min(size_coin, max_size_coin)

        return size_coin

    def calculate_leverage(
        self,
        coin: str,
        confidence: Decimal,
        current_price: Decimal,
        portfolio: PortfolioState,
        is_trend_trade: bool = False,
    ) -> int:
        """
        Calculate safe leverage based on confidence and market conditions.
        Trend trades use lower leverage for safety.
        """
        # Base leverage
        base_leverage = 3 if is_trend_trade else 5

        # Confidence adjustment
        if confidence >= Decimal("0.85"):
            leverage = base_leverage
        elif confidence >= Decimal("0.75"):
            leverage = max(2, base_leverage - 1)
        else:
            leverage = max(1, base_leverage - 2)

        # Margin usage consideration
        if portfolio.margin_usage > Decimal("0.5"):
            leverage = max(1, leverage - 1)
        if portfolio.margin_usage > Decimal("0.7"):
            leverage = 1  # No leverage if margin high

        # Hard cap
        leverage = min(int(leverage), int(self.hard_max_leverage))

        return leverage