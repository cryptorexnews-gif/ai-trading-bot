= 1.">
import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

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
        max_order_notional_usd: Decimal = Decimal("0"),
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
        self.max_order_notional_usd = max_order_notional_usd
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
        raw_size = Decimal(str(order.get("size", 0)))
        leverage = Decimal(str(order.get("leverage", 1)))
        confidence = Decimal(str(order.get("confidence", 0)))

        if action not in {a.value for a in TradingAction}:
            return False, "unknown_action"

        if action == TradingAction.HOLD.value:
            return True, "hold"

        open_actions = {
            TradingAction.BUY.value,
            TradingAction.SELL.value,
            TradingAction.INCREASE_POSITION.value,
        }
        manage_actions = {
            TradingAction.CLOSE_POSITION.value,
            TradingAction.REDUCE_POSITION.value,
            TradingAction.CHANGE_LEVERAGE.value,
        }

        if action in open_actions:
            if confidence < self.min_confidence_open:
                return False, "confidence_open_too_low"
        else:
            if confidence < self.min_confidence_manage:
                return False, "confidence_manage_too_low"

        # Lascia libertà all'LLM sulla leva: validiamo solo leverage minimo.
        if leverage < 1:
            return False, "leverage_out_of_bounds"

        existing_size = Decimal("0")
        if coin in portfolio.positions:
            existing_size = Decimal(str(portfolio.positions[coin].get("size", 0)))

        # Normalize size by action type
        if action == TradingAction.CHANGE_LEVERAGE.value:
            size = Decimal("0")
        elif action == TradingAction.CLOSE_POSITION.value:
            if existing_size == 0:
                return False, "no_position_to_close"
            requested = abs(raw_size)
            size = abs(existing_size) if requested <= 0 else min(requested, abs(existing_size))
            order["size"] = size
        elif action == TradingAction.REDUCE_POSITION.value:
            if existing_size == 0:
                return False, "no_position_to_reduce"
            if raw_size <= 0:
                return False, "size_zero_or_negative"
            size = min(abs(raw_size), abs(existing_size))
            order["size"] = size
        else:
            # Open / increase actions
            if raw_size <= 0:
                return False, "size_zero_or_negative"
            size = abs(raw_size)

            min_size = self.min_size_by_coin.get(coin, Decimal("0.001"))
            if size < min_size:
                return False, f"size_below_minimum_{min_size}"

        if action in {TradingAction.BUY.value, TradingAction.SELL.value} and existing_size != 0:
            if action == TradingAction.BUY.value and existing_size < 0:
                return False, "conflict_buy_while_short"
            if action == TradingAction.SELL.value and existing_size > 0:
                return False, "conflict_sell_while_long"
            if action == TradingAction.BUY.value and existing_size > 0:
                return False, "conflict_buy_while_long"
            if action == TradingAction.SELL.value and existing_size < 0:
                return False, "conflict_sell_while_short"

        # Open-only risk checks
        if action in open_actions:
            notional = size * current_price
            margin_needed = notional / leverage if leverage > 0 else Decimal("0")

            if self.max_order_notional_usd > 0 and notional > self.max_order_notional_usd:
                return False, "max_order_notional_exceeded"

            if self.max_order_margin_pct > 0 and portfolio.total_balance > 0:
                max_margin_allowed = portfolio.total_balance * self.max_order_margin_pct
                if margin_needed > max_margin_allowed:
                    return False, "order_margin_pct_exceeded"

            if margin_needed > portfolio.available_balance:
                return False, "insufficient_available_balance"

            if self._would_exceed_margin_usage(coin, size, current_price, leverage, portfolio):
                return False, "margin_usage_too_high"

            if self._would_exceed_single_asset_limit(coin, size, current_price, leverage, portfolio):
                return False, "single_asset_exposure_too_high"

            if peak_portfolio_value and portfolio.total_balance > 0:
                drawdown = (peak_portfolio_value - portfolio.total_balance) / peak_portfolio_value
                if drawdown >= self.max_drawdown_pct:
                    return False, "max_drawdown_breached"
                if drawdown >= self.max_drawdown_pct * Decimal("0.66"):
                    logger.info(
                        f"Drawdown warning: {float(drawdown) * 100:.1f}% "
                        f"approaching limit of {float(self.max_drawdown_pct) * 100:.1f}%"
                    )

            if coin in last_trade_timestamps:
                time_since_last = current_time - last_trade_timestamps[coin]
                if time_since_last < self.trade_cooldown_sec:
                    return False, "cooldown_active"

            if daily_notional_used + notional > self.daily_notional_limit_usd:
                return False, "daily_notional_cap_exceeded"

            if volatility_pct and volatility_pct > Decimal("0.02"):
                min_size = self.min_size_by_coin.get(coin, Decimal("0.001"))
                adjusted_size = size * (Decimal("0.02") / volatility_pct)
                if adjusted_size < min_size:
                    return False, "volatility_too_high_for_min_size"
                order["size"] = adjusted_size

        return True, "ok"

    def check_emergency_derisk(self, portfolio: PortfolioState) -> bool:
        return portfolio.margin_usage >= self.emergency_margin_threshold

    def get_emergency_close_coin(self, portfolio: PortfolioState) -> Optional[str]:
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

    def _would_exceed_margin_usage(
        self, coin: str, size: Decimal, price: Decimal, leverage: Decimal, portfolio: PortfolioState
    ) -> bool:
        notional = size * price
        margin_needed = notional / leverage

        existing_margin = Decimal("0")
        if coin in portfolio.positions:
            pos = portfolio.positions[coin]
            # Prefer real margin data from exchange snapshot
            existing_margin = Decimal(str(pos.get("margin_used", "0")))
            if existing_margin <= 0:
                # Fallback if margin_used is unavailable
                existing_size = abs(Decimal(str(pos.get("size", "0"))))
                existing_price = Decimal(str(pos.get("entry_price", price)))
                existing_margin = existing_size * existing_price

        new_margin_usage = (portfolio.margin_usage * portfolio.total_balance + margin_needed - existing_margin) / portfolio.total_balance

        return new_margin_usage > self.max_margin_usage

    def _would_exceed_single_asset_limit(
        self, coin: str, size: Decimal, price: Decimal, leverage: Decimal, portfolio: PortfolioState
    ) -> bool:
        notional = size * price

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