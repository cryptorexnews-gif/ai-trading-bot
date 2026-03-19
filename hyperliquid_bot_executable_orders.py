#!/usr/bin/env python3
"""
Hyperliquid Trading Bot - Executable Orders Version
Main bot script with Claude Opus 4.6 powered trading decisions.
All market data sourced exclusively from Hyperliquid API.
"""

import logging
import os
import signal
import sys
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from exchange_client import HyperliquidExchangeClient
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import MarketData, PortfolioState
from risk_manager import RiskManager
from state_store import StateStore
from technical_analyzer_simple import technical_fetcher
from utils.logging_config import setup_logging
from utils.metrics import MetricsCollector
from utils.validation import validate_configuration

load_dotenv()

# Configuration from environment
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "paper").lower()
ENABLE_MAINNET_TRADING = os.getenv("ENABLE_MAINNET_TRADING", "false").lower() == "true"
SAFE_FALLBACK_MODE = os.getenv("SAFE_FALLBACK_MODE", "de_risk").lower()
ALLOW_EXTERNAL_LLM = os.getenv("ALLOW_EXTERNAL_LLM", "true").lower() == "true"
LLM_INCLUDE_PORTFOLIO_CONTEXT = os.getenv("LLM_INCLUDE_PORTFOLIO_CONTEXT", "true").lower() == "true"
HYPERLIQUID_PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY")
HYPERLIQUID_WALLET_ADDRESS = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
HYPERLIQUID_BASE_URL = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
HYPERLIQUID_INFO_TIMEOUT = int(os.getenv("HYPERLIQUID_INFO_TIMEOUT", "15"))
HYPERLIQUID_EXCHANGE_TIMEOUT = int(os.getenv("HYPERLIQUID_EXCHANGE_TIMEOUT", "30"))

