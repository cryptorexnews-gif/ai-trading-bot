import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from models import (
    BreakEvenConfig,
    ManagedPosition,
    PortfolioState,
    PositionSide,
    StopLossConfig,
    TakeProfitConfig,
    TrailingStopConfig,
    TradingAction,
)
from utils.file_io import atomic_write_json, read_json_file

logger = logging.getLogger(__name__)

MANAGED_POSITIONS_PATH = "state/managed_positions.json"


class PositionManager:
    """
    Manages positions with stop-loss, take-profit, trailing stop, and break-even.
    Checks positions against current prices and triggers closes when needed.
    Persists managed position state to disk.
    """

    def __init__(
        self,
        default_sl_pct: Decimal = Decimal("0.03"),
        default_tp_pct: Decimal = Decimal("0.05"),
        default_trailing_callback: Decimal = Decimal("0.02"),
        enable_trailing_stop: bool = True,
        trailing_activation_pct: Decimal = Decimal("0.02"),
        break_even_activation_pct: Decimal = Decimal("0.015"),
        break_even_offset_pct: Decimal = Decimal("0.001"),
    ):
        self.default_sl_pct = default_sl_pct
        self.default_tp_pct = default_tp_pct
        self.default_trailing_callback = default_trailing_callback
        self.enable_trailing_stop = enable_trailing_stop
        self.trailing_activation_pct = trailing_activation_pct
        self.break_even_activation_pct = break_even_activation_pct
        self.break_even_offset_pct = break_even_offset_pct
        self._managed: Dict[str, ManagedPosition] = {}
        self._load_state()

    def _load_state(self) -> None:
        """Load managed positions from disk."""
        data = read_json_file(MANAGED_POSITIONS_PATH, default=None)
        if data is None:
            return
        try:
            for coin, pos_data in data.items():
                self._managed[coin] = ManagedPosition.from_dict(pos_data)
            logger.info(f"Loaded {len(self._managed)} managed positions from disk")
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to load managed positions: {e}")

    def _save_state(self) -> None:
        """Persist managed positions to disk atomically with restrictive permissions."""
        data = {coin: pos.to_dict() for coin, pos in self._managed.items()}
        atomic_write_json(MANAGED_POSITIONS_PATH, data)

    def sync_with_exchange(
        self,
        exchange_positions: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        Sync managed positions with actual exchange positions.
        Removes managed entries for positions that no longer exist.
        Updates size and entry_price for existing positions that changed.
        Adds managed entries for new positions found on exchange.
        """
        # Remove managed positions no longer on exchange
        closed_coins = [
            coin for coin in self._managed
            if coin not in exchange_positions
        ]
        for coin in closed_coins:
            logger.info(f"Position {coin} closed on exchange, removing from managed")
            del self._managed[coin]

        # Add or update positions found on exchange
        for coin, pos in exchange_positions.items():
            size = Decimal(str(pos.get("size", 0)))
            if size == 0:
                continue

            entry_price = Decimal(str(pos.get("entry_price", 0)))
            is_long = size > 0

            if coin not in self._managed:
                # New position — create managed entry
                if entry_price <= 0:
                    logger.warning(f"Skipping managed position for {coin}: entry_price={entry_price}")
                    continue

                activation_price = None
                if self.enable_trailing_stop:
                    if is_long:
                        activation_price = entry_price * (Decimal("1") + self.trailing_activation_pct)
                    else:
                        activation_price = entry_price * (Decimal("1") - self.trailing_activation_pct)

                managed = ManagedPosition(
                    coin=coin,
                    size=abs(size),
                    entry_price=entry_price,
                    is_long=is_long,
                    leverage=1,
                    opened_at=time.time(),
                    stop_loss=StopLossConfig(enabled=True, percentage=self.default_sl_pct),
                    take_profit=TakeProfitConfig(enabled=True, percentage=self.default_tp_pct),
                    trailing_stop=TrailingStopConfig(
                        enabled=self.enable_trailing_stop,
                        callback_rate=self.default_trailing_callback,
                        activation_price=activation_price,
                    ),
                    break_even=BreakEvenConfig(
                        enabled=True,
                        activation_pct=self.break_even_activation_pct,
                        offset_pct=self.break_even_offset_pct,
                        activated=False,
                    ),
                )
                self._managed[coin] = managed
                logger.info(
                    f"New managed position: {coin} {'LONG' if is_long else 'SHORT'} "
                    f"entry=${entry_price} SL={float(self.default_sl_pct)*100}% "
                    f"TP={float(self.default_tp_pct)*100}% "
                    f"trailing={'ON' if self.enable_trailing_stop else 'OFF'} "
                    f"break_even=ON@{float(self.break_even_activation_pct)*100}%"
                )
            else:
                # Existing position — update size, entry_price, and direction if changed
                existing = self._managed[coin]
                new_size = abs(size)
                new_is_long = size > 0

                size_changed = new_size != existing.size
                direction_changed = new_is_long != existing.is_long
                entry_changed = entry_price > 0 and entry_price != existing.entry_price

                if direction_changed:
                    # Direction flipped — this shouldn't happen (close first), but handle it
                    logger.warning(f"Position {coin} direction changed, resetting managed state")
                    self.remove_position(coin)
                    # Will be re-added on next sync
                    continue

                if size_changed:
                    existing.size = new_size
                    logger.info(f"Updated {coin} size: {existing.size} -> {new_size}")

                if entry_changed:
                    old_entry = existing.entry_price
                    existing.entry_price = entry_price
                    # Recalculate SL/TP if entry changed and break-even not yet activated
                    if not existing.break_even.activated:
                        existing.stop_loss.price = None  # Reset to percentage-based
                    logger.info(f"Updated {coin} entry: ${old_entry} -> ${entry_price}")

        self._save_state()

    def check_all_positions(
        self,
        current_prices: Dict[str, Decimal]
    ) -> List[Dict[str, Any]]:
        """
        Check all managed positions against current prices.
        Returns list of actions to take (close orders).
        Priority: trailing stop > stop loss > take profit.
        Break-even is handled internally (moves SL, doesn't close).
        """
        actions = []

        for coin, managed in self._managed.items():
            if coin not in current_prices:
                continue

            current_price = current_prices[coin]

            # Guard against zero entry price
            if managed.entry_price <= 0:
                logger.warning(f"Skipping risk check for {coin}: entry_price={managed.entry_price}")
                continue

            # === Break-even check (doesn't close, moves SL) ===
            if managed.check_break_even(current_price):
                be_price = managed.break_even.get_break_even_price(managed.entry_price, managed.is_long)
                logger.info(
                    f"Break-even activated for {coin}: SL moved to ${be_price} "
                    f"(entry=${managed.entry_price}, current=${current_price})"
                )

            # === Trailing stop (highest priority for close) ===
            if managed.should_trailing_stop(current_price):
                ts_price = managed.trailing_stop.get_trailing_stop_price(managed.is_long)
                actions.append({
                    "coin": coin, "trigger": "trailing_stop", "action": "close_position",
                    "size": managed.size, "is_long": managed.is_long,
                    "current_price": current_price, "trigger_price": ts_price,
                    "entry_price": managed.entry_price,
                    "reasoning": f"Trailing stop triggered for {coin}: price=${current_price} hit trailing stop at ${ts_price}"
                })
                continue

            # Update trailing stop extremes even if not triggered
            if managed.trailing_stop.enabled:
                managed.trailing_stop.update_extreme(current_price, managed.is_long)

            # === Stop-loss ===
            if managed.should_stop_loss(current_price):
                sl_price = managed.stop_loss.calculate_stop_price(managed.entry_price, managed.is_long)
                if managed.break_even.activated and managed.stop_loss.price is not None:
                    sl_price = managed.stop_loss.price

                trigger_name = "break_even_stop" if managed.break_even.activated else "stop_loss"
                actions.append({
                    "coin": coin, "trigger": trigger_name, "action": "close_position",
                    "size": managed.size, "is_long": managed.is_long,
                    "current_price": current_price, "trigger_price": sl_price,
                    "entry_price": managed.entry_price,
                    "reasoning": f"{'Break-even stop' if managed.break_even.activated else 'Stop-loss'} triggered for {coin}: price=${current_price} breached SL at ${sl_price}"
                })
                continue

            # === Take-profit ===
            if managed.should_take_profit(current_price):
                tp_price = managed.take_profit.calculate_tp_price(managed.entry_price, managed.is_long)
                actions.append({
                    "coin": coin, "trigger": "take_profit", "action": "close_position",
                    "size": managed.size, "is_long": managed.is_long,
                    "current_price": current_price, "trigger_price": tp_price,
                    "entry_price": managed.entry_price,
                    "reasoning": f"Take-profit triggered for {coin}: price=${current_price} reached TP at ${tp_price}"
                })

        self._save_state()
        return actions

    def register_position(
        self,
        coin: str,
        size: Decimal,
        entry_price: Decimal,
        is_long: bool,
        leverage: int = 1,
        sl_pct: Optional[Decimal] = None,
        tp_pct: Optional[Decimal] = None,
        trailing: Optional[bool] = None,
    ) -> None:
        """Register a new position with risk management."""
        if entry_price <= 0:
            logger.warning(f"Cannot register position for {coin}: entry_price={entry_price}")
            return

        sl_pct = sl_pct or self.default_sl_pct
        tp_pct = tp_pct or self.default_tp_pct
        use_trailing = trailing if trailing is not None else self.enable_trailing_stop

        activation_price = None
        if use_trailing:
            if is_long:
                activation_price = entry_price * (Decimal("1") + self.trailing_activation_pct)
            else:
                activation_price = entry_price * (Decimal("1") - self.trailing_activation_pct)

        self._managed[coin] = ManagedPosition(
            coin=coin, size=abs(size), entry_price=entry_price,
            is_long=is_long, leverage=leverage, opened_at=time.time(),
            stop_loss=StopLossConfig(enabled=True, percentage=sl_pct),
            take_profit=TakeProfitConfig(enabled=True, percentage=tp_pct),
            trailing_stop=TrailingStopConfig(
                enabled=use_trailing, callback_rate=self.default_trailing_callback,
                activation_price=activation_price,
            ),
            break_even=BreakEvenConfig(
                enabled=True, activation_pct=self.break_even_activation_pct,
                offset_pct=self.break_even_offset_pct, activated=False,
            ),
        )
        self._save_state()
        logger.info(
            f"Registered managed position: {coin} {'LONG' if is_long else 'SHORT'} "
            f"size={size} entry=${entry_price} SL={float(sl_pct)*100}% TP={float(tp_pct)*100}% "
            f"BE@{float(self.break_even_activation_pct)*100}%"
        )

    def remove_position(self, coin: str) -> None:
        """Remove a managed position (after close)."""
        if coin in self._managed:
            del self._managed[coin]
            self._save_state()
            logger.info(f"Removed managed position: {coin}")

    def get_managed_positions(self) -> Dict[str, ManagedPosition]:
        return self._managed.copy()

    def get_position_status(self) -> List[Dict[str, Any]]:
        """Get status of all managed positions for dashboard."""
        statuses = []
        for coin, pos in self._managed.items():
            sl_price = pos.stop_loss.calculate_stop_price(pos.entry_price, pos.is_long)
            if pos.break_even.activated and pos.stop_loss.price is not None:
                sl_price = pos.stop_loss.price
            tp_price = pos.take_profit.calculate_tp_price(pos.entry_price, pos.is_long)
            ts_price = pos.trailing_stop.get_trailing_stop_price(pos.is_long)

            statuses.append({
                "coin": coin,
                "side": "LONG" if pos.is_long else "SHORT",
                "size": str(pos.size),
                "entry_price": str(pos.entry_price),
                "stop_loss_price": str(sl_price),
                "stop_loss_pct": str(pos.stop_loss.percentage),
                "take_profit_price": str(tp_price),
                "take_profit_pct": str(pos.take_profit.percentage),
                "trailing_stop_price": str(ts_price) if ts_price else None,
                "trailing_enabled": pos.trailing_stop.enabled,
                "trailing_callback": str(pos.trailing_stop.callback_rate),
                "highest_tracked": str(pos.trailing_stop.highest_price) if pos.trailing_stop.highest_price else None,
                "lowest_tracked": str(pos.trailing_stop.lowest_price) if pos.trailing_stop.lowest_price else None,
                "break_even_activated": pos.break_even.activated,
                "break_even_activation_pct": str(pos.break_even.activation_pct),
                "opened_at": pos.opened_at,
            })
        return statuses