import logging
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from config.bot_config import BotConfig
from correlation_engine import CorrelationEngine
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import PortfolioState
from notifier import Notifier
from orchestration.coin_processing_utils import log_coin_indicators
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


class CoinCycleProcessor:
    """Gestisce l'intero flusso per singola coin: dati → decisione → risk → esecuzione."""

    def __init__(
        self,
        cfg: BotConfig,
        execution_engine: ExecutionEngine,
        risk_manager: RiskManager,
        state_store: StateStore,
        metrics: MetricsCollector,
        position_manager: PositionManager,
        correlation_engine: CorrelationEngine,
        order_verifier: OrderVerifier,
        notifier: Notifier,
        portfolio_service: PortfolioService,
        llm_engine: Optional[LLMEngine],
        hl_rate_limiter: TokenBucketRateLimiter,
        llm_rate_limiter: TokenBucketRateLimiter,
        update_protection_without_trade: Callable[[str, Dict[str, Any]], bool],
        sync_exchange_protective_orders: Callable[[str], bool],
        cancel_exchange_protective_orders: Callable[[str], None],
    ):
        self.cfg = cfg
        self.execution_engine = execution_engine
        self.risk_manager = risk_manager
        self.state_store = state_store
        self.metrics = metrics
        self.position_manager = position_manager
        self.correlation_engine = correlation_engine
        self.order_verifier = order_verifier
        self.notifier = notifier
        self.portfolio_service = portfolio_service
        self.llm_engine = llm_engine
        self.hl_rate_limiter = hl_rate_limiter
        self.llm_rate_limiter = llm_rate_limiter
        self.update_protection_without_trade = update_protection_without_trade
        self.sync_exchange_protective_orders = sync_exchange_protective_orders
        self.cancel_exchange_protective_orders = cancel_exchange_protective_orders

        self._dynamic_min_sizes: Dict[str, Decimal] = {}

    def process_single_coin(
        self,
        coin: str,
        portfolio: PortfolioState,
        state: Dict[str, Any],
        daily_notional_used: Decimal,
        peak: Decimal,
        consecutive_losses: int,
        all_mids: Optional[Dict[str, str]],
        recent_trades: List[Dict[str, Any]],
        correlations: Dict[str, Dict[str, Decimal]],
    ) -> Optional[Dict[str, Any]]:
        self.hl_rate_limiter.acquire(3)
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
            llm_engine=self.llm_engine,
            llm_rate_limiter=self.llm_rate_limiter,
            metrics=self.metrics,
            position_manager=self.position_manager,
            exchange_client=self.execution_engine.exchange_client,
            sync_exchange_protective_orders=self.sync_exchange_protective_orders,
            logger=logger,
        )

        logger.info(
            f"{coin} decision: action={decision['action']}, size={decision['size']}, "
            f"leverage={decision['leverage']}, confidence={decision['confidence']}, "
            f"sl_pct={decision.get('stop_loss_pct')}, tp_pct={decision.get('take_profit_pct')}"
        )

        gates_ok, gates_reason = evaluate_trade_gates(
            coin=coin,
            decision=decision,
            portfolio=portfolio,
            correlations=correlations,
            correlation_engine=self.correlation_engine,
            risk_manager=self.risk_manager,
            cfg=self.cfg,
            dynamic_min_sizes=self._dynamic_min_sizes,
            state=state,
            daily_notional_used=daily_notional_used,
            peak=peak,
            metrics=self.metrics,
            tech_data=tech_data,
            market_price=market_data.last_price,
        )
        if not gates_ok:
            logger.info(f"{coin} blocked by gates: {gates_reason}")
            return None

        if decision["action"] == "hold" and coin in portfolio.positions:
            updated = self.update_protection_without_trade(coin, decision)
            if updated:
                logger.info(f"{coin} hold with SL/TP update applied")
            self.metrics.increment("holds_total")
            return {"trades": 0, "notional": Decimal("0"), "failed": False}

        result, executed_price, executed_size, fill_status = execute_and_verify_trade(
            cfg=self.cfg,
            execution_engine=self.execution_engine,
            order_verifier=self.order_verifier,
            portfolio_service=self.portfolio_service,
            coin=coin,
            decision=decision,
            market_data=market_data,
            positions=portfolio.positions,
            logger=logger,
        )

        trade_record = build_trade_record(
            coin=coin,
            decision=decision,
            executed_size=executed_size,
            executed_price=executed_price,
            result=result,
            fill_status=fill_status,
            execution_mode=self.cfg.execution_mode,
        )
        self.state_store.add_trade_record(state, trade_record)

        if result["success"]:
            return handle_successful_execution(
                coin=coin,
                decision=decision,
                executed_size=executed_size,
                executed_price=executed_price,
                result=result,
                state=state,
                metrics=self.metrics,
                position_manager=self.position_manager,
                sync_exchange_protective_orders=self.sync_exchange_protective_orders,
                cancel_exchange_protective_orders=self.cancel_exchange_protective_orders,
                notifier=self.notifier,
                trade_record=trade_record,
                logger=logger,
            )

        self.metrics.increment("execution_failures_total")
        logger.warning(f"{coin} execution failed: {result.get('reason', 'unknown')}")
        return {"trades": 0, "notional": Decimal("0"), "failed": True}