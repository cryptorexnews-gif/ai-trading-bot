import logging
import time
from decimal import Decimal
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ProtectiveOrdersService:
    """Owns TP/SL exchange sync lifecycle and managed-position protection consistency."""

    def __init__(self, cfg, exchange_client, position_manager, portfolio_service):
        self.cfg = cfg
        self.exchange_client = exchange_client
        self.position_manager = position_manager
        self.portfolio_service = portfolio_service

        self.protective_sync_max_attempts = 12
        self.protective_sync_base_sleep_sec = 1.0
        self.protective_sync_cooldown_sec = 600.0
        self.protective_sync_suppressed_until: Dict[str, float] = {}

    def live_orders_enabled(self) -> bool:
        return self.cfg.execution_mode == "live" and self.cfg.enable_mainnet_trading

    def _is_terminal_protective_sync_reason(self, reason: str) -> bool:
        r = str(reason or "").strip().lower()
        terminal_markers = [
            "exchange_rejected",
            "status_error",
            "not_acknowledged",
            "asset_not_found",
            "invalid_side",
            "invalid_size",
            "invalid_trigger_price",
            "live_disabled_fail_closed",
            "auth_wallet_not_found",
            "master wallet",
            "wallet",
            "does not exist",
        ]
        return any(marker in r for marker in terminal_markers)

    def _is_protective_sync_suppressed(self, coin: str) -> bool:
        until = self.protective_sync_suppressed_until.get(coin, 0.0)
        return time.time() < until

    def _suppress_protective_sync(self, coin: str, reason: str) -> None:
        until = time.time() + self.protective_sync_cooldown_sec
        self.protective_sync_suppressed_until[coin] = until
        logger.error(
            f"{coin} protective sync suppressed for {int(self.protective_sync_cooldown_sec)}s "
            f"due to terminal reason: {reason}"
        )

    def _clear_protective_sync_suppression(self, coin: str) -> None:
        if coin in self.protective_sync_suppressed_until:
            del self.protective_sync_suppressed_until[coin]

    def cancel_exchange_protective_orders(self, coin: str) -> None:
        if not self.live_orders_enabled():
            self.position_manager.clear_protective_order_ids(coin)
            return

        managed = self.position_manager.get_position(coin)
        if not managed:
            return

        if managed.stop_loss_order_id is not None:
            self.exchange_client.cancel_order(coin, managed.stop_loss_order_id)
        if managed.take_profit_order_id is not None:
            self.exchange_client.cancel_order(coin, managed.take_profit_order_id)

        self.position_manager.clear_protective_order_ids(coin)

    def _verify_protective_orders_present(self, coin: str, sl_id: Optional[int], tp_id: Optional[int]) -> bool:
        if sl_id is None or tp_id is None:
            return False

        trading_user = self.exchange_client.get_trading_user_address()
        return self.exchange_client.are_order_ids_open(
            user=trading_user,
            coin=coin,
            order_ids=[sl_id, tp_id],
        )

    def _validate_and_repair_managed_risk(self, coin: str) -> bool:
        managed = self.position_manager.get_position(coin)
        if not managed:
            return False

        changed = False

        if managed.stop_loss.percentage <= 0 or managed.stop_loss.percentage >= 1:
            managed.stop_loss.percentage = self.cfg.trend_sl_pct
            managed.stop_loss.price = None
            changed = True

        if managed.take_profit.percentage <= 0 or managed.take_profit.percentage >= 1:
            managed.take_profit.percentage = self.cfg.trend_tp_pct
            managed.take_profit.price = None
            changed = True

        if managed.entry_price <= 0:
            logger.error(f"{coin} managed entry_price invalid ({managed.entry_price})")
            return False

        sl_price = managed.stop_loss.calculate_stop_price(managed.entry_price, managed.is_long)
        if managed.break_even.activated and managed.stop_loss.price is not None:
            sl_price = managed.stop_loss.price
        tp_price = managed.take_profit.calculate_tp_price(managed.entry_price, managed.is_long)

        if managed.is_long:
            if tp_price <= managed.entry_price:
                managed.take_profit.percentage = self.cfg.trend_tp_pct
                managed.take_profit.price = None
                changed = True
            if sl_price <= 0 or sl_price >= tp_price:
                managed.stop_loss.percentage = self.cfg.trend_sl_pct
                managed.stop_loss.price = None
                managed.break_even.activated = False
                changed = True
        else:
            if tp_price >= managed.entry_price:
                managed.take_profit.percentage = self.cfg.trend_tp_pct
                managed.take_profit.price = None
                changed = True
            if sl_price <= 0 or sl_price <= tp_price:
                managed.stop_loss.percentage = self.cfg.trend_sl_pct
                managed.stop_loss.price = None
                managed.break_even.activated = False
                changed = True

        if changed:
            self.position_manager.clear_protective_order_ids(coin)
            self.position_manager._save_state()
            logger.warning(
                f"{coin} repaired managed SL/TP config: "
                f"sl_pct={managed.stop_loss.percentage}, tp_pct={managed.take_profit.percentage}"
            )

        return True

    def sync_exchange_protective_orders(self, coin: str) -> bool:
        if not self.live_orders_enabled():
            self.position_manager.clear_protective_order_ids(coin)
            return True

        if self._is_protective_sync_suppressed(coin):
            logger.warning(f"{coin} protective sync currently suppressed (cooldown active), skipping")
            return False

        for attempt in range(1, self.protective_sync_max_attempts + 1):
            refreshed_portfolio = self.portfolio_service.get_portfolio_state()
            self.position_manager.sync_with_exchange(refreshed_portfolio.positions)

            if not self._validate_and_repair_managed_risk(coin):
                logger.error(f"{coin} cannot sync TP/SL: invalid managed position state")
                return False

            managed = self.position_manager.get_position(coin)
            if not managed:
                logger.warning(
                    f"{coin} protective sync attempt {attempt}/{self.protective_sync_max_attempts}: "
                    f"position not visible yet on exchange"
                )
                if attempt < self.protective_sync_max_attempts:
                    time.sleep(self.protective_sync_base_sleep_sec)
                    continue
                return False

            sl_price = managed.stop_loss.calculate_stop_price(managed.entry_price, managed.is_long)
            if managed.break_even.activated and managed.stop_loss.price is not None:
                sl_price = managed.stop_loss.price
            tp_price = managed.take_profit.calculate_tp_price(managed.entry_price, managed.is_long)

            result = self.exchange_client.upsert_protective_orders(
                coin=coin,
                position_size=managed.size,
                is_long=managed.is_long,
                stop_loss_price=sl_price,
                take_profit_price=tp_price,
                current_stop_order_id=managed.stop_loss_order_id,
                current_take_profit_order_id=managed.take_profit_order_id,
            )

            if not result.get("success"):
                reason = str(result.get("reason", "unknown"))
                logger.warning(
                    f"{coin} protective sync attempt {attempt}/{self.protective_sync_max_attempts} failed: {reason}"
                )
                if self._is_terminal_protective_sync_reason(reason):
                    self._suppress_protective_sync(coin, reason)
                    return False

                if attempt < self.protective_sync_max_attempts:
                    backoff = self.protective_sync_base_sleep_sec + min(2.0, attempt * 0.15)
                    time.sleep(backoff)
                continue

            sl_id = result.get("stop_loss_order_id")
            tp_id = result.get("take_profit_order_id")

            if not self._verify_protective_orders_present(coin, sl_id, tp_id):
                logger.warning(
                    f"{coin} protective sync attempt {attempt}/{self.protective_sync_max_attempts}: "
                    f"orders not yet confirmed on exchange (sl_id={sl_id}, tp_id={tp_id})"
                )
                if attempt < self.protective_sync_max_attempts:
                    time.sleep(self.protective_sync_base_sleep_sec)
                continue

            self.position_manager.set_protective_order_ids(coin, sl_id, tp_id)
            self._clear_protective_sync_suppression(coin)
            logger.info(f"{coin} protective orders confirmed on exchange: SL oid={sl_id} TP oid={tp_id}")
            return True

        logger.error(f"{coin} failed to confirm TP/SL on exchange after {self.protective_sync_max_attempts} attempts")
        return False

    def update_protection_without_trade(self, coin: str, decision: Dict[str, any]) -> bool:
        sl_pct = decision.get("stop_loss_pct")
        tp_pct = decision.get("take_profit_pct")

        if sl_pct is None and tp_pct is None:
            return False

        changed = self.position_manager.update_position_risk(
            coin=coin,
            sl_pct=sl_pct if isinstance(sl_pct, Decimal) else None,
            tp_pct=tp_pct if isinstance(tp_pct, Decimal) else None,
        )
        if not changed:
            return False

        self.sync_exchange_protective_orders(coin)
        return True

    def ensure_protective_orders_for_open_positions(self, portfolio) -> None:
        if not self.live_orders_enabled():
            return

        for coin, pos in portfolio.positions.items():
            size = Decimal(str(pos.get("size", 0)))
            if size == 0:
                continue

            managed = self.position_manager.get_position(coin)
            if not managed:
                self.position_manager.sync_with_exchange(portfolio.positions)
                managed = self.position_manager.get_position(coin)
                if not managed:
                    logger.error(f"{coin} has exchange position but no managed state; cannot enforce TP/SL")
                    continue

            if not self._validate_and_repair_managed_risk(coin):
                logger.error(f"{coin} managed TP/SL validation failed; skipping sync this pass")
                continue

            if self._is_protective_sync_suppressed(coin):
                logger.warning(f"{coin} protective sync suppressed, skipping enforcement this cycle")
                continue

            sl_id, tp_id = self.position_manager.get_protective_order_ids(coin)
            ids_present = sl_id is not None and tp_id is not None
            ids_confirmed = self._verify_protective_orders_present(coin, sl_id, tp_id) if ids_present else False

            if not ids_present or not ids_confirmed:
                logger.warning(
                    f"{coin} protective orders missing/stale (sl_id={sl_id}, tp_id={tp_id}, confirmed={ids_confirmed}), recreating"
                )
                synced = self.sync_exchange_protective_orders(coin)
                if not synced:
                    logger.error(f"{coin} failed to enforce TP/SL on exchange in this cycle")