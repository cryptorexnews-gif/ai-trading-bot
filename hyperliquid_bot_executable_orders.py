#!/usr/bin/env python3
"""
Hyperliquid Trading Bot - Executable Orders Version
Main bot script with LLM-powered trading decisions.
"""

import logging
import os
import sys
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# Local imports
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
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")  # For LLM if needed
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
    """Main trading bot class."""

    def __init__(self):
        self._validate_config()
        self._setup_logging()
        self._init_components()
        self._mask_wallet = lambda addr: f"{addr[:6]}...{addr[-4:]}" if addr else "unknown"

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
        log_file = "logs/hyperliquid_bot.log"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        setup_logging(log_level="INFO", json_format=True, log_file=log_file, console_output=True)

    def _init_components(self):
        """Initialize bot components."""
        self.exchange_client = HyperliquidExchangeClient(
            base_url="https://api.hyperliquid.xyz",
            private_key=HYPERLIQUID_PRIVATE_KEY,
            enable_mainnet_trading=ENABLE_MAINNET_TRADING,
            execution_mode=EXECUTION_MODE,
            meta_cache_ttl_sec=META_CACHE_TTL_SEC,
            paper_slippage_bps=PAPER_SLIPPAGE_BPS
        )
        self.llm_engine = LLMEngine(api_key=DEEPSEEK_API_KEY) if ALLOW_EXTERNAL_LLM else None
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
        """Fetch current portfolio state."""
        user_state = self.exchange_client.get_user_state(self.wallet_address)
        if not user_state:
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
            if coin:
                positions[coin] = {
                    "size": Decimal(str(pos_data.get("szi", 0))),
                    "entry_price": Decimal(str(pos_data.get("entryPx", 0))),
                    "unrealized_pnl": Decimal(str(pos_data.get("unrealizedPnl", 0)))
                }

        return PortfolioState(total_balance, available_balance, margin_usage, positions)

    def _get_market_data(self, coin: str) -> Optional[MarketData]:
        """Fetch market data for a coin."""
        tech_data = technical_fetcher.get_technical_indicators(coin)
        if not tech_data:
            return None

        oi_funding = technical_fetcher.get_open_interest_and_funding(coin)
        funding_rate = Decimal(oi_funding.get("funding_rate", "0.01").rstrip("%")) / 100

        return MarketData(
            coin=coin,
            last_price=tech_data["current_price"],
            change_24h=tech_data["change_24h"],
            volume_24h=tech_data["volume_24h"],
            funding_rate=funding_rate,
            timestamp=time.time()
        )

    def _get_fallback_decision(self) -> Dict[str, Any]:
        """Fallback decision when LLM is disabled or fails."""
        if SAFE_FALLBACK_MODE == "de_risk":
            return {"action": "hold", "size": Decimal("0"), "leverage": 1, "confidence": Decimal("0.5"), "reasoning": "Fallback: hold for safety"}
        return {"action": "hold", "size": Decimal("0"), "leverage": 1, "confidence": Decimal("0.5"), "reasoning": "Fallback: hold"}

    def _run_trading_cycle(self) -> bool:
        """Run a single trading cycle."""
        cycle_start = time.time()
        success = True

        try:
            portfolio_state = self._get_portfolio_state()
            state = self.state_store.load_state()
            metrics = self.state_store.load_metrics()

            trades_executed = 0
            daily_notional_used = Decimal(str(state.get("daily_notional_total", "0")))

            for coin in TRADING_PAIRS:
                if trades_executed >= MAX_TRADES_PER_CYCLE:
                    break

                market_data = self._get_market_data(coin)
                if not market_data:
                    continue

                # Get decision from LLM or fallback
                if self.llm_engine:
                    decision = self.llm_engine.get_trading_decision(market_data, portfolio_state)
                else:
                    decision = self._get_fallback_decision()

                if not decision:
                    decision = self._get_fallback_decision()

                # Risk check
                volatility = Decimal("0.05")  # Placeholder; could calculate from ATR
                risk_ok, risk_reason = self.risk_manager.check_order(
                    coin, decision, market_data.last_price, portfolio_state,
                    state.get("last_trade_timestamp_by_coin", {}),
                    daily_notional_used, time.time(), volatility
                )

                if not risk_ok:
                    self.metrics.increment("risk_rejections_total")
                    continue

                # Execute
                result = self.execution_engine.execute(coin, decision, market_data, portfolio_state.positions)
                if result["success"]:
                    trades_executed += 1
                    daily_notional_used += Decimal(str(result["notional"]))
                    state["last_trade_timestamp_by_coin"][coin] = time.time()
                    self.metrics.increment("trades_executed_total")
                else:
                    self.metrics.increment("execution_failures_total")

            # Update state
            state["daily_notional_total"] = str(daily_notional_used)
            self.state_store.save_state(state)
            self.state_store.save_metrics(metrics)

            cycle_duration = time.time() - cycle_start
            self.metrics.record_histogram("cycle_duration_seconds", cycle_duration)
            self.metrics.increment("cycles_total")

        except Exception as e:
            logging.error(f"Cycle failed: {e}")
            success = False
            self.metrics.increment("cycles_failed")

        return success

    def run(self, single_cycle: bool = False):
        """Main run loop."""
        logging.info(f"Bot initialized for wallet {self._mask_wallet(self.wallet_address)}")
        logging.info(f"Execution mode: {EXECUTION_MODE}")
        logging.info(f"Trading pairs: {TRADING_PAIRS}")
        logging.info(f"Fallback mode: {SAFE_FALLBACK_MODE}")
        logging.info(f"LLM enabled: {ALLOW_EXTERNAL_LLM}")

        consecutive_failures = 0

        while True:
            if self._run_trading_cycle():
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILED_CYCLES:
                    logging.error("Too many consecutive failures, shutting down")
                    break

            if single_cycle:
                break

            time.sleep(60)  # Wait 1 minute between cycles


def main():
    """Entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Hyperliquid Trading Bot")
    parser.add_argument("--single-cycle", action="store_true", help="Run single cycle and exit")
    args = parser.parse_args()

    bot = HyperliquidBot()
    bot.run(single_cycle=args.single_cycle)


if __name__ == "__main__":
    main()