# LLM Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-opus-4.6")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8192"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# Risk Management
MAX_ORDER_MARGIN_PCT = Decimal(os.getenv("MAX_ORDER_MARGIN_PCT", "0.1"))
HARD_MAX_LEVERAGE = Decimal(os.getenv("HARD_MAX_LEVERAGE", "10"))
MIN_CONFIDENCE_OPEN = Decimal(os.getenv("MIN_CONFIDENCE_OPEN", "0.7"))
MIN_CONFIDENCE_MANAGE = Decimal(os.getenv("MIN_CONFIDENCE_MANAGE", "0.5"))
MAX_MARGIN_USAGE = Decimal(os.getenv("MAX_MARGIN_USAGE", "0.8"))
TRADE_COOLDOWN_SEC = int(os.getenv("TRADE_COOLDOWN_SEC", "300"))
DAILY_NOTIONAL_LIMIT_USD = Decimal(os.getenv("DAILY_NOTIONAL_LIMIT_USD", "1000"))
MAX_TRADES_PER_CYCLE = int(os.getenv("MAX_TRADES_PER_CYCLE", "5"))
MAX_CONSECUTIVE_FAILED_CYCLES = int(os.getenv("MAX_CONSECUTIVE_FAILED_CYCLES", "10"))
META_CACHE_TTL_SEC = int(os.getenv("META_CACHE_TTL_SEC", "300"))
MAX_MARKET_DATA_AGE_SEC = int(os.getenv("MAX_MARKET_DATA_AGE_SEC", "300"))
PAPER_SLIPPAGE_BPS = Decimal(os.getenv("PAPER_SLIPPAGE_BPS", "50"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/hyperliquid_bot.log")
LOG_JSON_FORMAT = os.getenv("LOG_JSON_FORMAT", "true").lower() == "true"

# Trading pairs
TRADING_PAIRS = ["BTC", "ETH", "SOL", "BNB", "ADA"]

# Minimum sizes by coin
MIN_SIZE_BY_COIN = {
    "BTC": Decimal("0.001"),
    "ETH": Decimal("0.001"),
    "SOL": Decimal("0.1"),
    "BNB": Decimal("0.001"),
    "ADA": Decimal("16.0")
}


class HyperliquidBot:
    """Main trading bot class using Claude Opus 4.6 and Hyperliquid-only data."""

    def __init__(self):
        self._shutdown_requested = False
        self._setup_logging()
        self._validate_config()
        self._init_components()
        self._setup_signal_handlers()
        self._mask_wallet = lambda addr: f"{addr[:6]}...{addr[-4:]}" if addr and len(addr) >= 10 else "unknown"

    def _setup_signal_handlers(self):
        """Setup graceful shutdown on SIGINT/SIGTERM."""
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal gracefully."""
        sig_name = signal.Signals(signum).name
        logging.info(f"Received {sig_name}, initiating graceful shutdown...")
        self._shutdown_requested = True

    def _validate_config(self):
        """Validate configuration at startup."""
        config = {
            "EXECUTION_MODE": EXECUTION_MODE,
            "ENABLE_MAINNET_TRADING": str(ENABLE_MAINNET_TRADING).lower(),
            "SAFE_FALLBACK_MODE": SAFE_FALLBACK_MODE,
            "ALLOW_EXTERNAL_LLM": str(ALLOW_EXTERNAL_LLM).lower(),
            "LLM_INCLUDE_PORTFOLIO_CONTEXT": str(LLM_INCLUDE_PORTFOLIO_CONTEXT).lower(),
            "MAX_ORDER_MARGIN_PCT": str(MAX_ORDER_MARGIN_PCT),
            "HARD_MAX_LEVERAGE": str(HARD_MAX_LEVERAGE),
            "MIN_CONFIDENCE_OPEN": str(MIN_CONFIDENCE_OPEN),
            "MIN_CONFIDENCE_MANAGE": str(MIN_CONFIDENCE_MANAGE),
            "MAX_MARGIN_USAGE": str(MAX_MARGIN_USAGE),
            "TRADE_COOLDOWN_SEC": str(TRADE_COOLDOWN_SEC),
            "DAILY_NOTIONAL_LIMIT_USD": str(DAILY_NOTIONAL_LIMIT_USD),
            "MAX_TRADES_PER_CYCLE": str(MAX_TRADES_PER_CYCLE),
            "MAX_CONSECUTIVE_FAILED_CYCLES": str(MAX_CONSECUTIVE_FAILED_CYCLES),
            "META_CACHE_TTL_SEC": str(META_CACHE_TTL_SEC),
            "MAX_MARKET_DATA_AGE_SEC": str(MAX_MARKET_DATA_AGE_SEC),
            "PAPER_SLIPPAGE_BPS": str(PAPER_SLIPPAGE_BPS)
        }
        validate_configuration(config)

    def _setup_logging(self):
        """Setup logging configuration."""
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        setup_logging(
            log_level=LOG_LEVEL,
            json_format=LOG_JSON_FORMAT,
            log_file=LOG_FILE,
            console_output=True
        )

    def _init_components(self):
        """Initialize bot components."""
        self.exchange_client = HyperliquidExchangeClient(
            base_url=HYPERLIQUID_BASE_URL,
            private_key=HYPERLIQUID_PRIVATE_KEY,
            enable_mainnet_trading=ENABLE_MAINNET_TRADING,
            execution_mode=EXECUTION_MODE,
            meta_cache_ttl_sec=META_CACHE_TTL_SEC,
            paper_slippage_bps=PAPER_SLIPPAGE_BPS,
            info_timeout=HYPERLIQUID_INFO_TIMEOUT,
            exchange_timeout=HYPERLIQUID_EXCHANGE_TIMEOUT
        )

        if ALLOW_EXTERNAL_LLM and OPENROUTER_API_KEY:
            self.llm_engine = LLMEngine(
                api_key=OPENROUTER_API_KEY,
                base_url="https://openrouter.ai/api/v1",
                model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE
            )
            logging.info(f"LLM Engine initialized with model: {LLM_MODEL}")
        else:
            self.llm_engine = None
            logging.warning("LLM Engine disabled: ALLOW_EXTERNAL_LLM=false or OPENROUTER_API_KEY missing")

        self.risk_manager = RiskManager(
            min_size_by_coin=MIN_SIZE_BY_COIN,
            hard_max_leverage=HARD_MAX_LEVERAGE,
            min_confidence_open=MIN_CONFIDENCE_OPEN,
            min_confidence_manage=MIN_CONFIDENCE_MANAGE,
            max_margin_usage=MAX_MARGIN_USAGE,
            max_order_margin_pct=MAX_ORDER_MARGIN_PCT,
            trade_cooldown_sec=TRADE_COOLDOWN_SEC,
            daily_notional_limit_usd=DAILY_NOTIONAL_LIMIT_USD
        )
        self.execution_engine = ExecutionEngine(self.exchange_client)
        self.state_store = StateStore("state/bot_state.json", "state/bot_metrics.json")
        self.metrics = MetricsCollector()
        self.wallet_address = HYPERLIQUID_WALLET_ADDRESS

    def _get_portfolio_state(self) -> PortfolioState:
        """Fetch current portfolio state from Hyperliquid."""
        user_state = self.exchange_client.get_user_state(self.wallet_address)
        if not user_state:
            logging.warning("Could not fetch user state from Hyperliquid")
            return PortfolioState(Decimal("0"), Decimal("0"), Decimal("0"), {})

        margin_summary = user_state.get("marginSummary", {})
        total_balance = Decimal(str(margin_summary.get("accountValue", 0)))
        available_balance = Decimal(str(margin_summary.get("withdrawable", 0)))
        total_margin_used = Decimal(str(margin_summary.get("totalMarginUsed", 0)))
        margin_usage = (total_margin_used / total_balance) if total_balance > 0 else Decimal("0")

        positions = {}
        for pos in user_state.get("assetPositions", []):
            pos_data = pos.get("position", {})
            coin = pos_data.get("coin", "")
            size = Decimal(str(pos_data.get("szi", 0)))
            if coin and size != 0:
                positions[coin] = {
                    "size": size,
                    "entry_price": Decimal(str(pos_data.get("entryPx", 0))),
                    "unrealized_pnl": Decimal(str(pos_data.get("unrealizedPnl", 0))),
                    "margin_used": Decimal(str(pos_data.get("marginUsed", 0)))
                }

        self.metrics.set_gauge("current_balance", total_balance)
        self.metrics.set_gauge("available_balance", available_balance)
        self.metrics.set_gauge("margin_usage", margin_usage)
        self.metrics.set_gauge("open_positions_count", len(positions))

        return PortfolioState(total_balance, available_balance, margin_usage, positions)

    def _get_market_data_and_technicals(self, coin: str):
        """
        Fetch market data and technical indicators for a coin in a single call.
        Returns (MarketData, tech_data_dict) or (None, None) on failure.
        """
        tech_data = technical_fetcher.get_technical_indicators(coin)
        if not tech_data:
            logging.warning(f"No technical data available for {coin}")
            return None, None

        funding_rate = tech_data.get("funding_rate", Decimal("0"))

        market_data = MarketData(
            coin=coin,
            last_price=tech_data["current_price"],
            change_24h=tech_data["change_24h"],
            volume_24h=tech_data["volume_24h"],
            funding_rate=funding_rate,
            timestamp=time.time()
        )

        return market_data, tech_data

    def _get_fallback_decision(self) -> Dict[str, Any]:
        """Fallback decision when LLM is disabled or fails."""
        return {
            "action": "hold",
            "size": Decimal("0"),
            "leverage": 1,
            "confidence": Decimal("0.5"),
            "reasoning": f"Fallback: {SAFE_FALLBACK_MODE} mode - holding for safety"
        }

    def _get_daily_notional_used(self, state: Dict[str, Any]) -> Decimal:
        """Get today's notional usage, resetting if it's a new day."""
        today_key = self.state_store.day_key(time.time())
        daily_by_day = state.get("daily_notional_by_day", {})
        return Decimal(str(daily_by_day.get(today_key, "0")))

    def _run_trading_cycle(self) -> bool:
        """Run a single trading cycle."""
        cycle_start = time.time()
        success = True

        try:
            logging.info("=" * 60)
            logging.info("Starting new trading cycle")

            # Fetch portfolio state from Hyperliquid
            portfolio_state = self._get_portfolio_state()
            logging.info(
                f"Portfolio: balance=${portfolio_state.total_balance}, "
                f"available=${portfolio_state.available_balance}, "
                f"margin_usage={float(portfolio_state.margin_usage) * 100:.1f}%, "
                f"positions={len(portfolio_state.positions)}"
            )

            if portfolio_state.total_balance <= 0:
                logging.warning("Portfolio balance is zero or negative, skipping cycle")
                return True

            state = self.state_store.load_state()
            daily_notional_used = self._get_daily_notional_used(state)

            # Get all mid prices from Hyperliquid for market overview
            all_mids = technical_fetcher.get_all_mids()

            trades_executed = 0

            for coin in TRADING_PAIRS:
                if self._shutdown_requested:
                    logging.info("Shutdown requested, stopping coin analysis")
                    break

                if trades_executed >= MAX_TRADES_PER_CYCLE:
                    logging.info(f"Max trades per cycle ({MAX_TRADES_PER_CYCLE}) reached")
                    break

                logging.info(f"--- Analyzing {coin} ---")

                # Get market data AND technical indicators in one call (no duplicate)
                market_data, tech_data = self._get_market_data_and_technicals(coin)
                if not market_data:
                    logging.warning(f"Skipping {coin}: no market data")
                    continue

                logging.info(
                    f"{coin}: price=${market_data.last_price}, "
                    f"24h_change={float(market_data.change_24h) * 100:.2f}%, "
                    f"funding={float(market_data.funding_rate):.6f}%"
                )

                # Get funding data from Hyperliquid
                funding_data = technical_fetcher.get_funding_for_coin(coin)

                # Get decision from Claude Opus 4.6 or fallback
                if self.llm_engine:
                    self.metrics.increment("llm_calls_total")
                    decision = self.llm_engine.get_trading_decision(
                        market_data=market_data,
                        portfolio_state=portfolio_state,
                        technical_data=tech_data,
                        all_mids=all_mids,
                        funding_data=funding_data
                    )
                    if not decision:
                        self.metrics.increment("llm_errors_total")
                        decision = self._get_fallback_decision()
                        logging.warning(f"LLM failed for {coin}, using fallback")
                else:
                    decision = self._get_fallback_decision()

                logging.info(
                    f"{coin} decision: action={decision['action']}, "
                    f"size={decision['size']}, leverage={decision['leverage']}, "
                    f"confidence={decision['confidence']}"
                )

                # Risk check (may adjust size in-place for volatility)
                volatility = Decimal("0")
                if tech_data and tech_data.get("intraday_atr", Decimal("0")) > 0 and market_data.last_price > 0:
                    volatility = tech_data["intraday_atr"] / market_data.last_price

                risk_ok, risk_reason = self.risk_manager.check_order(
                    coin, decision, market_data.last_price, portfolio_state,
                    state.get("last_trade_timestamp_by_coin", {}),
                    daily_notional_used, time.time(), volatility
                )

                if not risk_ok:
                    logging.info(f"{coin} risk rejected: {risk_reason}")
                    self.metrics.increment("risk_rejections_total")
                    continue

                # Execute (decision['size'] may have been adjusted by risk manager)
                result = self.execution_engine.execute(
                    coin, decision, market_data, portfolio_state.positions
                )

                if result["success"]:
                    notional = Decimal(str(result["notional"]))
                    if notional > 0:
                        trades_executed += 1
                        daily_notional_used += notional
                        state.setdefault("last_trade_timestamp_by_coin", {})[coin] = time.time()
                        self.metrics.increment("trades_executed_total")
                        logging.info(
                            f"{coin} executed: reason={result['reason']}, notional=${notional}"
                        )
                    else:
                        self.metrics.increment("holds_total")
                        logging.info(f"{coin}: hold (no trade)")
                else:
                    self.metrics.increment("execution_failures_total")
                    logging.warning(f"{coin} execution failed: {result.get('reason', 'unknown')}")

            # Update state with proper daily tracking
            state["daily_notional_by_day"] = self.state_store.add_daily_notional(
                state.get("daily_notional_by_day", {}),
                time.time(),
                daily_notional_used - self._get_daily_notional_used(state)
            )
            # Update peak portfolio value
            peak = Decimal(str(state.get("peak_portfolio_value", "0")))
            if portfolio_state.total_balance > peak:
                state["peak_portfolio_value"] = str(portfolio_state.total_balance)
                self.metrics.set_gauge("peak_portfolio_value", portfolio_state.total_balance)

            state["consecutive_failed_cycles"] = 0
            self.state_store.save_state(state)

            cycle_duration = time.time() - cycle_start
            self.metrics.record_histogram("cycle_duration_seconds", cycle_duration)
            self.metrics.increment("cycles_total")

            logging.info(
                f"Cycle complete: {trades_executed} trades, "
                f"duration={cycle_duration:.1f}s, "
                f"daily_notional=${daily_notional_used}"
            )

        except Exception as e:
            logging.error(f"Cycle failed with exception: {type(e).__name__}: {e}", exc_info=True)
            success = False
            self.metrics.increment("cycles_failed")

            # Track consecutive failures in state
            state = self.state_store.load_state()
            state["consecutive_failed_cycles"] = state.get("consecutive_failed_cycles", 0) + 1
            self.state_store.save_state(state)

        return success

    def run(self, single_cycle: bool = False):
        """Main run loop."""
        logging.info("=" * 60)
        logging.info("HYPERLIQUID TRADING BOT STARTING")
        logging.info("=" * 60)
        logging.info(f"Wallet: {self._mask_wallet(self.wallet_address)}")
        logging.info(f"Execution mode: {EXECUTION_MODE}")
        logging.info(f"Mainnet trading: {ENABLE_MAINNET_TRADING}")
        logging.info(f"LLM model: {LLM_MODEL}")
        logging.info(f"LLM enabled: {self.llm_engine is not None}")
        logging.info(f"Trading pairs: {TRADING_PAIRS}")
        logging.info(f"Fallback mode: {SAFE_FALLBACK_MODE}")
        logging.info(f"Data source: Hyperliquid API only")
        logging.info("=" * 60)

        # Verify Hyperliquid connectivity at startup
        meta = self.exchange_client.get_meta(force_refresh=True)
        if meta:
            logging.info(f"Hyperliquid connected: {len(meta.get('universe', []))} assets available")
        else:
            logging.error("FAILED to connect to Hyperliquid API at startup!")
            if not single_cycle:
                logging.error("Aborting: cannot start without Hyperliquid connectivity")
                return

        consecutive_failures = 0

        while not self._shutdown_requested:
            if self._run_trading_cycle():
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logging.warning(
                    f"Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILED_CYCLES}"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILED_CYCLES:
                    logging.error("Too many consecutive failures, shutting down")
                    break

            if single_cycle:
                logging.info("Single cycle mode: exiting")
                break

            # Interruptible sleep
            logging.info("Waiting 60 seconds before next cycle...")
            for _ in range(60):
                if self._shutdown_requested:
                    break
                time.sleep(1)

        # Graceful shutdown
        logging.info("=" * 60)
        logging.info("BOT SHUTTING DOWN GRACEFULLY")
        state = self.state_store.load_state()
        self.state_store.save_state(state)
        logging.info("State saved. Goodbye.")
        logging.info("=" * 60)


def main():
    """Entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Hyperliquid Trading Bot - Claude Opus 4.6")
    parser.add_argument("--single-cycle", action="store_true", help="Run single cycle and exit")
    args = parser.parse_args()

    bot = HyperliquidBot()
    bot.run(single_cycle=args.single_cycle)


if __name__ == "__main__":
    main()