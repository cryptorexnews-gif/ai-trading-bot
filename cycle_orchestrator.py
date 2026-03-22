"""
CycleOrchestrator — runs a single trading cycle through clear phases:
  1. Health check
  2. Portfolio snapshot + equity recording
  3. SL/TP/Trailing/Break-even checks
  4. Emergency de-risk
  5. Correlation analysis
  6. Per-coin analysis + LLM decision + risk check + execution
  7. State persistence
"""

import logging
from decimal import Decimal
from typing import Dict, List, Tuple

from orchestration.coin_cycle_processor import CoinCycleProcessor, CoinProcessingContext
from orchestration.coin_scheduler import CoinScheduler
from orchestration.emergency_derisk_service import EmergencyDeriskService
from orchestration.protective_orders_service import ProtectiveOrdersService
from orchestration.risk_trigger_service import RiskTriggerService
from utils.health import HealthStatus

logger = logging.getLogger(__name__)


class CycleOrchestrator:
    """Orchestrates a single trading cycle through well-defined phases."""

    def __init__(
        self,
        cfg,
        exchange_client,
        execution_engine,
        risk_manager,
        state_store,
        metrics,
        position_manager,
        correlation_engine,
        order_verifier,
        notifier,
        health_monitor,
        portfolio_service,
        llm_engine,
        hl_rate_limiter,
        llm_rate_limiter,
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

        self.protective_orders_service = ProtectiveOrdersService(
            cfg=self.cfg,
            exchange_client=self.exchange_client,
            position_manager=self.position_manager,
            portfolio_service=self.portfolio_service,
        )

        self.risk_trigger_service = RiskTriggerService(
            cfg=self.cfg,
            hl_rate_limiter=self.hl_rate_limiter,
            exchange_client=self.exchange_client,
            portfolio_service=self.portfolio_service,
            position_manager=self.position_manager,
            notifier=self.notifier,
            metrics=self.metrics,
            state_store=self.state_store,
            protective_orders_service=self.protective_orders_service,
        )

        self.emergency_derisk_service = EmergencyDeriskService(
            notifier=self.notifier,
            risk_manager=self.risk_manager,
            position_manager=self.position_manager,
            protective_orders_service=self.protective_orders_service,
            risk_trigger_service=self.risk_trigger_service,
            portfolio_service=self.portfolio_service,
            state_store=self.state_store,
            metrics=self.metrics,
            cfg=self.cfg,
        )

        coin_context = CoinProcessingContext(
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
            update_protection_without_trade=self.update_protection_without_trade,
            sync_exchange_protective_orders=self.sync_exchange_protective_orders,
            cancel_exchange_protective_orders=self.cancel_exchange_protective_orders,
        )

        self.coin_processor = CoinCycleProcessor(context=coin_context)

        self.coin_scheduler = CoinScheduler(
            correlation_engine=self.correlation_engine,
            coin_processor=self.coin_processor,
        )

    def set_cycle_count(self, count: int) -> None:
        self._cycle_count = count

    def run_health_check(self, cycle_count: int) -> None:
        if cycle_count % 10 != 1:
            return
        health_result = self.health_monitor.run_all_checks()
        if health_result["status"] == HealthStatus.UNHEALTHY:
            logger.error(f"Health check UNHEALTHY: {health_result}")
            self.notifier.notify_error(f"Health check unhealthy: {health_result['summary']}")
        elif health_result["status"] == HealthStatus.DEGRADED:
            logger.warning(f"Health check DEGRADED: {health_result['summary']}")

    def fetch_portfolio(self):
        self.hl_rate_limiter.acquire(1)
        portfolio = self.portfolio_service.get_portfolio_state()
        self.metrics.set_gauge("current_balance", portfolio.total_balance)
        self.metrics.set_gauge("available_balance", portfolio.available_balance)
        self.metrics.set_gauge("margin_usage", portfolio.margin_usage)
        self.metrics.set_gauge("open_positions_count", len(portfolio.positions))
        logger.info(
            f"Portfolio: balance={portfolio.total_balance}, "
            f"available={portfolio.available_balance}, "
            f"margin_usage={portfolio.margin_usage}, "
            f"positions={len(portfolio.positions)}, "
            f"unrealized_pnl={portfolio.get_total_unrealized_pnl()}"
        )
        return portfolio

    def process_risk_triggers(self, portfolio) -> int:
        return self.risk_trigger_service.process_risk_triggers(portfolio)

    def handle_emergency_derisk(self, portfolio):
        return self.emergency_derisk_service.handle_emergency_derisk(portfolio)

    def analyze_and_trade(
        self,
        portfolio,
        state: Dict,
        daily_notional_used: Decimal,
        peak: Decimal,
        consecutive_losses: int,
        shutdown_requested: bool,
    ) -> Tuple[int, Decimal]:
        return self.coin_scheduler.analyze_and_trade(
            trading_pairs=self.trading_pairs,
            cycle_count=self._cycle_count,
            execution_mode=self.cfg.execution_mode,
            portfolio=portfolio,
            state=state,
            daily_notional_used=daily_notional_used,
            peak=peak,
            consecutive_losses=consecutive_losses,
            shutdown_requested=shutdown_requested,
        )

    def sync_exchange_protective_orders(self, coin: str) -> bool:
        return self.protective_orders_service.sync_exchange_protective_orders(coin)

    def cancel_exchange_protective_orders(self, coin: str) -> None:
        self.protective_orders_service.cancel_exchange_protective_orders(coin)

    def update_protection_without_trade(self, coin: str, decision: Dict) -> bool:
        return self.protective_orders_service.update_protection_without_trade(coin, decision)

    # Compatibility wrappers (legacy callers)
    def _run_health_check(self, cycle_count: int) -> None:
        self.run_health_check(cycle_count)

    def _fetch_portfolio(self):
        return self.fetch_portfolio()

    def _process_risk_triggers(self, portfolio) -> int:
        return self.process_risk_triggers(portfolio)

    def _handle_emergency_derisk(self, portfolio):
        return self.handle_emergency_derisk(portfolio)

    def _analyze_and_trade(
        self,
        portfolio,
        state: Dict,
        daily_notional_used: Decimal,
        peak: Decimal,
        consecutive_losses: int,
        shutdown_requested: bool,
    ) -> Tuple[int, Decimal]:
        return self.analyze_and_trade(
            portfolio=portfolio,
            state=state,
            daily_notional_used=daily_notional_used,
            peak=peak,
            consecutive_losses=consecutive_losses,
            shutdown_requested=shutdown_requested,
        )

    def _sync_exchange_protective_orders(self, coin: str) -> bool:
        return self.sync_exchange_protective_orders(coin)

    def _cancel_exchange_protective_orders(self, coin: str) -> None:
        self.cancel_exchange_protective_orders(coin)

    def _update_protection_without_trade(self, coin: str, decision: Dict) -> bool:
        return self.update_protection_without_trade(coin, decision)