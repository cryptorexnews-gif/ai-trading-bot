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
from models import MarketData, PortfolioState
from notifier import Notifier
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
        self._dynamic_min_sizes: Dict[str, Decimal] = {}
        self._cycle_count: int = 0

    def set_cycle_count(self, count: int) -> None:
        """Set current cycle count for live status updates."""
        self._cycle_count = count

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

            self.hl_rate_limiter.acquire(1)
            result = self.exchange_client.place_order(coin, side, close_size, current_price)

            if result.get("success"):
                triggered += 1
                self.position_manager.remove_position(coin)
                self._send_trigger_notification(trigger, coin, entry_price, trigger_price, current_price)
                self._record_trigger_trade(coin, close_size, current_price, result, action_info, trigger)
                self.metrics.increment("trades_executed_total")
                logger.info(f"{trigger.upper()} close executed for {coin}")
            else:
                logger.error(f"Failed to execute {trigger} close for {coin}: {result}")

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
        result: Dict, action_info: Dict, trigger: str
    ) -> None:
        state = self.state_store.load_state()
        trade_record = {
            "timestamp": time.time(), "coin": coin, "action": "close_position",
            "size": str(close_size), "price": str(current_price),
            "notional": str(result.get("notional", "0")), "leverage": 1, "confidence": 1.0,
            "reasoning": action_info.get("reasoning", ""), "success": True,
            "mode": self.cfg.execution_mode, "trigger": trigger, "order_status": "filled",
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
            self.hl_rate_limiter.acquire(1)
            result = self.exchange_client.place_order(worst_coin, side, close_size, current_price)
            if result.get("success"):
                self.position_manager.remove_position(worst_coin)
                logger.info(f"Emergency close executed for {worst_coin}")
                state = self.state_store.load_state()
                trade_record = {
                    "timestamp": time.time(), "coin": worst_coin, "action": "close_position",
                    "size": str(close_size), "price": str(current_price),
                    "notional": str(result.get("notional", "0")), "leverage": 1, "confidence": 1.0,
                    "reasoning": "Emergency derisk: margin usage critical", "success": True,
                    "mode": self.cfg.execution_mode, "trigger": "emergency", "order_status": "filled",
                }
                self.state_store.add_trade_record(state, trade_record)
                self.state_store.save_state(state)
                return self._fetch_portfolio()
            else:
                logger.error(f"Emergency close FAILED for {worst_coin}: {result}")

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
                is_running=True, execution_mode=self.cfg.execution_mode,
                cycle_count=self._cycle_count, last_cycle_duration=0, portfolio=portfolio, current_coin=coin
            )

            result = self._process_single_coin(
                coin, portfolio, state, daily_notional_used + notional_added, peak,
                consecutive_losses, all_mids, recent_trades, correlations
            )

            if result is not None:
                trades_executed += result["trades"]
                notional_added += result["notional"]
                if result["trades"] > 0:
                    state["consecutive_losses"] = 0
                elif result.get("failed"):
                    state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1

        return trades_executed, notional_added

    def _late_confirm_fill(
        self,
        coin: str,
        snapshot: Dict[str, Any],
        expected_side: str,
        expected_size: Decimal,
        tolerance_pct: Decimal = Decimal("0.05")
    ) -> Tuple[bool, str]:
        """
        Secondary confirmation when initial verifier says not_filled.
        Checks latest portfolio position delta to catch delayed fills.
        Returns (confirmed, fill_status).
        """
        try:
            latest_portfolio = self.portfolio_service.get_portfolio_state()
        except Exception:
            return False, "not_filled"

        size_before = Decimal(str(snapshot.get("size_before", "0")))
        current_size = Decimal("0")
        if coin in latest_portfolio.positions:
            current_size = Decimal(str(latest_portfolio.positions[coin].get("size", 0)))

        actual_change = current_size - size_before
        expected_change = expected_size if expected_side == "buy" else -expected_size

        if expected_change == 0:
            return False, "not_filled"

        fill_ratio = abs(actual_change) / abs(expected_change)
        if fill_ratio >= (Decimal("1") - tolerance_pct):
            return True, "filled_late"
        if fill_ratio >= Decimal("0.1"):
            return True, "partially_filled_late"
        return False, "not_filled"

    def _process_single_coin(
        self, coin: str, portfolio: PortfolioState, state: Dict,
        daily_notional_used: Decimal, peak: Decimal, consecutive_losses: int,
        all_mids: Optional[Dict], recent_trades: List, correlations: Dict
    ) -> Optional[Dict[str, Any]]:
        """Process a single coin: fetch data → LLM → risk check → execute."""
        self.hl_rate_limiter.acquire(3)
        tech_data = technical_fetcher.get_technical_indicators(coin)
        if not tech_data:
            logger.warning(f"Skipping {coin}: no market data")
            return None

        market_data = MarketData(
            coin=coin, last_price=tech_data["current_price"],
            change_24h=tech_data["change_24h"], volume_24h=tech_data["volume_24h"],
            funding_rate=tech_data["funding_rate"], timestamp=time.time()
        )

        self._log_coin_indicators(coin, market_data, tech_data)

        corr_ok, corr_reason = self.correlation_engine.check_correlation_risk(
            coin, "buy", portfolio.positions, correlations
        )
        if not corr_ok:
            logger.info(f"{coin} correlation risk: {corr_reason}")

        funding_data = technical_fetcher.get_funding_for_coin(coin)
        decision = self._get_decision(coin, market_data, portfolio, tech_data, all_mids, funding_data, recent_trades, peak, consecutive_losses)

        logger.info(
            f"{coin} decision: action={decision['action']}, size={decision['size']}, "
            f"leverage={decision['leverage']}, confidence={decision['confidence']}, "
            f"sl_pct={decision.get('stop_loss_pct')}, tp_pct={decision.get('take_profit_pct')}"
        )

        if not corr_ok and decision["action"] in ["buy", "sell", "increase_position"]:
            logger.info(f"{coin} blocked by correlation risk: {corr_reason}")
            self.metrics.increment("risk_rejections_total")
            return None

        min_size = self._resolve_min_size(coin)
        self.risk_manager.min_size_by_coin[coin] = min_size

        volatility = Decimal("0")
        if tech_data.get("intraday_atr", Decimal("0")) > 0 and market_data.last_price > 0:
            volatility = tech_data["intraday_atr"] / market_data.last_price

        risk_ok, risk_reason = self.risk_manager.check_order(
            coin, decision, market_data.last_price, portfolio,
            state.get("last_trade_timestamp_by_coin", {}),
            daily_notional_used, time.time(), volatility, peak
        )
        if not risk_ok:
            logger.info(f"{coin} risk rejected: {risk_reason}")
            self.metrics.increment("risk_rejections_total")
            return None

        snapshot = None
        if self.cfg.execution_mode == "live" and self.cfg.enable_mainnet_trading:
            snapshot = self.order_verifier.snapshot_position(self.cfg.wallet_address, coin)

        result = self.execution_engine.execute(coin, decision, market_data, portfolio.positions)

        fill_status = "unknown"
        if snapshot and result["success"] and decision["action"] in ["buy", "sell", "increase_position"]:
            expected_side = "buy" if decision["action"] in ["buy", "increase_position"] else "sell"
            expected_size = Decimal(str(decision["size"]))

            verification = self.order_verifier.verify_fill(
                self.cfg.wallet_address, coin, expected_side, expected_size, snapshot
            )
            fill_status = verification.get("fill_status", "unknown")

            if fill_status == "not_filled":
                late_confirmed, late_status = self._late_confirm_fill(
                    coin=coin,
                    snapshot=snapshot,
                    expected_side=expected_side,
                    expected_size=expected_size
                )
                if late_confirmed:
                    fill_status = late_status
                    logger.info(f"{coin} late fill confirmation succeeded: {late_status}")
                else:
                    logger.warning(f"{coin} order NOT FILLED — marking as failed")
                    result["success"] = False
                    result["reason"] = "order_not_filled"

        trade_record = {
            "timestamp": time.time(), "coin": coin, "action": decision["action"],
            "size": str(decision["size"]), "price": str(market_data.last_price),
            "notional": str(result.get("notional", "0")), "leverage": decision["leverage"],
            "confidence": decision["confidence"], "reasoning": decision.get("reasoning", "")[:200],
            "success": result["success"], "mode": self.cfg.execution_mode,
            "trigger": "ai", "order_status": fill_status,
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
                        size=Decimal(str(decision["size"])),
                        entry_price=market_data.last_price,
                        is_long=is_long,
                        leverage=decision["leverage"],
                        sl_pct=sl_pct if isinstance(sl_pct, Decimal) else None,
                        tp_pct=tp_pct if isinstance(tp_pct, Decimal) else None,
                    )
                self.notifier.notify_trade(trade_record)
                logger.info(f"{coin} executed: reason={result['reason']}, notional=${notional}")
                return {"trades": 1, "notional": notional, "failed": False}
            else:
                self.metrics.increment("holds_total")
                logger.info(f"{coin}: hold (no trade)")
                return {"trades": 0, "notional": Decimal("0"), "failed": False}
        else:
            self.metrics.increment("execution_failures_total")
            logger.warning(f"{coin} execution failed: {result.get('reason', 'unknown')}")
            return {"trades": 0, "notional": Decimal("0"), "failed": True}

    def _get_decision(self, coin, market_data, portfolio, tech_data, all_mids, funding_data, recent_trades, peak, consecutive_losses):
        """Get trading decision from LLM or fallback."""
        if self.llm_engine:
            self.llm_rate_limiter.acquire(1)
            self.metrics.increment("llm_calls_total")
            decision = self.llm_engine.get_trading_decision(
                market_data=market_data, portfolio_state=portfolio, technical_data=tech_data,
                all_mids=all_mids, funding_data=funding_data, recent_trades=recent_trades,
                peak_portfolio_value=peak, consecutive_losses=consecutive_losses
            )
            if not decision:
                self.metrics.increment("llm_errors_total")
                decision = self._fallback_decision()
                logger.warning(f"LLM failed for {coin}, using fallback")
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
            "reasoning": "LLM unavailable — safe fallback to hold"
        }

    def _log_coin_indicators(self, coin: str, market_data: MarketData, tech_data: Dict) -> None:
        trends_aligned = tech_data.get("trends_aligned", False)
        intraday_trend = tech_data.get("intraday_trend", "unknown")
        hourly_ctx = tech_data.get("hourly_context", {})
        hourly_trend = hourly_ctx.get("trend", "unknown")
        logger.info(
            f"{coin}: price=${market_data.last_price}, "
            f"RSI14={float(tech_data.get('current_rsi_14', 50)):.1f}, "
            f"BB={float(tech_data.get('bb_position', 0.5)):.2f}, "
            f"vol_ratio={float(tech_data.get('volume_ratio', 1)):.2f}, "
            f"trends={'ALIGNED' if trends_aligned else 'DIVERGENT'} "
            f"(1h={intraday_trend}, 4h={hourly_trend})"
        )

    def _resolve_min_size(self, coin: str) -> Decimal:
        if coin in self.cfg.min_size_by_coin:
            return self.cfg.min_size_by_coin[coin]
        if coin in self._dynamic_min_sizes:
            return self._dynamic_min_sizes[coin]
        mids = self.exchange_client.get_all_mids()
        if mids and coin in mids:
            mid_price = Decimal(str(mids[coin]))
            if mid_price > 0:
                raw_min = Decimal("1") / mid_price
                if raw_min < Decimal("0.001"): resolved = Decimal("0.001")
                elif raw_min < Decimal("0.01"): resolved = Decimal("0.01")
                elif raw_min < Decimal("0.1"): resolved = Decimal("0.1")
                elif raw_min < Decimal("1"): resolved = Decimal("1")
                elif raw_min < Decimal("10"): resolved = Decimal("10")
                elif raw_min < Decimal("100"): resolved = Decimal("100")
                elif raw_min < Decimal("1000"): resolved = Decimal("1000")
                else: resolved = Decimal("10000")
                self._dynamic_min_sizes[coin] = resolved
                logger.info(f"Dynamic min size for {coin}: {resolved} (price=${mid_price})")
                return resolved
        logger.warning(f"No min size data for {coin}, using default {self.cfg.default_min_size}")
        return self.cfg.default_min_size