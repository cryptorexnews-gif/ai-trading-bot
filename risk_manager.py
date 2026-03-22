import logging
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from models import PortfolioState, TradingAction

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Risk manager con controlli operativi essenziali:
    - validazione azioni/size/leverage
    - soglie confidenza open/manage
    - drawdown, margin usage, cap margine ordine
    - cooldown per coin
    - cap notionale giornaliero
    - conflitti direzione posizione
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
        action = str(order.get("action", "")).strip().lower()
        raw_size = Decimal(str(order.get("size", 0)))
        leverage = Decimal(str(order.get("leverage", 1)))
        confidence = Decimal(str(order.get("confidence", 0)))

        valid_actions = {a.value for a in TradingAction}
        if action not in valid_actions:
            return False, "unknown_action"

        if action == TradingAction.HOLD.value:
            return True, "hold"

        if leverage < 1 or leverage > self.hard_max_leverage:
            return False, "leverage_out_of_bounds"

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

        if action in open_actions and confidence < self.min_confidence_open:
            return False, "confidence_open_too_low"
        if action in manage_actions and confidence < self.min_confidence_manage:
            return False, "confidence_manage_too_low"

        existing_size = Decimal("0")
        if coin in portfolio.positions:
            existing_size = Decimal(str(portfolio.positions[coin].get("size", 0)))

        if action == TradingAction.CHANGE_LEVERAGE.value:
            if existing_size == 0:
                return False, "no_position_for_leverage_change"
            return True, "ok"

        if action == TradingAction.CLOSE_POSITION.value:
            if existing_size == 0:
                return False, "no_position_to_close"
            requested = abs(raw_size)
            order["size"] = abs(existing_size) if requested <= 0 else min(requested, abs(existing_size))
            return True, "ok"

        if action == TradingAction.REDUCE_POSITION.value:
            if existing_size == 0:
                return False, "no_position_to_reduce"
            if raw_size <= 0:
                return False, "size_zero_or_negative"
            order["size"] = min(abs(raw_size), abs(existing_size))
            return True, "ok"

        if raw_size <= 0:
            return False, "size_zero_or_negative"

        size = abs(raw_size)
        min_size = self.min_size_by_coin.get(coin, Decimal("0"))
        if size < min_size:
            return False, "size_below_min"

        if action in {TradingAction.BUY.value, TradingAction.INCREASE_POSITION.value} and existing_size < 0:
            return False, "conflict_buy_while_short"
        if action == TradingAction.SELL.value and existing_size > 0:
            return False, "conflict_sell_while_long"

        if peak_portfolio_value is not None and peak_portfolio_value > 0:
            drawdown = (peak_portfolio_value - portfolio.total_balance) / peak_portfolio_value
            if drawdown > self.max_drawdown_pct:
                return False, "max_drawdown_breached"

        if portfolio.margin_usage > self.max_margin_usage:
            return False, "margin_usage_too_high"

        last_ts = last_trade_timestamps.get(coin)
        if last_ts is not None:
            elapsed = current_time - float(last_ts)
            if elapsed < self.trade_cooldown_sec:
                return False, "cooldown_active"

        order_notional = size * current_price
        if self.max_order_notional_usd > 0 and order_notional > self.max_order_notional_usd:
            return False, "order_notional_cap_exceeded"

        if self.daily_notional_limit_usd > 0 and (daily_notional_used + order_notional) > self.daily_notional_limit_usd:
            return False, "daily_notional_cap_exceeded"

        margin_required = order_notional / leverage if leverage > 0 else Decimal("0")
        if margin_required > portfolio.available_balance:
            return False, "insufficient_available_balance"

        max_order_margin = portfolio.total_balance * self.max_order_margin_pct
        if margin_required > max_order_margin:
            return False, "order_margin_pct_exceeded"

        order["size"] = size
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