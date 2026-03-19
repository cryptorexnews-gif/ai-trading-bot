#!/usr/bin/env python3
"""
Hyperliquid Trading Bot — Production Entry Point
Uses Claude Opus 4.6 via OpenRouter for AI-driven trading decisions.
All market data sourced exclusively from Hyperliquid API.
"""

import argparse
import logging
import os
import signal
import sys
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

load_dotenv()

from bot_live_writer import write_live_status
from correlation_engine import CorrelationEngine
from exchange_client import HyperliquidExchangeClient
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import MarketData, PortfolioState
from notifier import Notifier
from order_verifier import OrderVerifier
from position_manager import PositionManager
from risk_manager import RiskManager
from state_store import StateStore
from technical_analyzer_simple import technical_fetcher
from utils.health import HealthMonitor, HealthStatus, HealthCheckResult, check_disk_space, check_file_writable
from utils.logging_config import setup_logging
from utils.metrics import MetricsCollector
from utils.rate_limiter import get_rate_limiter

# ─── Configuration from environment ───────────────────────────────────────────

EXECUTION_MODE = os.getenv("EXECUTION_MODE", "paper").lower()
ENABLE_MAINNET_TRADING = os.getenv("ENABLE_MAINNET_TRADING", "false").lower() == "true"

WALLET_ADDRESS = os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
BASE_URL = os.getenv("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")
INFO_TIMEOUT = int(os.getenv("HYPERLIQUID_INFO_TIMEOUT", "15"))
EXCHANGE_TIMEOUT = int(os.getenv("HYPERLIQUID_EXCHANGE_TIMEOUT", "30"))

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-opus-4.6")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8192"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.15"))

TRADING_PAIRS_RAW = os.getenv(
    "TRADING_PAIRS",
    "BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI,ARB,OP,NEAR,WIF,PEPE,INJ,TIA,SEI,RENDER,FET"
).split(",")
TRADING_PAIRS_RAW = [p.strip().upper() for p in TRADING_PAIRS_RAW if p.strip()]

MAX_ORDER_MARGIN_PCT = Decimal(os.getenv("MAX_ORDER_MARGIN_PCT", "0.1"))
HARD_MAX_LEVERAGE = Decimal(os.getenv("HARD_MAX_LEVERAGE", "10"))
MIN_CONFIDENCE_OPEN = Decimal(os.getenv("MIN_CONFIDENCE_OPEN", "0.72"))
MIN_CONFIDENCE_MANAGE = Decimal(os.getenv("MIN_CONFIDENCE_MANAGE", "0.50"))
MAX_MARGIN_USAGE = Decimal(os.getenv("MAX_MARGIN_USAGE", "0.8"))
MAX_DRAWDOWN_PCT = Decimal(os.getenv("MAX_DRAWDOWN_PCT", "0.15"))
MAX_SINGLE_ASSET_PCT = Decimal(os.getenv("MAX_SINGLE_ASSET_PCT", "0.40"))
EMERGENCY_MARGIN_THRESHOLD = Decimal(os.getenv("EMERGENCY_MARGIN_THRESHOLD", "0.88"))
TRADE_COOLDOWN_SEC = int(os.getenv("TRADE_COOLDOWN_SEC", "300"))
DAILY_NOTIONAL_LIMIT_USD = Decimal(os.getenv("DAILY_NOTIONAL_LIMIT_USD", "1000"))
MAX_TRADES_PER_CYCLE = int(os.getenv("MAX_TRADES_PER_CYCLE", "3"))
MAX_CONSECUTIVE_FAILED_CYCLES = int(os.getenv("MAX_CONSECUTIVE_FAILED_CYCLES", "5"))
PAPER_SLIPPAGE_BPS = Decimal(os.getenv("PAPER_SLIPPAGE_BPS", "5"))
VOLATILITY_MULTIPLIER = Decimal(os.getenv("VOLATILITY_MULTIPLIER", "1.2"))
SAFE_FALLBACK_MODE = os.getenv("SAFE_FALLBACK_MODE", "de_risk").lower()

DEFAULT_SL_PCT = Decimal(os.getenv("DEFAULT_SL_PCT", "0.03"))
DEFAULT_TP_PCT = Decimal(os.getenv("DEFAULT_TP_PCT", "0.05"))
DEFAULT_TRAILING_CALLBACK = Decimal(os.getenv("DEFAULT_TRAILING_CALLBACK", "0.02"))
ENABLE_TRAILING_STOP = os.getenv("ENABLE_TRAILING_STOP", "true").lower() == "true"
TRAILING_ACTIVATION_PCT = Decimal(os.getenv("TRAILING_ACTIVATION_PCT", "0.02"))
BREAK_EVEN_ACTIVATION_PCT = Decimal(os.getenv("BREAK_EVEN_ACTIVATION_PCT", "0.015"))
BREAK_EVEN_OFFSET_PCT = Decimal(os.getenv("BREAK_EVEN_OFFSET_PCT", "0.001"))

