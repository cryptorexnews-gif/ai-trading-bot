#!/usr/bin/env python3
"""
Hyperliquid Trading Bot — Production Entry Point
Uses DeepSeek v3.2 via OpenRouter for AI-driven trading decisions.
All market data sourced exclusively from Hyperliquid API.

Architecture:
  BotConfig (config/bot_config.py) — all configuration
  CycleOrchestrator (cycle_orchestrator.py) — trading cycle logic
  This file — initialization, signal handling, run loop
"""

import argparse
import logging
import os
import signal
import time
from decimal import Decimal
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

from bot_live_writer import write_live_status
from config.bot_config import BotConfig
from correlation_engine import CorrelationEngine
from cycle_orchestrator import CycleOrchestrator
from exchange_client import HyperliquidExchangeClient
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import PortfolioState
from notifier import Notifier
from order_verifier import OrderVerifier
from portfolio_service import PortfolioService
from position_manager import PositionManager
from risk_manager import RiskManager
from runtime_config_store import RuntimeConfigStore
from state_store import StateStore
from technical_analyzer_simple import technical_fetcher
from utils.health import HealthMonitor, HealthStatus, HealthCheckResult, check_disk_space, check_file_writable
from utils.logging_config import setup_logging
from utils.metrics import MetricsCollector
from utils.rate_limiter import get_rate_limiter


