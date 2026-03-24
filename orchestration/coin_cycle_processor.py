import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from config.bot_config import BotConfig
from correlation_engine import CorrelationEngine
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from notifier import Notifier
from orchestration.coin_processing_utils import log_coin_indicators
from orchestration.contracts import TradeDecision
from orchestration.decision_service import get_decision_for_coin
from orchestration.execution_flow_service import execute_and_verify_trade
from orchestration.execution_result_service import build_trade_record
from orchestration.market_data_service import build_market_data
from orchestration.post_trade_service import handle_successful_execution
from orchestration.risk_gate_service import evaluate_trade_gates
from order_verifier import OrderVerifier
from portfolio_service import PortfolioService
from position_manager import PositionManager
from risk_manager import RiskManager
from state_store import StateStore
from technical_analyzer_simple import technical_fetcher
from utils.metrics import MetricsCollector
from utils.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


@dataclass
class CoinProcessingContext:
    cfg: BotConfig
    execution_engine: ExecutionEngine
    risk_manager: RiskManager
    state_store: StateStore
    metrics: MetricsCollector
    position_manager: PositionManager
    correlation_engine: CorrelationEngine
    order_verifier: OrderVerifier
    notifier: Notifier
    portfolio_service: PortfolioService
    llm_engine: Optional[LLMEngine]
    hl_rate_limiter: TokenBucketRateLimiter
    llm_rate_limiter: TokenBucketRateLimiter
    update_protection_without_trade: Callable[[str, Dict], bool]
    sync_exchange_protective_orders: Callable[[str], bool]
    cancel_exchange_protective_orders: Callable[[str], None]


class CoinCycleProcessor:
    """Gestisce l'intero flusso per singola coin: dati → decisione → risk → esecuzione."""

    def __init__(self, context: CoinProcessingContext):
        self.context = context
        self._dynamic_min_sizes: Dict[str, Decimal] = {}

    @property
    def cfg(self) -> BotConfig:
        return self.context.cfg

    @property
    def state_store(self) -> StateStore:
        return self.context.state_store

    @property
    def metrics(self) -> MetricsCollector:
        return self.context.metrics

    @property
    def position_manager(self) -> PositionManager:
        return self.context.position_manager

    @property
    def portfolio_service(self) -> PortfolioService:
        return self.context.portfolio_service

    def process_single_coin(
        self,
        coin: str,
        portfolio,
        state: Dict[str, any],
        daily_notional_used: Decimal,
        peak: Decimal,
        consecutive_losses: int,
        all_mids: Optional[Dict[str, str]],
        recent_trades: List[Dict[str, any]],
        correlations: Dict[str, Dict[str, Decimal]],
    ) -> Optional[Dict[str, any]]:
        self.context.hl_rate_limiter.acquire(3)
        tech_data = technical_fetcher.get_technical_indicators(coin)
        if not tech_data:
            logger.warning(f"Skipping {coin}: no market data")
            return None

        market_data = build_market_data(coin=coin, technical_data=tech_data)
        log_coin_indicators(coin, market_data, tech_data)

        funding_data = technical_fetcher.get_funding_for_coin(coin)
        decision = get_decision_for_coin(
            coin=coin,
            market_data=market_data,
            portfolio=portfolio,
            tech_data=tech_data,
            all_mids=all_mids,
            funding_data=funding_data,
            recent_trades=recent_trades,
            peak=peak,
            consecutive_losses=consecutive_losses,
            llm_engine=self.context.llm_engine,
            llm_rate_limiter=self.context.llm_rate_limiter,
            metrics=self.context.metrics,
            position_manager=self.context.position_manager,
            exchange_client=self.context.execution_engine.exchange_client,
            sync_exchange_protective_orders=self.context.sync_exchange_protective_orders,
            logger=logger,
            cfg=self.context.cfg,
        )

        logger.info(
            f"{coin} decision: action={decision.action}, size={decision.size}, "
            f"leverage={decision.leverage}, confidence={decision.confidence}, "
            f"sl_pct={decision.stop_loss_pct}, tp_pct={decision.take_profit_pct}"
        )

        decision_order = decision.to_order_dict()

        gates_ok, gates_reason = evaluate_trade_gates(
            coin=coin,
            decision_order=decision_order,
            portfolio=portfolio,
            correlations=correlations,
            correlation_engine=self.context.correlation_engine,
            risk_manager=self.context.risk_manager,
            cfg=self.context.cfg,
            dynamic_min_sizes=self._dynamic_min_sizes,
            state=state,
            daily_notional_used=daily_notional_used,
            peak=peak,
            metrics=self.context.metrics,
            tech_data=tech_data,
            market_price=market_data.last_price,
        )
        if not gates_ok:
            logger.info(f"{coin} blocked by gates: {gates_reason}")
            return None

        decision = TradeDecision.from_order_dict(decision_order)

        if decision.action == "hold" and coin in portfolio.positions:
            updated = self.context.update_protection_without_trade(coin, decision_order)
            if updated:
                logger.info(f"{coin} hold with SL/TP update applied")
            self.context.metrics.increment("holds_total")
            return {"trades": 0, "notional": Decimal("0"), "failed": False}

        execution = execute_and_verify_trade(
            cfg=self.context.cfg,
            execution_engine=self.context.execution_engine,
            order_verifier=self.context.order_verifier,
            portfolio_service=self.context.portfolio_service,
            coin=coin,
            decision_order=decision_order,
            market_data=market_data,
            positions=portfolio.positions,
            logger=logger,
        )

        trade_record = build_trade_record(
            coin=coin,
            decision=decision,
            execution=execution,
            execution_mode=self.context.cfg.execution_mode,
        )
        self.context.state_store.add_trade_record(state, trade_record)

        if execution.success:
            return handle_successful_execution(
                coin=coin,
                decision=decision,
                execution=execution,
                state=state,
                metrics=self.context.metrics,
                position_manager=self.context.position_manager,
                sync_exchange_protective_orders=self.context.sync_exchange_protective_orders,
                cancel_exchange_protective_orders=self.context.cancel_exchange_protective_orders,
                notifier=self.context.notifier,
                trade_record=trade_record,
                logger=logger,
            )

        self.context.metrics.increment("execution_failures_total")
        logger.warning(f"{coin} execution failed: {execution.reason or 'unknown'}")
        return {"trades": 0, "notional": Decimal("0"), "failed": True}