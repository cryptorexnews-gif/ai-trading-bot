import logging
import time
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from config.bot_config import BotConfig
from correlation_engine import CorrelationEngine
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import MarketData, PortfolioState
from notifier import Notifier
from orchestration.coin_processing_utils import late_confirm_fill, log_coin_indicators, resolve_min_size
from orchestration.order_context_builder import (
    build_managed_position_context,
    extract_protective_orders_for_coin,
    has_both_tp_sl,
)
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

        market_data = MarketData(
            coin=coin,
            last_price=tech_data["current_price"],
            change_24h=tech_data["change_24h"],
            volume_24h=tech_data["volume_24h"],
            funding_rate=tech_data["funding_rate"],
            timestamp=time.time(),
        )

        log_coin_indicators(coin, market_data, tech_data)

        funding_data = technical_fetcher.get_funding_for_coin(coin)
        decision = self._get_decision(
            coin=coin,
            market_data=market_data,
            portfolio=portfolio,
            tech_data=tech_data,
            all_mids=all_mids,
            funding_data=funding_data,
            recent_trades=recent_trades,
            peak=peak,
            consecutive_losses=consecutive_losses,
        )

        logger.info(
            f"{coin} decision: action={decision['action']}, size={decision['size']}, "
            f"leverage={decision['leverage']}, confidence={decision['confidence']}, "
            f"sl_pct={decision.get('stop_loss_pct')}, tp_pct={decision.get('take_profit_pct')}"
        )

        corr_ok, corr_reason = self.correlation_engine.check_correlation_risk(
            coin, decision["action"], portfolio.positions, correlations
        )
        if not corr_ok and decision["action"] in ["buy", "sell", "increase_position"]:
            logger.info(f"{coin} blocked by correlation risk: {corr_reason}")
            self.metrics.increment("risk_rejections_total")
            return None

        min_size = resolve_min_size(coin, self.cfg, self._dynamic_min_sizes)
        self.risk_manager.min_size_by_coin[coin] = min_size

        volatility = Decimal("0")
        if tech_data.get("intraday_atr", Decimal("0")) > 0 and market_data.last_price > 0:
            volatility = tech_data["intraday_atr"] / market_data.last_price

        risk_ok, risk_reason = self.risk_manager.check_order(
            coin,
            decision,
            market_data.last_price,
            portfolio,
            state.get("last_trade_timestamps_by_coin", state.get("last_trade_timestamp_by_coin", {})),
            daily_notional_used,
            time.time(),
            volatility,
            peak,
        )
        if not risk_ok:
            logger.warning(f"{coin} risk manager rejection bypassed: {risk_reason}")

        if decision["action"] == "hold" and coin in portfolio.positions:
            updated = self.update_protection_without_trade(coin, decision)
            if updated:
                logger.info(f"{coin} hold with SL/TP update applied")
            self.metrics.increment("holds_total")
            return {"trades": 0, "notional": Decimal("0"), "failed": False}

        snapshot = None
        if self.cfg.execution_mode == "live" and self.cfg.enable_mainnet_trading:
            snapshot = self.order_verifier.snapshot_position(self.cfg.wallet_address, coin)

        result = self.execution_engine.execute(coin, decision, market_data, portfolio.positions)

        executed_price = Decimal(str(result.get("filled_price", market_data.last_price)))
        if executed_price <= 0:
            executed_price = market_data.last_price

        executed_size = Decimal(str(result.get("executed_size", decision["size"])))
        if executed_size <= 0:
            executed_size = Decimal(str(decision["size"]))

        fill_status = "unknown"
        if snapshot and result["success"] and decision["action"] in ["buy", "sell", "increase_position"]:
            expected_side = "buy" if decision["action"] in ["buy", "increase_position"] else "sell"
            expected_size = Decimal(str(executed_size))

            verification = self.order_verifier.verify_fill(
                self.cfg.wallet_address, coin, expected_side, expected_size, snapshot
            )
            fill_status = verification.get("fill_status", "unknown")

            if fill_status == "not_filled":
                late_confirmed, late_status = late_confirm_fill(
                    coin=coin,
                    snapshot=snapshot,
                    expected_side=expected_side,
                    expected_size=expected_size,
                    portfolio_service=self.portfolio_service,
                )
                if late_confirmed:
                    fill_status = late_status
                    logger.info(f"{coin} late fill confirmation succeeded: {late_status}")
                else:
                    logger.warning(f"{coin} order NOT FILLED — marking as failed")
                    result["success"] = False
                    result["reason"] = "order_not_filled"

        trade_record = {
            "timestamp": time.time(),
            "coin": coin,
            "action": decision["action"],
            "size": str(executed_size),
            "price": str(executed_price),
            "notional": str(result.get("notional", "0")),
            "leverage": decision["leverage"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "success": result["success"],
            "mode": self.cfg.execution_mode,
            "trigger": "ai",
            "order_status": fill_status,
        }
        self.state_store.add_trade_record(state, trade_record)

        if result["success"]:
            notional = Decimal(str(result["notional"]))
            if notional > 0:
                state.setdefault("last_trade_timestamp_by_coin", {})[coin] = time.time()
                self.metrics.increment("trades_executed_total")

                if decision["action"] in ["buy", "sell", "increase_position"]:
                    is_long = decision["action"] in ["buy", "increase_position"]
                    sl_pct = decision.get("stop_loss_pct")
                    tp_pct = decision.get("take_profit_pct")

                    self.position_manager.register_position(
                        coin=coin,
                        size=executed_size,
                        entry_price=executed_price,
                        is_long=is_long,
                        leverage=decision["leverage"],
                        sl_pct=sl_pct if isinstance(sl_pct, Decimal) else None,
                        tp_pct=tp_pct if isinstance(tp_pct, Decimal) else None,
                    )
                    self.sync_exchange_protective_orders(coin)

                elif decision["action"] == "close_position":
                    self.cancel_exchange_protective_orders(coin)
                    self.position_manager.remove_position(coin)

                elif decision["action"] == "reduce_position":
                    self.sync_exchange_protective_orders(coin)

                self.notifier.notify_trade(trade_record)
                logger.info(f"{coin} executed: reason={result['reason']}, notional=${notional}")
                return {"trades": 1, "notional": notional, "failed": False}

            self.metrics.increment("holds_total")
            logger.info(f"{coin}: hold (no trade)")
            return {"trades": 0, "notional": Decimal("0"), "failed": False}

        self.metrics.increment("execution_failures_total")
        logger.warning(f"{coin} execution failed: {result.get('reason', 'unknown')}")
        return {"trades": 0, "notional": Decimal("0"), "failed": True}

    def _get_decision(
        self,
        coin: str,
        market_data: MarketData,
        portfolio: PortfolioState,
        tech_data: Dict[str, Any],
        all_mids: Optional[Dict[str, str]],
        funding_data: Optional[Dict[str, Any]],
        recent_trades: List[Dict[str, Any]],
        peak: Decimal,
        consecutive_losses: int,
    ) -> Dict[str, Any]:
        if self.llm_engine:
            self.llm_rate_limiter.acquire(1)
            self.metrics.increment("llm_calls_total")

            managed_position = build_managed_position_context(self.position_manager, coin)
            protective_orders = extract_protective_orders_for_coin(self.execution_engine.exchange_client, coin)

            has_open_position = coin in portfolio.positions and Decimal(str(portfolio.positions[coin].get("size", 0))) != 0
            if has_open_position and not has_both_tp_sl(protective_orders):
                logger.warning(f"{coin} missing TP/SL protective orders before LLM call, forcing sync")
                self.sync_exchange_protective_orders(coin)
                protective_orders = extract_protective_orders_for_coin(self.execution_engine.exchange_client, coin)

            decision = self.llm_engine.get_trading_decision(
                market_data=market_data,
                portfolio_state=portfolio,
                technical_data=tech_data,
                all_mids=all_mids,
                funding_data=funding_data,
                recent_trades=recent_trades,
                peak_portfolio_value=peak,
                consecutive_losses=consecutive_losses,
                managed_position=managed_position,
                protective_orders=protective_orders,
            )
            if not decision:
                self.metrics.increment("llm_errors_total")
                logger.warning(f"LLM failed for {coin}, using fallback")
                return self._fallback_decision()
            return decision
        return self._fallback_decision()

    @staticmethod
    def _fallback_decision() -> Dict[str, Any]:
        return {
            "action": "hold",
            "size": Decimal("0"),
            "leverage": 1,
            "confidence": 0.0,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "reasoning": "LLM unavailable — safe fallback to hold",
        }