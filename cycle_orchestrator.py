"""
CycleOrchestrator — runs a single trading cycle through clear phases:
  1. Health check
  2. Portfolio snapshot + equity recording
  3. SL/TP/Trailing/Break-even checks
  4. Emergency de-risk
  5. Correlation analysis
  6. Per-coin analysis + LLM decision + risk check + execution
  7. State persistence

Optimized for 4h/1d trend trading strategy.
"""

import logging
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from bot_live_writer import write_live_status
from config.bot_config import BotConfig
from correlation_engine import CorrelationEngine
from exchange_client import HyperliquidExchangeClient
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import PortfolioState
from notifier import Notifier
from orchestration.coin_cycle_processor import CoinCycleProcessor
from order_verifier import OrderVerifier
from portfolio_service import PortfolioService
from position_manager import PositionManager
from risk_manager import RiskManager
from state_store import StateStore
from technical_analyzer_simple import technical_fetcher
from utils.health import HealthMonitor, HealthStatus
from utils.metrics import MetricsCollector
from utils.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class CycleOrchestrator:
    """Orchestrates a single trading cycle through well-defined phases."""

    def __init__(
        self,
        cfg: BotConfig,
        exchange_client: HyperliquidExchangeClient,
        execution_engine: ExecutionEngine,
        risk_manager: RiskManager,
        state_store: StateStore,
        metrics: MetricsCollector,
        position_manager: PositionManager,
        correlation_engine: CorrelationEngine,
        order_verifier: OrderVerifier,
        notifier: Notifier,
        health_monitor: HealthMonitor,
        portfolio_service: PortfolioService,
        llm_engine: Optional[LLMEngine],
        hl_rate_limiter: TokenBucketRateLimiter,
        llm_rate_limiter: TokenBucketRateLimiter,
        trading_pairs: List[str],
    ):
        self.cfg = cfg
        self.exchange_client = exchange_client
        self.execution_engine = execution_engine
        self.risk_manager = risk_manager
        self.state_store = state_store
        self.metrics = metrics
        self.position_manager = position_manager
        self.correlation_engine = correlation_engine
        self.order_verifier = order_verifier
        self.notifier = notifier
        self.health_monitor = health_monitor
        self.portfolio_service = portfolio_service
        self.llm_engine = llm_engine
        self.hl_rate_limiter = hl_rate_limiter
        self.llm_rate_limiter = llm_rate_limiter
        self.trading_pairs = trading_pairs
        self._cycle_count: int = 0

        self._protective_sync_max_attempts = 12
        self._protective_sync_base_sleep_sec = 1.0
        self._protective_sync_cooldown_sec = 600.0  # anti-loop per errori terminali
        self._protective_sync_suppressed_until: Dict[str, float] = {}

        self._trigger_close_max_attempts = 8
        self._trigger_close_base_sleep_sec = 1.0

        self.coin_processor = CoinCycleProcessor(
            cfg=self.cfg,
            execution_engine=self.execution_engine,
            risk_manager=self.risk_manager,
            state_store=self.state_store,
            metrics=self.metrics,
            position_manager=self.position_manager,
            correlation_engine=self.correlation_engine,
            order_verifier=self.order_verifier,
            notifier=self.notifier,
            portfolio_service=self.portfolio_service,
            llm_engine=self.llm_engine,
            hl_rate_limiter=self.hl_rate_limiter,
            llm_rate_limiter=self.llm_rate_limiter,
            update_protection_without_trade=self._update_protection_without_trade,
            sync_exchange_protective_orders=self._sync_exchange_protective_orders,
            cancel_exchange_protective_orders=self._cancel_exchange_protective_orders,
        )

    def set_cycle_count(self, count: int) -> None:
        """Set current cycle count for live status updates."""
        self._cycle_count = count

    # ─── Helpers: on-exchange protection ──────────────────────────────────

    def _live_orders_enabled(self) -> bool:
        return self.cfg.execution_mode == "live" and self.cfg.enable_mainnet_trading

    def _is_terminal_protective_sync_reason(self, reason: str) -> bool:
        """
        Errori terminali: non migliorano con retry immediato e causano loop ordini.
        """
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
        until = self._protective_sync_suppressed_until.get(coin, 0.0)
        return time.time() < until

    def _suppress_protective_sync(self, coin: str, reason: str) -> None:
        until = time.time() + self._protective_sync_cooldown_sec
        self._protective_sync_suppressed_until[coin] = until
        logger.error(
            f"{coin} protective sync suppressed for {int(self._protective_sync_cooldown_sec)}s "
            f"due to terminal reason: {reason}"
        )

    def _clear_protective_sync_suppression(self, coin: str) -> None:
        if coin in self._protective_sync_suppressed_until:
            del self._protective_sync_suppressed_until[coin]

    def _cancel_exchange_protective_orders(self, coin: str) -> None:
        if not self._live_orders_enabled():
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
        return self.exchange_client.are_order_ids_open(
            user=self.cfg.wallet_address,
            coin=coin,
            order_ids=[sl_id, tp_id],
        )

    def _sync_exchange_protective_orders(self, coin: str) -> bool:
        if not self._live_orders_enabled():
            self.position_manager.clear_protective_order_ids(coin)
            return True

        if self._is_protective_sync_suppressed(coin):
            logger.warning(f"{coin} protective sync currently suppressed (cooldown active), skipping")
            return False

        max_attempts = self._protective_sync_max_attempts
        for attempt in range(1, max_attempts + 1):
            refreshed_portfolio = self.portfolio_service.get_portfolio_state()
            self.position_manager.sync_with_exchange(refreshed_portfolio.positions)

            managed = self.position_manager.get_position(coin)
            if not managed:
                logger.warning(
                    f"{coin} protective sync attempt {attempt}/{max_attempts}: "
                    f"position not visible yet on exchange"
                )
                if attempt < max_attempts:
                    time.sleep(self._protective_sync_base_sleep_sec)
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
                    f"{coin} protective sync attempt {attempt}/{max_attempts} failed: {reason}"
                )

                if self._is_terminal_protective_sync_reason(reason):
                    self._suppress_protective_sync(coin, reason)
                    return False

                if attempt < max_attempts:
                    backoff = self._protective_sync_base_sleep_sec + min(2.0, attempt * 0.15)
                    time.sleep(backoff)
                continue

            sl_id = result.get("stop_loss_order_id")
            tp_id = result.get("take_profit_order_id")

            if not self._verify_protective_orders_present(coin, sl_id, tp_id):
                logger.warning(
                    f"{coin} protective sync attempt {attempt}/{max_attempts}: "
                    f"orders not yet confirmed on exchange (sl_id={sl_id}, tp_id={tp_id})"
                )
                if attempt < max_attempts:
                    time.sleep(self._protective_sync_base_sleep_sec)
                continue

            self.position_manager.set_protective_order_ids(coin, sl_id, tp_id)
            self._clear_protective_sync_suppression(coin)
            logger.info(
                f"{coin} protective orders confirmed on exchange: "
                f"SL oid={sl_id} TP oid={tp_id}"
            )
            return True

        logger.error(f"{coin} failed to confirm TP/SL on exchange after {max_attempts} attempts")
        return False

    def _execute_trigger_close_with_retries(
        self,
        coin: str,
        side: str,
        close_size: Decimal,
        current_price: Decimal,
        trigger: str,
        previous_size: Decimal,
    ) -> Tuple[bool, Dict[str, Any]]:
        last_result: Dict[str, Any] = {"success": False, "reason": "not_executed"}

        for attempt in range(1, self._trigger_close_max_attempts + 1):
            self.hl_rate_limiter.acquire(1)
            result = self.exchange_client.place_order(
                coin=coin,
                side=side,
                size=close_size,
                desired_price=current_price,
                reduce_only=True,
            )
            last_result = result if isinstance(result, dict) else {"success": False, "reason": "invalid_result"}

            if not last_result.get("success"):
                logger.warning(
                    f"{trigger.upper()} close attempt {attempt}/{self._trigger_close_max_attempts} failed for {coin}: "
                    f"{last_result.get('reason', 'unknown')}"
                )
                if attempt < self._trigger_close_max_attempts:
                    backoff = self._trigger_close_base_sleep_sec + min(2.0, attempt * 0.2)
                    time.sleep(backoff)
                continue

            refreshed = self.portfolio_service.get_portfolio_state()
            new_size = Decimal(str(refreshed.positions.get(coin, {}).get("size", 0)))

            if abs(new_size) < abs(previous_size):
                logger.info(
                    f"{trigger.upper()} close confirmed on exchange for {coin}: "
                    f"size {previous_size} -> {new_size}"
                )
                return True, last_result

            logger.warning(
                f"{trigger.upper()} close attempt {attempt}/{self._trigger_close_max_attempts} not reflected yet on exchange for {coin} "
                f"(expected reduction from {previous_size}, got {new_size})"
            )
            if attempt < self._trigger_close_max_attempts:
                time.sleep(self._trigger_close_base_sleep_sec)

        return False, last_result

    def _update_protection_without_trade(self, coin: str, decision: Dict[str, Any]) -> bool:
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

        self._sync_exchange_protective_orders(coin)
        return True

    # ─── Phase 1: Health Check ────────────────────────────────────────────

    def _run_health_check(self, cycle_count: int) -> None:
        """Run health checks every 10 cycles."""
        if cycle_count % 10 != 1:
            return
        health_result = self.health_monitor.run_all_checks()
        if health_result["status"] == HealthStatus.UNHEALTHY:
            logger.error(f"Health check UNHEALTHY: {health_result}")
            self.notifier.notify_error(f"Health check unhealthy: {health_result['summary']}")
        elif health_result["status"] == HealthStatus.DEGRADED:
            logger.warning(f"Health check DEGRADED: {health_result['summary']}")

    # ─── Phase 2: Portfolio Snapshot ──────────────────────────────────────

    def _fetch_portfolio(self) -> PortfolioState:
        """Fetch portfolio and update metrics."""
        self.hl_rate_limiter.acquire(1)
        portfolio = self.portfolio_service.get_portfolio_state()
        self.metrics.set_gauge("current_balance", portfolio.total_balance)
        self.metrics.set_gauge("available_balance", portfolio.available_balance)
        self.metrics.set_gauge("margin_usage", portfolio.margin_usage)
        self.metrics.set_gauge("open_positions_count", len(portfolio.positions))
        logger.info(
            f"Portfolio: balance=${portfolio.total_balance}, "
            f"available=${portfolio.available_balance}, "
            f"margin_usage={float(portfolio.margin_usage) * 100:.1f}%, "
            f"positions={len(portfolio.positions)}, "
            f"unrealized_pnl=${portfolio.get_total_unrealized_pnl()}"
        )
        return portfolio

    # ─── Phase 3: SL/TP/Trailing/Break-Even ───────────────────────────────

    def _process_risk_triggers(self, portfolio: PortfolioState) -> int:
        """Check and execute SL/TP/trailing/break-even triggers."""
        self.position_manager.sync_with_exchange(portfolio.positions)
        self._ensure_protective_orders_for_open_positions(portfolio)

        mids = technical_fetcher.get_all_mids()
        if not mids:
            return 0

        current_prices: Dict[str, Decimal] = {}
        for coin in portfolio.positions:
            if coin in mids:
                current_prices[coin] = Decimal(str(mids[coin]))

        actions = self.position_manager.check_all_positions(current_prices)
        triggered = 0

        for action_info in actions:
            coin = action_info["coin"]
            trigger = action_info["trigger"]
            current_price = action_info["current_price"]
            trigger_price = action_info.get("trigger_price", Decimal("0"))
            entry_price = action_info.get("entry_price", Decimal("0"))

            logger.warning(
                f"{trigger.upper()} triggered for {coin}: "
                f"entry=${entry_price}, current=${current_price}, trigger=${trigger_price}"
            )

            pos_size = Decimal(str(portfolio.positions[coin]["size"]))
            side = "sell" if pos_size > 0 else "buy"
            close_size = abs(pos_size)

            close_ok, result = self._execute_trigger_close_with_retries(
                coin=coin,
                side=side,
                close_size=close_size,
                current_price=current_price,
                trigger=trigger,
                previous_size=pos_size,
            )

            if close_ok:
                triggered += 1
                self._cancel_exchange_protective_orders(coin)
                self.position_manager.remove_position(coin)
                self._send_trigger_notification(trigger, coin, entry_price, trigger_price, current_price)
                self._record_trigger_trade(coin, close_size, current_price, result, action_info, trigger)
                self.metrics.increment("trades_executed_total")
                logger.info(f"{trigger.upper()} close executed for {coin}")
            else:
                logger.error(f"Failed to execute {trigger} close for {coin} after retries: {result}")

        return triggered

    def _send_trigger_notification(
        self, trigger: str, coin: str,
        entry_price: Decimal, trigger_price: Decimal, current_price: Decimal
    ) -> None:
        if trigger == "stop_loss" or trigger == "break_even_stop":
            self.notifier.notify_stop_loss(coin, entry_price, trigger_price, current_price)
        elif trigger == "take_profit":
            self.notifier.notify_take_profit(coin, entry_price, trigger_price, current_price)
        elif trigger == "trailing_stop":
            self.notifier.notify_trailing_stop(coin, entry_price, trigger_price, current_price)

    def _record_trigger_trade(
        self, coin: str, close_size: Decimal, current_price: Decimal,
        result: Dict[str, Any], action_info: Dict[str, Any], trigger: str
    ) -> None:
        state = self.state_store.load_state()
        trade_record = {
            "timestamp": time.time(),
            "coin": coin,
            "action": "close_position",
            "size": str(close_size),
            "price": str(current_price),
            "notional": str(result.get("notional", "0")),
            "leverage": 1,
            "confidence": 1.0,
            "reasoning": action_info.get("reasoning", ""),
            "success": True,
            "mode": self.cfg.execution_mode,
            "trigger": trigger,
            "order_status": "filled",
        }
        self.state_store.add_trade_record(state, trade_record)
        self.state_store.save_state(state)

    # ─── Phase 4: Emergency De-Risk ───────────────────────────────────────

    def _handle_emergency_derisk(self, portfolio: PortfolioState) -> PortfolioState:
        """Close worst-performing position if margin usage is critical. Returns updated portfolio."""
        if not self.risk_manager.check_emergency_derisk(portfolio):
            return portfolio

        worst_coin = self.risk_manager.get_emergency_close_coin(portfolio)
        if not worst_coin:
            logger.warning("Emergency derisk: no position to close")
            return portfolio

        logger.warning(f"EMERGENCY DERISK: closing {worst_coin}")
        self.notifier.notify_emergency_derisk(worst_coin, "margin_usage_critical")

        pos_size = Decimal(str(portfolio.positions[worst_coin]["size"]))
        side = "sell" if pos_size > 0 else "buy"
        close_size = abs(pos_size)
        mids = technical_fetcher.get_all_mids()
        current_price = Decimal(str(mids.get(worst_coin, "0"))) if mids and worst_coin in mids else Decimal("0")

        if current_price > 0:
            close_ok, result = self._execute_trigger_close_with_retries(
                coin=worst_coin,
                side=side,
                close_size=close_size,
                current_price=current_price,
                trigger="emergency",
                previous_size=pos_size,
            )
            if close_ok:
                self._cancel_exchange_protective_orders(worst_coin)
                self.position_manager.remove_position(worst_coin)
                logger.info(f"Emergency close executed for {worst_coin}")
                state = self.state_store.load_state()
                trade_record = {
                    "timestamp": time.time(),
                    "coin": worst_coin,
                    "action": "close_position",
                    "size": str(close_size),
                    "price": str(current_price),
                    "notional": str(result.get("notional", "0")),
                    "leverage": 1,
                    "confidence": 1.0,
                    "reasoning": "Emergency derisk: margin usage critical",
                    "success": True,
                    "mode": self.cfg.execution_mode,
                    "trigger": "emergency",
                    "order_status": "filled",
                }
                self.state_store.add_trade_record(state, trade_record)
                self.state_store.save_state(state)
                return self._fetch_portfolio()
            logger.error(f"Emergency close FAILED for {worst_coin} after retries: {result}")

        return portfolio

    # ─── Phase 5: Per-Coin Analysis & Execution ──────────────────────────

    def _analyze_and_trade(
        self,
        portfolio: PortfolioState,
        state: Dict[str, Any],
        daily_notional_used: Decimal,
        peak: Decimal,
        consecutive_losses: int,
        shutdown_requested: bool,
    ) -> Tuple[int, Decimal]:
        """Analyze each coin and execute trades. Returns (trades_executed, notional_added_this_cycle)."""
        correlations = self.correlation_engine.calculate_correlations(self.trading_pairs, "1h", 50)
        corr_summary = self.correlation_engine.get_correlation_summary(correlations)
        if corr_summary["high_correlation_pairs"]:
            logger.info(f"High correlation pairs: {corr_summary['high_correlation_pairs'][:5]}")

        all_mids = technical_fetcher.get_all_mids()
        recent_trades = self.state_store.get_recent_trades(state, count=5)
        trades_executed = 0
        notional_added = Decimal("0")

        for coin in self.trading_pairs:
            if shutdown_requested:
                logger.info("Shutdown requested, stopping coin analysis")
                break
            if trades_executed >= self.cfg.max_trades_per_cycle:
                logger.info(f"Max trades per cycle ({self.cfg.max_trades_per_cycle}) reached")
                break

            logger.info(f"--- Analyzing {coin} ---")
            write_live_status(
                is_running=True,
                execution_mode=self.cfg.execution_mode,
                cycle_count=self._cycle_count,
                last_cycle_duration=0,
                portfolio=portfolio,
                current_coin=coin,
            )

            result = self.coin_processor.process_single_coin(
                coin=coin,
                portfolio=portfolio,
                state=state,
                daily_notional_used=daily_notional_used + notional_added,
                peak=peak,
                consecutive_losses=consecutive_losses,
                all_mids=all_mids,
                recent_trades=recent_trades,
                correlations=correlations,
            )

            if result is not None:
                trades_executed += result["trades"]
                notional_added += result["notional"]
                if result["trades"] > 0:
                    state["consecutive_losses"] = 0
                elif result.get("failed"):
                    state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1

        return trades_executed, notional_added

    def _ensure_protective_orders_for_open_positions(self, portfolio: PortfolioState) -> None:
        """
        Ensure every managed open position has TP/SL order ids and that they truly exist on Hyperliquid.
        If missing or stale, force recreate/sync.
        """
        if not self._live_orders_enabled():
            return

        for coin, pos in portfolio.positions.items():
            size = Decimal(str(pos.get("size", 0)))
            if size == 0:
                continue

            managed = self.position_manager.get_position(coin)
            if not managed:
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
                synced = self._sync_exchange_protective_orders(coin)
                if not synced:
                    logger.error(f"{coin} failed to enforce TP/SL on exchange in this cycle")