ENABLE_ADAPTIVE_CYCLE = os.getenv("ENABLE_ADAPTIVE_CYCLE", "true").lower() == "true"
DEFAULT_CYCLE_SEC = int(os.getenv("DEFAULT_CYCLE_SEC", "60"))
MIN_CYCLE_SEC = int(os.getenv("MIN_CYCLE_SEC", "20"))
MAX_CYCLE_SEC = int(os.getenv("MAX_CYCLE_SEC", "180"))

CORRELATION_THRESHOLD = Decimal(os.getenv("CORRELATION_THRESHOLD", "0.7"))

META_CACHE_TTL_SEC = int(os.getenv("META_CACHE_TTL_SEC", "120"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/hyperliquid_bot.log")

STATE_PATH = "state/bot_state.json"
METRICS_PATH = "state/bot_metrics.json"

MIN_SIZE_BY_COIN: Dict[str, Decimal] = {
    "BTC": Decimal("0.001"), "ETH": Decimal("0.01"), "SOL": Decimal("0.1"),
    "BNB": Decimal("0.01"), "XRP": Decimal("1"), "ADA": Decimal("10"),
    "DOGE": Decimal("10"), "AVAX": Decimal("0.1"), "LINK": Decimal("0.1"),
    "NEAR": Decimal("1"), "SUI": Decimal("1"), "ARB": Decimal("1"),
    "OP": Decimal("1"), "SEI": Decimal("1"), "TIA": Decimal("0.1"),
    "INJ": Decimal("0.01"), "WIF": Decimal("1"), "PEPE": Decimal("100000"),
    "RENDER": Decimal("0.1"), "FET": Decimal("1"),
}
DEFAULT_MIN_SIZE = Decimal("1")


def _validate_startup_config() -> List[str]:
    warnings = []
    if not WALLET_ADDRESS:
        raise SystemExit("CRITICAL: HYPERLIQUID_WALLET_ADDRESS not set")
    if not PRIVATE_KEY:
        raise SystemExit("CRITICAL: HYPERLIQUID_PRIVATE_KEY not set")
    if EXECUTION_MODE == "live" and not ENABLE_MAINNET_TRADING:
        warnings.append("EXECUTION_MODE=live but ENABLE_MAINNET_TRADING=false — orders will be paper")
    if EXECUTION_MODE not in ("paper", "live"):
        warnings.append(f"Unknown EXECUTION_MODE '{EXECUTION_MODE}', defaulting to paper behavior")
    if MAX_DRAWDOWN_PCT > Decimal("0.30"):
        warnings.append(f"MAX_DRAWDOWN_PCT={MAX_DRAWDOWN_PCT} is very high (>30%)")
    if HARD_MAX_LEVERAGE > Decimal("20"):
        warnings.append(f"HARD_MAX_LEVERAGE={HARD_MAX_LEVERAGE} is very high (>20x)")
    if not OPENROUTER_API_KEY:
        warnings.append("OPENROUTER_API_KEY not set — LLM disabled, using fallback only")
    if DAILY_NOTIONAL_LIMIT_USD < Decimal("10"):
        warnings.append(f"DAILY_NOTIONAL_LIMIT_USD={DAILY_NOTIONAL_LIMIT_USD} is very low")
    return warnings


class HyperliquidBot:
    def __init__(self):
        setup_logging(log_level=LOG_LEVEL, json_format=True, log_file=LOG_FILE, console_output=True)
        config_warnings = _validate_startup_config()
        for warning in config_warnings:
            logging.warning(f"CONFIG WARNING: {warning}")

        self.wallet_address = WALLET_ADDRESS
        self._cycle_count = 0
        self._last_cycle_duration = 0.0
        self._next_cycle_sec = DEFAULT_CYCLE_SEC
        self._shutdown_requested = False
        self._last_portfolio_state: Optional[PortfolioState] = None
        self._dynamic_min_sizes: Dict[str, Decimal] = {}
        self._trading_pairs: List[str] = list(TRADING_PAIRS_RAW)

        self._hl_rate_limiter = get_rate_limiter("hyperliquid_api", max_tokens=20, tokens_per_second=2.0)
        self._llm_rate_limiter = get_rate_limiter("openrouter_api", max_tokens=5, tokens_per_second=0.5)

        self.exchange_client = HyperliquidExchangeClient(
            base_url=BASE_URL, private_key=PRIVATE_KEY,
            enable_mainnet_trading=ENABLE_MAINNET_TRADING, execution_mode=EXECUTION_MODE,
            meta_cache_ttl_sec=META_CACHE_TTL_SEC, paper_slippage_bps=PAPER_SLIPPAGE_BPS,
            info_timeout=INFO_TIMEOUT, exchange_timeout=EXCHANGE_TIMEOUT,
        )
        self.execution_engine = ExecutionEngine(self.exchange_client)
        self.risk_manager = RiskManager(
            min_size_by_coin=MIN_SIZE_BY_COIN, hard_max_leverage=HARD_MAX_LEVERAGE,
            min_confidence_open=MIN_CONFIDENCE_OPEN, min_confidence_manage=MIN_CONFIDENCE_MANAGE,
            max_margin_usage=MAX_MARGIN_USAGE, max_order_margin_pct=MAX_ORDER_MARGIN_PCT,
            trade_cooldown_sec=TRADE_COOLDOWN_SEC, daily_notional_limit_usd=DAILY_NOTIONAL_LIMIT_USD,
            volatility_multiplier=VOLATILITY_MULTIPLIER, max_drawdown_pct=MAX_DRAWDOWN_PCT,
            max_single_asset_pct=MAX_SINGLE_ASSET_PCT, emergency_margin_threshold=EMERGENCY_MARGIN_THRESHOLD,
        )
        self.state_store = StateStore(STATE_PATH, METRICS_PATH)
        self.metrics = MetricsCollector()
        self.position_manager = PositionManager(
            default_sl_pct=DEFAULT_SL_PCT, default_tp_pct=DEFAULT_TP_PCT,
            default_trailing_callback=DEFAULT_TRAILING_CALLBACK, enable_trailing_stop=ENABLE_TRAILING_STOP,
            trailing_activation_pct=TRAILING_ACTIVATION_PCT,
            break_even_activation_pct=BREAK_EVEN_ACTIVATION_PCT, break_even_offset_pct=BREAK_EVEN_OFFSET_PCT,
        )
        self.correlation_engine = CorrelationEngine(correlation_threshold=CORRELATION_THRESHOLD)
        self.order_verifier = OrderVerifier(exchange_client=self.exchange_client, max_wait_sec=10.0, check_interval=2.0)
        self.notifier = Notifier(enabled=True)
        self.health_monitor = HealthMonitor()
        self._setup_health_checks()

        if OPENROUTER_API_KEY:
            self.llm_engine: Optional[LLMEngine] = LLMEngine(
                api_key=OPENROUTER_API_KEY, model=LLM_MODEL,
                max_tokens=LLM_MAX_TOKENS, temperature=LLM_TEMPERATURE,
            )
        else:
            self.llm_engine = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _setup_health_checks(self) -> None:
        self.health_monitor.add_check("exchange_connectivity", lambda: self._check_exchange_health(), interval=60.0)
        self.health_monitor.add_check("disk_space", lambda: check_disk_space(".", min_free_gb=0.5), interval=300.0)
        self.health_monitor.add_check("state_writable", lambda: check_file_writable("state"), interval=300.0)

    def _check_exchange_health(self) -> HealthCheckResult:
        meta = self.exchange_client.get_meta(force_refresh=True)
        if meta:
            return HealthCheckResult(name="exchange_connectivity", status=HealthStatus.HEALTHY,
                                     message="Hyperliquid API reachable", details={"assets_count": len(meta.get("universe", []))})
        return HealthCheckResult(name="exchange_connectivity", status=HealthStatus.UNHEALTHY, message="Hyperliquid API unreachable")

    def _signal_handler(self, signum, frame):
        logging.info(f"Received {signal.Signals(signum).name}, requesting graceful shutdown...")
        self._shutdown_requested = True

    @staticmethod
    def _mask_wallet(wallet: str) -> str:
        if not wallet or len(wallet) < 12:
            return "invalid"
        return f"{wallet[:6]}...{wallet[-4:]}"

    def _resolve_min_size(self, coin: str) -> Decimal:
        if coin in MIN_SIZE_BY_COIN:
            return MIN_SIZE_BY_COIN[coin]
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
                logging.info(f"Dynamic min size for {coin}: {resolved} (price=${mid_price})")
                return resolved
        logging.warning(f"No min size data for {coin}, using default {DEFAULT_MIN_SIZE}")
        return DEFAULT_MIN_SIZE

    def _validate_trading_pairs(self) -> List[str]:
        meta = self.exchange_client.get_meta(force_refresh=True)
        if not meta:
            logging.warning("Cannot validate trading pairs — meta unavailable")
            return list(TRADING_PAIRS_RAW)
        available_coins = {asset.get("name") for asset in meta.get("universe", [])}
        valid_pairs = [c for c in TRADING_PAIRS_RAW if c in available_coins]
        invalid_pairs = [c for c in TRADING_PAIRS_RAW if c not in available_coins]
        if invalid_pairs:
            logging.warning(f"Trading pairs NOT found on Hyperliquid (removed): {invalid_pairs}")
        logging.info(f"Validated {len(valid_pairs)} trading pairs: {valid_pairs}")
        return valid_pairs

    def _get_portfolio_state(self) -> PortfolioState:
        self._hl_rate_limiter.acquire(1)
        user_state = self.exchange_client.get_user_state(self.wallet_address)
        if not user_state:
            logging.warning("Failed to get user state, returning empty portfolio")
            return PortfolioState(total_balance=Decimal("0"), available_balance=Decimal("0"), margin_usage=Decimal("0"), positions={})
        margin_summary = user_state.get("marginSummary", {})
        total_balance = Decimal(str(margin_summary.get("accountValue", "0")))
        available_balance = Decimal(str(margin_summary.get("withdrawable", "0")))
        total_margin_used = Decimal(str(margin_summary.get("totalMarginUsed", "0")))
        margin_usage = (total_margin_used / total_balance) if total_balance > 0 else Decimal("0")
        positions: Dict[str, Dict[str, Any]] = {}
        for pos_wrapper in user_state.get("assetPositions", []):
            pos = pos_wrapper.get("position", {})
            coin = pos.get("coin", "")
            size = Decimal(str(pos.get("szi", "0")))
            if size != 0 and coin:
                positions[coin] = {
                    "size": size, "entry_price": Decimal(str(pos.get("entryPx", "0"))),
                    "unrealized_pnl": Decimal(str(pos.get("unrealizedPnl", "0"))),
                    "margin_used": Decimal(str(pos.get("marginUsed", "0"))),
                }
        self.metrics.set_gauge("current_balance", total_balance)
        self.metrics.set_gauge("available_balance", available_balance)
        self.metrics.set_gauge("margin_usage", margin_usage)
        self.metrics.set_gauge("open_positions_count", len(positions))
        return PortfolioState(total_balance=total_balance, available_balance=available_balance, margin_usage=margin_usage, positions=positions)

    def _get_market_data_and_technicals(self, coin: str) -> Tuple[Optional[MarketData], Optional[Dict[str, Any]]]:
        self._hl_rate_limiter.acquire(3)
        tech_data = technical_fetcher.get_technical_indicators(coin)
        if not tech_data:
            return None, None
        market_data = MarketData(
            coin=coin, last_price=tech_data["current_price"], change_24h=tech_data["change_24h"],
            volume_24h=tech_data["volume_24h"], funding_rate=tech_data["funding_rate"], timestamp=time.time()
        )
        return market_data, tech_data

    def _get_daily_notional_used(self, state: Dict[str, Any]) -> Decimal:
        day_key = self.state_store.day_key(time.time())
        return Decimal(str(state.get("daily_notional_by_day", {}).get(day_key, "0")))

    def _get_fallback_decision(self) -> Dict[str, Any]:
        return {"action": "hold", "size": Decimal("0"), "leverage": 1, "confidence": 0.0, "reasoning": "LLM unavailable — safe fallback to hold"}

    def _process_sl_tp_trailing(self, portfolio_state: PortfolioState) -> int:
        self.position_manager.sync_with_exchange(portfolio_state.positions)
        mids = technical_fetcher.get_all_mids()
        if not mids:
            return 0
        current_prices: Dict[str, Decimal] = {}
        for coin in portfolio_state.positions:
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
            logging.warning(f"{trigger.upper()} triggered for {coin}: entry=${entry_price}, current=${current_price}, trigger=${trigger_price}")
            pos_size = Decimal(str(portfolio_state.positions[coin]["size"]))
            side = "sell" if pos_size > 0 else "buy"
            close_size = abs(pos_size)
            result = self.exchange_client.place_order(coin, side, close_size, current_price)
            if result.get("success"):
                triggered += 1
                self.position_manager.remove_position(coin)
                if trigger == "stop_loss":
                    self.notifier.notify_stop_loss(coin, entry_price, trigger_price, current_price)
                elif trigger == "take_profit":
                    self.notifier.notify_take_profit(coin, entry_price, trigger_price, current_price)
                elif trigger == "trailing_stop":
                    self.notifier.notify_trailing_stop(coin, entry_price, trigger_price, current_price)
                elif trigger == "break_even_stop":
                    self.notifier.notify_stop_loss(coin, entry_price, trigger_price, current_price)
                state = self.state_store.load_state()
                trade_record = {
                    "timestamp": time.time(), "coin": coin, "action": "close_position",
                    "size": str(close_size), "price": str(current_price),
                    "notional": str(result.get("notional", "0")), "leverage": 1, "confidence": 1.0,
                    "reasoning": action_info.get("reasoning", ""), "success": True,
                    "mode": EXECUTION_MODE, "trigger": trigger, "order_status": "filled",
                }
                self.state_store.add_trade_record(state, trade_record)
                self.state_store.save_state(state)
                self.metrics.increment("trades_executed_total")
                logging.info(f"{trigger.upper()} close executed for {coin}")
            else:
                logging.error(f"Failed to execute {trigger} close for {coin}: {result}")
        return triggered

    def _handle_emergency_derisk(self, portfolio_state: PortfolioState) -> None:
        worst_coin = self.risk_manager.get_emergency_close_coin(portfolio_state)
        if not worst_coin:
            logging.warning("Emergency derisk: no position to close")
            return
        logging.warning(f"EMERGENCY DERISK: closing {worst_coin}")
        self.notifier.notify_emergency_derisk(worst_coin, "margin_usage_critical")
        pos_size = Decimal(str(portfolio_state.positions[worst_coin]["size"]))
        side = "sell" if pos_size > 0 else "buy"
        close_size = abs(pos_size)
        mids = technical_fetcher.get_all_mids()
        current_price = Decimal(str(mids.get(worst_coin, "0"))) if mids and worst_coin in mids else Decimal("0")
        if current_price > 0:
            result = self.exchange_client.place_order(worst_coin, side, close_size, current_price)
            if result.get("success"):
                self.position_manager.remove_position(worst_coin)
                logging.info(f"Emergency close executed for {worst_coin}")
                state = self.state_store.load_state()
                trade_record = {
                    "timestamp": time.time(), "coin": worst_coin, "action": "close_position",
                    "size": str(close_size), "price": str(current_price),
                    "notional": str(result.get("notional", "0")), "leverage": 1, "confidence": 1.0,
                    "reasoning": "Emergency derisk: margin usage critical", "success": True,
                    "mode": EXECUTION_MODE, "trigger": "emergency", "order_status": "filled",
                }
                self.state_store.add_trade_record(state, trade_record)
                self.state_store.save_state(state)
            else:
                logging.error(f"Emergency close FAILED for {worst_coin}: {result}")

    def _calculate_adaptive_cycle(self) -> int:
        if not ENABLE_ADAPTIVE_CYCLE:
            return DEFAULT_CYCLE_SEC
        vol_signal = technical_fetcher.get_volatility_signal(self._trading_pairs[0])
        suggested = vol_signal.get("suggested_cycle_sec", DEFAULT_CYCLE_SEC)
        clamped = max(MIN_CYCLE_SEC, min(MAX_CYCLE_SEC, suggested))
        if clamped != self._next_cycle_sec:
            logging.info(f"Adaptive cycle: {self._next_cycle_sec}s -> {clamped}s (volatility={vol_signal.get('volatility_level', 'unknown')})")
        return clamped

    def _log_performance_summary(self, state: Dict[str, Any]):
        summary = self.state_store.get_performance_summary(state)
        if summary["total_trades"] > 0:
            logging.info(f"Performance: {summary['total_trades']} trades, win_rate={summary['win_rate']:.1f}%, wins={summary['wins']}, losses={summary['losses']}, holds={summary['holds']}, consecutive_losses={summary['consecutive_losses']}")

    def _persist_metrics(self):
        metrics_data = self.metrics.get_all_metrics()
        serializable = {}
        for key, value in metrics_data.items():
            if isinstance(value, Decimal): serializable[key] = str(value)
            elif isinstance(value, list): serializable[key] = [float(v) if isinstance(v, (Decimal, float)) else v for v in value]
            else: serializable[key] = value
        self.state_store.save_metrics(serializable)

    def _run_trading_cycle(self) -> bool:
        cycle_start = time.time()
        self._cycle_count += 1
        success = True
        try:
            logging.info("=" * 60)
            logging.info(f"Starting trading cycle #{self._cycle_count}")

            if self._cycle_count % 10 == 1:
                health_result = self.health_monitor.run_all_checks()
                if health_result["status"] == HealthStatus.UNHEALTHY:
                    logging.error(f"Health check UNHEALTHY: {health_result}")
                    self.notifier.notify_error(f"Health check unhealthy: {health_result['summary']}")
                elif health_result["status"] == HealthStatus.DEGRADED:
                    logging.warning(f"Health check DEGRADED: {health_result['summary']}")

            portfolio_state = self._get_portfolio_state()
            self._last_portfolio_state = portfolio_state

            logging.info(f"Portfolio: balance=${portfolio_state.total_balance}, available=${portfolio_state.available_balance}, margin_usage={float(portfolio_state.margin_usage) * 100:.1f}%, positions={len(portfolio_state.positions)}, unrealized_pnl=${portfolio_state.get_total_unrealized_pnl()}")

            write_live_status(is_running=True, execution_mode=EXECUTION_MODE, cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration, portfolio=portfolio_state, current_coin="scanning...")

            if portfolio_state.total_balance <= 0:
                logging.warning("Portfolio balance zero or negative, skipping cycle")
                return True

            state = self.state_store.load_state()

            # === Save equity snapshot for real equity curve ===
            self.state_store.add_equity_snapshot(
                state,
                balance=portfolio_state.total_balance,
                unrealized_pnl=portfolio_state.get_total_unrealized_pnl(),
                position_count=len(portfolio_state.positions),
                margin_usage=portfolio_state.margin_usage,
            )

            daily_notional_used = self._get_daily_notional_used(state)
            peak = Decimal(str(state.get("peak_portfolio_value", "0")))
            consecutive_losses = state.get("consecutive_losses", 0)

            sl_tp_triggered = self._process_sl_tp_trailing(portfolio_state)
            if sl_tp_triggered > 0:
                logging.info(f"SL/TP/Trailing/BE triggered {sl_tp_triggered} closes, refreshing portfolio")
                portfolio_state = self._get_portfolio_state()
                self._last_portfolio_state = portfolio_state

            if self.risk_manager.check_emergency_derisk(portfolio_state):
                logging.warning("EMERGENCY: Critical margin usage, attempting de-risk")
                self._handle_emergency_derisk(portfolio_state)
                portfolio_state = self._get_portfolio_state()
                self._last_portfolio_state = portfolio_state

            correlations = self.correlation_engine.calculate_correlations(self._trading_pairs, "1h", 50)
            corr_summary = self.correlation_engine.get_correlation_summary(correlations)
            if corr_summary["high_correlation_pairs"]:
                logging.info(f"High correlation pairs: {corr_summary['high_correlation_pairs'][:5]}")

            all_mids = technical_fetcher.get_all_mids()
            recent_trades = self.state_store.get_recent_trades(state, count=5)
            trades_executed = 0

            for coin in self._trading_pairs:
                if self._shutdown_requested:
                    logging.info("Shutdown requested, stopping coin analysis")
                    break
                if trades_executed >= MAX_TRADES_PER_CYCLE:
                    logging.info(f"Max trades per cycle ({MAX_TRADES_PER_CYCLE}) reached")
                    break

                logging.info(f"--- Analyzing {coin} ---")
                write_live_status(is_running=True, execution_mode=EXECUTION_MODE, cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration, portfolio=portfolio_state, current_coin=coin)

                market_data, tech_data = self._get_market_data_and_technicals(coin)
                if not market_data:
                    logging.warning(f"Skipping {coin}: no market data")
                    continue

                trends_aligned = tech_data.get("trends_aligned", False) if tech_data else False
                intraday_trend = tech_data.get("intraday_trend", "unknown") if tech_data else "unknown"
                hourly_ctx = tech_data.get("hourly_context", {}) if tech_data else {}
                hourly_trend = hourly_ctx.get("trend", "unknown")

                logging.info(f"{coin}: price=${market_data.last_price}, RSI14={float(tech_data.get('current_rsi_14', 50)):.1f}, BB={float(tech_data.get('bb_position', 0.5)):.2f}, vol_ratio={float(tech_data.get('volume_ratio', 1)):.2f}, trends={'ALIGNED' if trends_aligned else 'DIVERGENT'} (5m={intraday_trend}, 1h={hourly_trend})")

                funding_data = technical_fetcher.get_funding_for_coin(coin)

                corr_ok, corr_reason = self.correlation_engine.check_correlation_risk(coin, "buy", portfolio_state.positions, correlations)
                if not corr_ok:
                    logging.info(f"{coin} correlation risk: {corr_reason}")

                if self.llm_engine:
                    self._llm_rate_limiter.acquire(1)
                    self.metrics.increment("llm_calls_total")
                    decision = self.llm_engine.get_trading_decision(
                        market_data=market_data, portfolio_state=portfolio_state, technical_data=tech_data,
                        all_mids=all_mids, funding_data=funding_data, recent_trades=recent_trades,
                        peak_portfolio_value=peak, consecutive_losses=consecutive_losses
                    )
                    if not decision:
                        self.metrics.increment("llm_errors_total")
                        decision = self._get_fallback_decision()
                        logging.warning(f"LLM failed for {coin}, using fallback")
                else:
                    decision = self._get_fallback_decision()

                logging.info(f"{coin} decision: action={decision['action']}, size={decision['size']}, leverage={decision['leverage']}, confidence={decision['confidence']}")

                if not corr_ok and decision["action"] in ["buy", "sell", "increase_position"]:
                    logging.info(f"{coin} blocked by correlation risk: {corr_reason}")
                    self.metrics.increment("risk_rejections_total")
                    continue

                min_size = self._resolve_min_size(coin)
                self.risk_manager.min_size_by_coin[coin] = min_size

                volatility = Decimal("0")
                if tech_data and tech_data.get("intraday_atr", Decimal("0")) > 0 and market_data.last_price > 0:
                    volatility = tech_data["intraday_atr"] / market_data.last_price

                risk_ok, risk_reason = self.risk_manager.check_order(
                    coin, decision, market_data.last_price, portfolio_state,
                    state.get("last_trade_timestamp_by_coin", {}),
                    daily_notional_used, time.time(), volatility, peak
                )
                if not risk_ok:
                    logging.info(f"{coin} risk rejected: {risk_reason}")
                    self.metrics.increment("risk_rejections_total")
                    continue

                snapshot = None
                if EXECUTION_MODE == "live" and ENABLE_MAINNET_TRADING:
                    snapshot = self.order_verifier.snapshot_position(self.wallet_address, coin)

                result = self.execution_engine.execute(coin, decision, market_data, portfolio_state.positions)

                fill_status = "unknown"
                if snapshot and result["success"] and decision["action"] in ["buy", "sell", "increase_position"]:
                    expected_side = "buy" if decision["action"] in ["buy", "increase_position"] else "sell"
                    verification = self.order_verifier.verify_fill(self.wallet_address, coin, expected_side, Decimal(str(decision["size"])), snapshot)
                    fill_status = verification.get("fill_status", "unknown")
                    if fill_status == "not_filled":
                        logging.warning(f"{coin} order NOT FILLED — marking as failed")
                        result["success"] = False
                        result["reason"] = "order_not_filled"

                trade_record = {
                    "timestamp": time.time(), "coin": coin, "action": decision["action"],
                    "size": str(decision["size"]), "price": str(market_data.last_price),
                    "notional": str(result.get("notional", "0")), "leverage": decision["leverage"],
                    "confidence": decision["confidence"], "reasoning": decision.get("reasoning", "")[:200],
                    "success": result["success"], "mode": EXECUTION_MODE, "trigger": "ai", "order_status": fill_status,
                }
                self.state_store.add_trade_record(state, trade_record)

                if result["success"]:
                    notional = Decimal(str(result["notional"]))
                    if notional > 0:
                        trades_executed += 1
                        daily_notional_used += notional
                        state.setdefault("last_trade_timestamp_by_coin", {})[coin] = time.time()
                        self.metrics.increment("trades_executed_total")
                        state["consecutive_losses"] = 0
                        if decision["action"] in ["buy", "sell", "increase_position"]:
                            is_long = decision["action"] in ["buy", "increase_position"]
                            self.position_manager.register_position(coin=coin, size=Decimal(str(decision["size"])), entry_price=market_data.last_price, is_long=is_long, leverage=decision["leverage"])
                        self.notifier.notify_trade(trade_record)
                        logging.info(f"{coin} executed: reason={result['reason']}, notional=${notional}")
                    else:
                        self.metrics.increment("holds_total")
                        logging.info(f"{coin}: hold (no trade)")
                else:
                    self.metrics.increment("execution_failures_total")
                    state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
                    logging.warning(f"{coin} execution failed: {result.get('reason', 'unknown')}")

            state["daily_notional_by_day"] = self.state_store.add_daily_notional(state.get("daily_notional_by_day", {}), time.time(), daily_notional_used - self._get_daily_notional_used(state))
            if portfolio_state.total_balance > peak:
                state["peak_portfolio_value"] = str(portfolio_state.total_balance)
                self.metrics.set_gauge("peak_portfolio_value", portfolio_state.total_balance)
            state["consecutive_failed_cycles"] = 0
            self.state_store.save_state(state)

            cycle_duration = time.time() - cycle_start
            self._last_cycle_duration = cycle_duration
            self.metrics.record_histogram("cycle_duration_seconds", cycle_duration)
            self.metrics.increment("cycles_total")
            self._persist_metrics()
            self._log_performance_summary(state)
            self._next_cycle_sec = self._calculate_adaptive_cycle()

            write_live_status(is_running=True, execution_mode=EXECUTION_MODE, cycle_count=self._cycle_count, last_cycle_duration=cycle_duration, portfolio=portfolio_state, current_coin="idle")
            logging.info(f"Cycle #{self._cycle_count} complete: {trades_executed} trades, duration={cycle_duration:.1f}s, next_cycle={self._next_cycle_sec}s")

        except Exception as e:
            logging.error(f"Cycle failed: {type(e).__name__}: {e}", exc_info=True)
            success = False
            self.metrics.increment("cycles_failed")
            self.notifier.notify_error(f"Cycle failed: {type(e).__name__}: {str(e)[:200]}")
            write_live_status(is_running=True, execution_mode=EXECUTION_MODE, cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration, portfolio=self._last_portfolio_state, error=f"{type(e).__name__}: {str(e)[:200]}")
            state = self.state_store.load_state()
            state["consecutive_failed_cycles"] = state.get("consecutive_failed_cycles", 0) + 1
            self.state_store.save_state(state)

        return success

    def run(self, single_cycle: bool = False):
        logging.info("=" * 60)
        logging.info("HYPERLIQUID TRADING BOT STARTED")
        logging.info("=" * 60)
        logging.info(f"Wallet: {self._mask_wallet(self.wallet_address)}")
        logging.info(f"Execution mode: {EXECUTION_MODE}")
        logging.info(f"Mainnet trading: {ENABLE_MAINNET_TRADING}")
        logging.info(f"LLM model: {LLM_MODEL}")
        logging.info(f"Trading pairs ({len(TRADING_PAIRS_RAW)}): {TRADING_PAIRS_RAW}")
        logging.info(f"Strategy: Asymmetric R:R — SL {float(DEFAULT_SL_PCT)*100}% / TP {float(DEFAULT_TP_PCT)*100}% / Trailing {float(DEFAULT_TRAILING_CALLBACK)*100}% / Break-Even @{float(BREAK_EVEN_ACTIVATION_PCT)*100}%")
        logging.info(f"Confidence threshold: open={MIN_CONFIDENCE_OPEN} manage={MIN_CONFIDENCE_MANAGE}")
        logging.info(f"Adaptive cycle: {ENABLE_ADAPTIVE_CYCLE} ({MIN_CYCLE_SEC}-{MAX_CYCLE_SEC}s)")
        logging.info(f"Correlation threshold: {CORRELATION_THRESHOLD}")
        logging.info(f"Max drawdown: {float(MAX_DRAWDOWN_PCT)*100}%")
        logging.info(f"Telegram: {'enabled' if self.notifier.telegram_enabled else 'disabled'}")
        logging.info("=" * 60)

        health_result = self.health_monitor.run_all_checks()
        logging.info(f"Startup health check: {health_result['status']} ({health_result['summary']})")

        self.notifier.notify_bot_started(EXECUTION_MODE, TRADING_PAIRS_RAW)
        write_live_status(is_running=True, execution_mode=EXECUTION_MODE, cycle_count=0, last_cycle_duration=0.0, current_coin="starting...")

        meta = self.exchange_client.get_meta(force_refresh=True)
        if meta:
            logging.info(f"Hyperliquid connected: {len(meta.get('universe', []))} assets available")
        else:
            logging.error("FAILED to connect to Hyperliquid API at startup!")
            self.notifier.notify_error("Failed to connect to Hyperliquid API at startup")
            if not single_cycle:
                write_live_status(is_running=False, execution_mode=EXECUTION_MODE, cycle_count=0, last_cycle_duration=0.0, error="Failed to connect to Hyperliquid API")
                return

        self._trading_pairs = self._validate_trading_pairs()
        consecutive_failures = 0

        while not self._shutdown_requested:
            if self._run_trading_cycle():
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logging.warning(f"Consecutive failures: {consecutive_failures}/{MAX_CONSECUTIVE_FAILED_CYCLES}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILED_CYCLES:
                    logging.error("Too many consecutive failures, shutting down")
                    self.notifier.notify_error(f"Bot shutdown: {consecutive_failures} consecutive failures")
                    break
            if single_cycle:
                logging.info("Single cycle mode: exiting")
                break
            wait_sec = self._next_cycle_sec
            logging.info(f"Waiting {wait_sec} seconds before next cycle...")
            for _ in range(wait_sec):
                if self._shutdown_requested:
                    break
                time.sleep(1)

        logging.info("=" * 60)
        logging.info("BOT GRACEFUL SHUTDOWN")
        state = self.state_store.load_state()
        self._log_performance_summary(state)
        self.state_store.save_state(state)
        self._persist_metrics()
        self.notifier.notify_bot_stopped("graceful_shutdown")
        write_live_status(is_running=False, execution_mode=EXECUTION_MODE, cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration, portfolio=self._last_portfolio_state, current_coin="stopped")
        logging.info("State saved. Goodbye.")
        logging.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Hyperliquid Trading Bot — Claude Opus 4.6")
    parser.add_argument("--single-cycle", action="store_true", help="Run single cycle and exit")
    args = parser.parse_args()
    bot = HyperliquidBot()
    bot.run(single_cycle=args.single_cycle)


if __name__ == "__main__":
    main()