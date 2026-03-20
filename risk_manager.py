</think>

Assistant: The user is getting a syntax error in risk_manager.py. I need to fix the incomplete line. Looking at the code, it seems like the line is cut off. Let me complete the risk_manager.py file properly.<dyad-write path="risk_manager.py" description="Complete the risk_manager.py file with all methods">
import logging
from decimal import Decimal
from typing import Any, Dict, Tuple

from models import PortfolioState, PositionSide, TradingAction
from utils.decimals import safe_decimal

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Validates all trading decisions against risk parameters before execution.
    Handles drawdown protection, margin limits, position conflicts, volatility sizing,
    asset concentration, cooldowns, and daily notional caps.
    """

    def __init__(
        self,
        min_size_by_coin: Dict[str, Decimal],
        hard_max_leverage: Decimal,
        min_confidence_open: Decimal,
        min_confidence_manage: Decimal,
        max_margin_usage: Decimal,
        max_order_margin_pct: Decimal,
        trade_cooldown_sec: int,
        daily_notional_limit_usd: Decimal,
        volatility_multiplier: Decimal = Decimal("1.2"),
        max_drawdown_pct: Decimal = Decimal("0.12"),
        max_single_asset_pct: Decimal = Decimal("0.35"),
        emergency_margin_threshold: Decimal = Decimal("0.88")
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
        self.allowed_actions = {action.value for action in TradingAction}

    def _calculate_volatility_adjusted_size(self, base_size: Decimal, volatility: Decimal) -> Decimal:
        """
        Adjust position size based on market volatility.
        Higher volatility = smaller size to maintain consistent risk per trade.
        """
        if volatility <= 0:
            return base_size
        normal_vol = Decimal("0.005")
        ratio = volatility / normal_vol
        adjustment = Decimal("1") / (Decimal("1") + ((ratio - Decimal("1")) * self.volatility_multiplier))
        adjustment = max(Decimal("0.4"), min(Decimal("1.2"), adjustment))
        return base_size * adjustment

    def _calculate_trend_adjusted_size_and_leverage(
        self,
        base_size: Decimal,
        trend_strength: str,
        trend_direction: str,
        atr_pct: Decimal,
        coin: str
    ) -> Tuple[Decimal, int]:
        """
        Adjust size and leverage based on trend strength and ATR volatility.
        Stronger trends = larger size, higher leverage.
        Higher volatility = smaller size, lower leverage.
        """
        # Trend strength multiplier
        strength_multiplier = {
            "strong": Decimal("1.2"),
            "moderate": Decimal("1.0"),
            "weak": Decimal("0.7")
        }.get(trend_strength, Decimal("1.0"))

        # ATR-based volatility adjustment
        if atr_pct > Decimal("0.02"):  # High volatility
            vol_adjustment = Decimal("0.8")
        elif atr_pct > Decimal("0.01"):  # Medium volatility
            vol_adjustment = Decimal("0.9")
        else:  # Low volatility
            vol_adjustment = Decimal("1.0")

        adjusted_size = base_size * strength_multiplier * vol_adjustment

        # Leverage based on trend strength and coin type
        base_leverage = 3
        if trend_strength == "strong":
            base_leverage = 5
        elif trend_strength == "moderate":
            base_leverage = 4

        # Reduce leverage for volatile coins
        if coin in ["WIF", "PEPE"]:
            base_leverage = min(base_leverage, 2)
        elif coin in ["SOL", "AVAX", "LINK"]:
            base_leverage = min(base_leverage, 3)

        # Reduce leverage for high ATR
        if atr_pct > Decimal("0.015"):
            base_leverage = max(2, base_leverage - 1)

        return adjusted_size, base_leverage

    def check_drawdown(
        self,
        portfolio_state: PortfolioState,
        peak_portfolio_value: Decimal
    ) -> Tuple[bool, str]:
        if peak_portfolio_value <= 0:
            return True, "ok"
        current = portfolio_state.total_balance
        drawdown = (peak_portfolio_value - current) / peak_portfolio_value
        if drawdown >= self.max_drawdown_pct:
            logger.warning(
                f"Max drawdown breached: {float(drawdown) * 100:.1f}% "
                f"(limit={float(self.max_drawdown_pct) * 100:.1f}%)"
            )
            return False, "max_drawdown_breached"
        if drawdown >= self.max_drawdown_pct * Decimal("0.66"):
            logger.info(
                f"Drawdown warning: {float(drawdown) * 100:.1f}% "
                f"approaching limit of {float(self.max_drawdown_pct) * 100:.1f}%"
            )
        return True, "ok"

    def check_emergency_derisk(self, portfolio_state: PortfolioState) -> bool:
        return portfolio_state.margin_usage >= self.emergency_margin_threshold

    def get_emergency_close_coin(self, portfolio_state: PortfolioState) -> str:
        worst_coin = ""
        worst_pnl = Decimal("0")
        for coin, pos in portfolio_state.positions.items():
            pnl = Decimal(str(pos.get("unrealized_pnl", 0)))
            if pnl < worst_pnl:
                worst_pnl = pnl
                worst_coin = coin
        return worst_coin

    def check_order(
        self,
        coin: str,
        order: Dict[str, Any],
        market_price: Decimal,
        portfolio_state: PortfolioState,
        last_trade_timestamp_by_coin: Dict[str, float],
        daily_notional_used: Decimal,
        now_ts: float,
        volatility: Decimal = Decimal("0"),
        peak_portfolio_value: Decimal = Decimal("0"),
        trend_strength: str = "moderate",
        trend_direction: str = "neutral",
        atr_pct: Decimal = Decimal("0")
    ) -> Tuple[bool, str]:
        action = str(order.get("action", "")).strip().lower()
        size = safe_decimal(order.get("size", 0))
        leverage = safe_decimal(order.get("leverage", 1))
        confidence = safe_decimal(order.get("confidence", 0))

        if action not in self.allowed_actions:
            return False, "unknown_action"

        if action == TradingAction.HOLD.value:
            return True, "hold"

        if leverage < Decimal("1") or leverage > self.hard_max_leverage:
            return False, "leverage_out_of_bounds"

        manage_actions = {
            TradingAction.CLOSE_POSITION.value,
            TradingAction.REDUCE_POSITION.value,
            TradingAction.CHANGE_LEVERAGE.value
        }
        open_actions = {
            TradingAction.BUY.value,
            TradingAction.SELL.value,
            TradingAction.INCREASE_POSITION.value
        }

        if action in manage_actions and confidence < self.min_confidence_manage:
            return False, "confidence_manage_too_low"

        if action in open_actions and confidence < self.min_confidence_open:
            return False, "confidence_open_too_low"

        if action in open_actions:
            # Drawdown check
            dd_ok, dd_reason = self.check_drawdown(portfolio_state, peak_portfolio_value)
            if not dd_ok:
                return False, dd_reason

            if portfolio_state.margin_usage > self.max_margin_usage:
                return False, "margin_usage_too_high"

            if market_price <= 0 or size <= 0:
                return False, "invalid_price_or_size"

            # Position conflict detection
            current_side = portfolio_state.get_position_side(coin)
            if action == TradingAction.BUY.value and current_side == PositionSide.SHORT:
                return False, "conflict_buy_while_short"
            if action == TradingAction.SELL.value and current_side == PositionSide.LONG:
                return False, "conflict_sell_while_long"

            # Apply volatility adjustment to size
            adjusted_size = self._calculate_volatility_adjusted_size(size, volatility)

            # Apply trend-based size and leverage adjustment
            final_size, suggested_leverage = self._calculate_trend_adjusted_size_and_leverage(
                adjusted_size, trend_strength, trend_direction, atr_pct, coin
            )

            min_size = self.min_size_by_coin.get(coin, Decimal("0"))
            if final_size < min_size:
                return False, "adjusted_size_below_min"

            required_margin = (final_size * market_price) / suggested_leverage
            max_margin_per_trade = portfolio_state.total_balance * self.max_order_margin_pct
            if required_margin > portfolio_state.available_balance:
                return False, "insufficient_available_balance"
            if required_margin > max_margin_per_trade:
                return False, "per_trade_margin_cap_exceeded"

            # Per-asset concentration limit
            new_notional = final_size * market_price
            existing_notional = Decimal("0")
            if coin in portfolio_state.positions:
                pos = portfolio_state.positions[coin]
                existing_notional = abs(Decimal(str(pos.get("size", 0)))) * Decimal(str(pos.get("entry_price", 0)))
            total_asset_exposure = existing_notional + new_notional
            max_asset_exposure = portfolio_state.total_balance * self.max_single_asset_pct
            if total_asset_exposure > max_asset_exposure:
                return False, "single_asset_concentration_exceeded"

            last_ts = float(last_trade_timestamp_by_coin.get(coin, 0))
            if (now_ts - last_ts) < self.trade_cooldown_sec:
                return False, "cooldown_active"

            projected_daily = daily_notional_used + new_notional
            if projected_daily > self.daily_notional_limit_usd:
                return False, "daily_notional_cap_exceeded"

            # Write adjusted size and leverage back into order so execution uses them
            order["size"] = final_size
            order["leverage"] = suggested_leverage

        return True, "ok"