class HyperliquidBot:
    """Top-level bot: init, signal handling, run loop. Delegates cycle logic to CycleOrchestrator."""

    def __init__(self):
        self.cfg = BotConfig.from_env()
        setup_logging(log_level=self.cfg.log_level, json_format=True, log_file=self.cfg.log_file, console_output=True)

        warnings = self.cfg.validate()
        for w in warnings:
            logging.warning(f"CONFIG WARNING: {w}")

        self._cycle_count = 0
        self._last_cycle_duration = 0.0
        self._next_cycle_sec = self.cfg.default_cycle_sec
        self._shutdown_requested = False
        self._last_portfolio: Optional[PortfolioState] = None
        self._active_strategy_mode = "trend"
        self._active_runtime_pairs: List[str] = list(self.cfg.trading_pairs)

        self._base_profile = {
            "default_cycle_sec": self.cfg.default_cycle_sec,
            "min_cycle_sec": self.cfg.min_cycle_sec,
            "max_cycle_sec": self.cfg.max_cycle_sec,
            "max_trades_per_cycle": self.cfg.max_trades_per_cycle,
            "hard_max_leverage": self.cfg.hard_max_leverage,
            "min_confidence_open": self.cfg.min_confidence_open,
            "min_confidence_manage": self.cfg.min_confidence_manage,
            "max_order_margin_pct": self.cfg.max_order_margin_pct,
            "trade_cooldown_sec": self.cfg.trade_cooldown_sec,
            "daily_notional_limit_usd": self.cfg.daily_notional_limit_usd,
            "max_drawdown_pct": self.cfg.max_drawdown_pct,
            "max_single_asset_pct": self.cfg.max_single_asset_pct,
            "emergency_margin_threshold": self.cfg.emergency_margin_threshold,
            "trend_sl_pct": self.cfg.trend_sl_pct,
            "trend_tp_pct": self.cfg.trend_tp_pct,
            "trend_break_even_activation_pct": self.cfg.trend_break_even_activation_pct,
            "trend_trailing_activation_pct": self.cfg.trend_trailing_activation_pct,
            "trend_trailing_callback": self.cfg.trend_trailing_callback,
            "trend_position_size_pct": self.cfg.trend_position_size_pct,
            "volume_confirmation_threshold": self.cfg.volume_confirmation_threshold,
        }

        # Build components
        private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
        self.exchange_client = HyperliquidExchangeClient(
            base_url=self.cfg.base_url, private_key=private_key,
            enable_mainnet_trading=self.cfg.enable_mainnet_trading,
            execution_mode=self.cfg.execution_mode,
            meta_cache_ttl_sec=self.cfg.meta_cache_ttl_sec,
            paper_slippage_bps=self.cfg.paper_slippage_bps,
            info_timeout=self.cfg.info_timeout, exchange_timeout=self.cfg.exchange_timeout,
        )

        self.state_store = StateStore(self.cfg.state_path, self.cfg.metrics_path)
        self.runtime_config_store = RuntimeConfigStore("state/runtime_config.json", self.cfg.trading_pairs)
        self.metrics = MetricsCollector()
        self.notifier = Notifier(enabled=True)
        self.health_monitor = HealthMonitor()
        self._setup_health_checks()

        self.portfolio_service = PortfolioService(self.exchange_client, self.cfg.wallet_address)

        self.orchestrator = CycleOrchestrator(
            cfg=self.cfg,
            exchange_client=self.exchange_client,
            execution_engine=ExecutionEngine(self.exchange_client),
            risk_manager=RiskManager(
                min_size_by_coin=dict(self.cfg.min_size_by_coin),
                hard_max_leverage=self.cfg.hard_max_leverage,
                min_confidence_open=self.cfg.min_confidence_open,
                min_confidence_manage=self.cfg.min_confidence_manage,
                max_margin_usage=self.cfg.max_margin_usage,
                max_order_margin_pct=self.cfg.max_order_margin_pct,
                max_order_notional_usd=self.cfg.max_order_notional_usd,
                trade_cooldown_sec=self.cfg.trade_cooldown_sec,
                daily_notional_limit_usd=self.cfg.daily_notional_limit_usd,
                volatility_multiplier=self.cfg.volatility_multiplier,
                max_drawdown_pct=self.cfg.max_drawdown_pct,
                max_single_asset_pct=self.cfg.max_single_asset_pct,
                emergency_margin_threshold=self.cfg.emergency_margin_threshold,
            ),
            state_store=self.state_store,
            metrics=self.metrics,
            position_manager=PositionManager(
                default_sl_pct=self.cfg.trend_sl_pct,
                default_tp_pct=self.cfg.trend_tp_pct,
                default_trailing_callback=self.cfg.trend_trailing_callback,
                enable_trailing_stop=self.cfg.enable_trailing_stop,
                trailing_activation_pct=self.cfg.trend_trailing_activation_pct,
                break_even_activation_pct=self.cfg.trend_break_even_activation_pct,
                break_even_offset_pct=self.cfg.break_even_offset_pct,
            ),
            correlation_engine=CorrelationEngine(correlation_threshold=self.cfg.correlation_threshold),
            order_verifier=OrderVerifier(exchange_client=self.exchange_client, max_wait_sec=20.0, check_interval=2.0),
            notifier=self.notifier,
            health_monitor=self.health_monitor,
            portfolio_service=self.portfolio_service,
            llm_engine=LLMEngine(
                api_key=self.cfg.openrouter_api_key, model=self.cfg.llm_model,
                max_tokens=self.cfg.llm_max_tokens, temperature=self.cfg.llm_temperature,
            ) if self.cfg.openrouter_api_key else None,
            hl_rate_limiter=get_rate_limiter("hyperliquid_api", max_tokens=20, tokens_per_second=2.0),
            llm_rate_limiter=get_rate_limiter("openrouter_api", max_tokens=5, tokens_per_second=0.5),
            trading_pairs=list(self.cfg.trading_pairs),
        )

        self._apply_runtime_config(force=True)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_health_checks(self) -> None:
        self.health_monitor.add_check(
            "exchange_connectivity",
            lambda: self._check_exchange_health(),
            interval=60.0
        )
        self.health_monitor.add_check("disk_space", lambda: check_disk_space(".", min_free_gb=0.5), interval=300.0)
        self.health_monitor.add_check("state_writable", lambda: check_file_writable("state"), interval=300.0)

    def _check_exchange_health(self) -> HealthCheckResult:
        meta = self.exchange_client.get_meta(force_refresh=True)
        if meta:
            return HealthCheckResult(
                name="exchange_connectivity", status=HealthStatus.HEALTHY,
                message="Hyperliquid API reachable",
                details={"assets_count": len(meta.get("universe", []))}
            )
        return HealthCheckResult(
            name="exchange_connectivity", status=HealthStatus.UNHEALTHY,
            message="Hyperliquid API unreachable"
        )

    def _signal_handler(self, signum, frame):
        logging.info(f"Received {signal.Signals(signum).name}, requesting graceful shutdown...")
        self._shutdown_requested = True

    def _validate_trading_pairs(self, pairs: Optional[List[str]] = None) -> List[str]:
        meta = self.exchange_client.get_meta(force_refresh=True)
        source_pairs = pairs if pairs is not None else list(self.cfg.trading_pairs)
        if not meta:
            logging.warning("Cannot validate trading pairs — meta unavailable")
            return source_pairs
        available = {a.get("name") for a in meta.get("universe", [])}
        valid = [c for c in source_pairs if c in available]
        invalid = [c for c in source_pairs if c not in available]
        if invalid:
            logging.warning(f"Trading pairs NOT found on Hyperliquid (removed): {invalid}")
        logging.info(f"Validated {len(valid)} trading pairs: {valid}")
        return valid

    def _apply_strategy_profile(self, strategy_mode: str) -> None:
        rm = self.orchestrator.risk_manager
        pm = self.orchestrator.position_manager

        if strategy_mode == "scalping":
            self.cfg.default_cycle_sec = 300
            self.cfg.min_cycle_sec = 300
            self.cfg.max_cycle_sec = 900
            self.cfg.max_trades_per_cycle = 3

            self.cfg.hard_max_leverage = Decimal("2")
            self.cfg.min_confidence_open = Decimal("0.66")
            self.cfg.min_confidence_manage = Decimal("0.45")
            self.cfg.max_order_margin_pct = Decimal("0.06")
            self.cfg.trade_cooldown_sec = 120
            self.cfg.daily_notional_limit_usd = Decimal("25")
            self.cfg.max_drawdown_pct = Decimal("0.08")
            self.cfg.max_single_asset_pct = Decimal("0.25")
            self.cfg.emergency_margin_threshold = Decimal("0.80")
            self.cfg.trend_position_size_pct = Decimal("0.01")
            self.cfg.volume_confirmation_threshold = Decimal("1.2")
            self.cfg.trend_sl_pct = Decimal("0.02")
            self.cfg.trend_tp_pct = Decimal("0.04")
            self.cfg.trend_break_even_activation_pct = Decimal("0.01")
            self.cfg.trend_trailing_activation_pct = Decimal("0.015")
            self.cfg.trend_trailing_callback = Decimal("0.01")
        else:
            self.cfg.default_cycle_sec = self._base_profile["default_cycle_sec"]
            self.cfg.min_cycle_sec = self._base_profile["min_cycle_sec"]
            self.cfg.max_cycle_sec = self._base_profile["max_cycle_sec"]
            self.cfg.max_trades_per_cycle = self._base_profile["max_trades_per_cycle"]

            self.cfg.hard_max_leverage = self._base_profile["hard_max_leverage"]
            self.cfg.min_confidence_open = self._base_profile["min_confidence_open"]
            self.cfg.min_confidence_manage = self._base_profile["min_confidence_manage"]
            self.cfg.max_order_margin_pct = self._base_profile["max_order_margin_pct"]
            self.cfg.trade_cooldown_sec = self._base_profile["trade_cooldown_sec"]
            self.cfg.daily_notional_limit_usd = self._base_profile["daily_notional_limit_usd"]
            self.cfg.max_drawdown_pct = self._base_profile["max_drawdown_pct"]
            self.cfg.max_single_asset_pct = self._base_profile["max_single_asset_pct"]
            self.cfg.emergency_margin_threshold = self._base_profile["emergency_margin_threshold"]
            self.cfg.trend_position_size_pct = self._base_profile["trend_position_size_pct"]
            self.cfg.volume_confirmation_threshold = self._base_profile["volume_confirmation_threshold"]
            self.cfg.trend_sl_pct = self._base_profile["trend_sl_pct"]
            self.cfg.trend_tp_pct = self._base_profile["trend_tp_pct"]
            self.cfg.trend_break_even_activation_pct = self._base_profile["trend_break_even_activation_pct"]
            self.cfg.trend_trailing_activation_pct = self._base_profile["trend_trailing_activation_pct"]
            self.cfg.trend_trailing_callback = self._base_profile["trend_trailing_callback"]

        rm.hard_max_leverage = self.cfg.hard_max_leverage
        rm.min_confidence_open = self.cfg.min_confidence_open
        rm.min_confidence_manage = self.cfg.min_confidence_manage
        rm.max_order_margin_pct = self.cfg.max_order_margin_pct
        rm.trade_cooldown_sec = self.cfg.trade_cooldown_sec
        rm.daily_notional_limit_usd = self.cfg.daily_notional_limit_usd
        rm.max_drawdown_pct = self.cfg.max_drawdown_pct
        rm.max_single_asset_pct = self.cfg.max_single_asset_pct
        rm.emergency_margin_threshold = self.cfg.emergency_margin_threshold

        pm.default_sl_pct = self.cfg.trend_sl_pct
        pm.default_tp_pct = self.cfg.trend_tp_pct
        pm.default_trailing_callback = self.cfg.trend_trailing_callback
        pm.trailing_activation_pct = self.cfg.trend_trailing_activation_pct
        pm.break_even_activation_pct = self.cfg.trend_break_even_activation_pct

        self._next_cycle_sec = self.cfg.default_cycle_sec

    def _apply_runtime_config(self, force: bool = False) -> None:
        runtime = self.runtime_config_store.load()
        runtime_mode = str(runtime.get("strategy_mode", "trend")).strip().lower()
        if runtime_mode not in {"trend", "scalping"}:
            runtime_mode = "trend"

        runtime_pairs = [str(p).strip().upper() for p in runtime.get("trading_pairs", []) if str(p).strip()]
        if not runtime_pairs:
            runtime_pairs = list(self.cfg.trading_pairs)

        validated_pairs = self._validate_trading_pairs(runtime_pairs)
        if not validated_pairs:
            validated_pairs = self._validate_trading_pairs(list(self.cfg.trading_pairs))

        mode_changed = runtime_mode != self._active_strategy_mode
        pairs_changed = validated_pairs != self._active_runtime_pairs

        if not force and not mode_changed and not pairs_changed:
            return

        self._apply_strategy_profile(runtime_mode)
        self.orchestrator.trading_pairs = validated_pairs
        self._active_strategy_mode = runtime_mode
        self._active_runtime_pairs = list(validated_pairs)

        logging.info(
            f"Runtime config applied: strategy_mode={runtime_mode}, "
            f"pairs={validated_pairs}, cycle={self.cfg.default_cycle_sec}s, "
            f"max_trades_per_cycle={self.cfg.max_trades_per_cycle}"
        )

    def _format_cycle_label(self, cycle_seconds: int) -> str:
        if cycle_seconds <= 0:
            return "0s"
        if cycle_seconds % 60 == 0:
            minutes = cycle_seconds // 60
            return "1 minuto" if minutes == 1 else f"{minutes} minuti"
        return f"{cycle_seconds}s"

    def _calculate_adaptive_cycle(self) -> int:
        if not self.cfg.enable_adaptive_cycle:
            return self.cfg.default_cycle_sec

        # Per trend trading 4H/1D, manteniamo ciclo fisso a 30 minuti
        # per timing ottimale su timeframe 1H
        return self.cfg.default_cycle_sec

    def _run_trading_cycle(self) -> bool:
        cycle_start = time.time()
        self._cycle_count += 1
        self.orchestrator.set_cycle_count(self._cycle_count)
        try:
            logging.info("=" * 60)
            logging.info(
                f"Starting trading cycle #{self._cycle_count} "
                f"({self._format_cycle_label(self._next_cycle_sec)})"
            )

            self.orchestrator._run_health_check(self._cycle_count)

            portfolio = self.orchestrator._fetch_portfolio()
            self._last_portfolio = portfolio

            write_live_status(
                is_running=True, execution_mode=self.cfg.execution_mode,
                cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration,
                portfolio=portfolio, current_coin="scanning..."
            )

            if portfolio.total_balance <= 0:
                logging.warning("Portfolio balance zero or negative, skipping cycle")
                return True

            state = self.state_store.load_state()

            # Equity snapshot
            self.state_store.add_equity_snapshot(
                state, balance=portfolio.total_balance,
                unrealized_pnl=portfolio.get_total_unrealized_pnl(),
                position_count=len(portfolio.positions), margin_usage=portfolio.margin_usage,
            )

            daily_key = self.state_store.day_key(time.time())
            daily_notional_used = Decimal(str(state.get("daily_notional_by_day", {}).get(daily_key, "0")))
            peak = Decimal(str(state.get("peak_portfolio_value", "0")))
            consecutive_losses = state.get("consecutive_losses", 0)

            # SL/TP/Trailing
            triggered = self.orchestrator._process_risk_triggers(portfolio)
            if triggered > 0:
                logging.info(f"SL/TP/Trailing/BE triggered {triggered} closes, refreshing portfolio")
                portfolio = self.orchestrator._fetch_portfolio()
                self._last_portfolio = portfolio

            # Emergency de-risk (returns updated portfolio)
            portfolio = self.orchestrator._handle_emergency_derisk(portfolio)
            self._last_portfolio = portfolio

            # Analyze & trade — returns (trades_executed, notional_added_this_cycle)
            trades_executed, notional_added = self.orchestrator._analyze_and_trade(
                portfolio, state, daily_notional_used, peak, consecutive_losses, self._shutdown_requested
            )

            # Persist state — add only the delta notional from this cycle
            if notional_added > 0:
                state["daily_notional_by_day"] = self.state_store.add_daily_notional(
                    state.get("daily_notional_by_day", {}), time.time(), notional_added
                )
            if portfolio.total_balance > peak:
                state["peak_portfolio_value"] = str(portfolio.total_balance)
                self.metrics.set_gauge("peak_portfolio_value", portfolio.total_balance)
            state["consecutive_failed_cycles"] = 0
            self.state_store.save_state(state)

            # Metrics
            cycle_duration = time.time() - cycle_start
            self._last_cycle_duration = cycle_duration
            self.metrics.record_histogram("cycle_duration_seconds", cycle_duration)
            self.metrics.increment("cycles_total")
            self._persist_metrics()

            summary = self.state_store.get_performance_summary(state)
            if summary["total_trades"] > 0:
                logging.info(
                    f"Performance: {summary['total_trades']} trades, "
                    f"win_rate={summary['win_rate']:.1f}%, wins={summary['wins']}, "
                    f"losses={summary['losses']}, holds={summary['holds']}"
                )

            self._next_cycle_sec = self._calculate_adaptive_cycle()

            write_live_status(
                is_running=True, execution_mode=self.cfg.execution_mode,
                cycle_count=self._cycle_count, last_cycle_duration=cycle_duration,
                portfolio=portfolio, current_coin="idle"
            )
            logging.info(f"Cycle #{self._cycle_count} complete: {trades_executed} trades, duration={cycle_duration:.1f}s, next_cycle={self._next_cycle_sec}s")
            return True

        except Exception as e:
            logging.error(f"Cycle failed: {type(e).__name__}: {e}", exc_info=True)
            self.metrics.increment("cycles_failed")
            self.notifier.notify_error(f"Cycle failed: {type(e).__name__}: {str(e)[:200]}")
            write_live_status(
                is_running=True, execution_mode=self.cfg.execution_mode,
                cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration,
                portfolio=self._last_portfolio, error=f"{type(e).__name__}: {str(e)[:200]}"
            )
            state = self.state_store.load_state()
            state["consecutive_failed_cycles"] = state.get("consecutive_failed_cycles", 0) + 1
            self.state_store.save_state(state)
            return False

    def _persist_metrics(self):
        metrics_data = self.metrics.get_all_metrics()
        serializable = {}
        for key, value in metrics_data.items():
            if isinstance(value, Decimal):
                serializable[key] = str(value)
            elif isinstance(value, list):
                serializable[key] = [float(v) if isinstance(v, (Decimal, float)) else v for v in value]
            else:
                serializable[key] = value
        self.state_store.save_metrics(serializable)

    def run(self, single_cycle: bool = False):
        logging.info("=" * 60)
        logging.info("HYPERLIQUID TRADING BOT STARTED - TREND 4H/1D ULTRA-CONSERVATIVO")
        logging.info("=" * 60)
        logging.info(f"Wallet: {self.cfg.mask_wallet(self.cfg.wallet_address)}")
        logging.info(f"Execution mode: {self.cfg.execution_mode}")
        logging.info(f"Mainnet trading: {self.cfg.enable_mainnet_trading}")
        logging.info(f"LLM model: {self.cfg.llm_model}")
        logging.info(f"Trading pairs ({len(self.cfg.trading_pairs)}): {self.cfg.trading_pairs}")
        logging.info(
            f"Strategy: Trend 4H/1D Ultra-Conservativo\n"
            f"  • Ciclo base: {self._format_cycle_label(self.cfg.default_cycle_sec)}\n"
            f"  • SL Trend: {float(self.cfg.trend_sl_pct)*100}% / TP Trend: {float(self.cfg.trend_tp_pct)*100}% (R:R 1:2)\n"
            f"  • Position Size: {float(self.cfg.trend_position_size_pct)*100}% del portfolio\n"
            f"  • Max Trend Positions: {self.cfg.max_trend_positions}\n"
            f"  • Max Leverage: {self.cfg.hard_max_leverage}x\n"
            f"  • Max Drawdown: {float(self.cfg.max_drawdown_pct)*100}%\n"
            f"  • Daily Limit: ${self.cfg.daily_notional_limit_usd}"
        )
        logging.info(f"Adaptive cycle: {self.cfg.enable_adaptive_cycle} ({self.cfg.min_cycle_sec}-{self.cfg.max_cycle_sec}s)")
        logging.info(f"Telegram: {'enabled' if self.notifier.telegram_enabled else 'disabled'}")
        logging.info("=" * 60)

        health_result = self.health_monitor.run_all_checks()
        logging.info(f"Startup health check: {health_result['status']} ({health_result['summary']})")

        self.notifier.notify_bot_started(self.cfg.execution_mode, self.cfg.trading_pairs)
        write_live_status(is_running=True, execution_mode=self.cfg.execution_mode, cycle_count=0, last_cycle_duration=0.0, current_coin="starting...")

        meta = self.exchange_client.get_meta(force_refresh=True)
        if meta:
            logging.info(f"Hyperliquid connected: {len(meta.get('universe', []))} assets available")
        else:
            logging.error("FAILED to connect to Hyperliquid API at startup!")
            self.notifier.notify_error("Failed to connect to Hyperliquid API at startup")
            if not single_cycle:
                write_live_status(is_running=False, execution_mode=self.cfg.execution_mode, cycle_count=0, last_cycle_duration=0.0, error="Failed to connect to Hyperliquid API")
                return

        self._apply_runtime_config(force=True)
        consecutive_failures = 0

        while not self._shutdown_requested:
            self._apply_runtime_config()

            if self._run_trading_cycle():
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logging.warning(f"Consecutive failures: {consecutive_failures}/{self.cfg.max_consecutive_failed_cycles}")
                if consecutive_failures >= self.cfg.max_consecutive_failed_cycles:
                    logging.error("Too many consecutive failures, shutting down")
                    self.notifier.notify_error(f"Bot shutdown: {consecutive_failures} consecutive failures")
                    break
            if single_cycle:
                logging.info("Single cycle mode: exiting")
                break
            for _ in range(self._next_cycle_sec):
                if self._shutdown_requested:
                    break
                time.sleep(1)

        logging.info("=" * 60)
        logging.info("BOT GRACEFUL SHUTDOWN")
        state = self.state_store.load_state()
        self.state_store.save_state(state)
        self._persist_metrics()
        self.notifier.notify_bot_stopped("graceful_shutdown")
        write_live_status(
            is_running=False, execution_mode=self.cfg.execution_mode,
            cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration,
            portfolio=self._last_portfolio, current_coin="stopped"
        )
        logging.info("State saved. Goodbye.")
        logging.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Hyperliquid Trading Bot — DeepSeek v3.2 - Trend 4H/1D Ultra-Conservativo")
    parser.add_argument("--single-cycle", action="store_true", help="Run single cycle and exit")
    args = parser.parse_args()
    bot = HyperliquidBot()
    bot.run(single_cycle=args.single_cycle)


if __name__ == "__main__":
    main()