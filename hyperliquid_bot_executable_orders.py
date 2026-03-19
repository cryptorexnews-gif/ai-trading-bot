#!/usr/bin/env python3
"""
Hyperliquid Trading Bot con operación autónoma enterprise.
"""

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from eth_account import Account

from exchange_client import HyperliquidExchangeClient
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import MarketData, PortfolioState, TradingAction
from risk_manager import RiskManager
from state_store import StateStore

load_dotenv()
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/hyperliquid_bot_executable.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from technical_analyzer_simple import technical_fetcher


class HyperliquidTradingBotExecutable:
    def __init__(
        self,
        wallet_address: str,
        private_key: str,
        deepseek_api_key: str,
        trading_pairs: Optional[List[str]] = None
    ):
        self.wallet_address = wallet_address
        self.private_key = private_key
        self.deepseek_api_key = deepseek_api_key
        self.base_url = "https://api.hyperliquid.xyz"
        self.trading_pairs = trading_pairs or ["BTC", "ETH", "SOL", "BNB", "ADA"]

        self.max_margin_usage = Decimal("0.95")
        self.max_order_margin_pct = Decimal(os.getenv("MAX_ORDER_MARGIN_PCT", "0.10"))
        self.hard_max_leverage = Decimal(os.getenv("HARD_MAX_LEVERAGE", "10"))
        self.min_confidence_open = Decimal(os.getenv("MIN_CONFIDENCE_OPEN", "0.20"))
        self.min_confidence_manage = Decimal(os.getenv("MIN_CONFIDENCE_MANAGE", "0.10"))

        self.max_trades_per_cycle = int(os.getenv("MAX_TRADES_PER_CYCLE", "2"))
        self.max_consecutive_failed_cycles = int(os.getenv("MAX_CONSECUTIVE_FAILED_CYCLES", "3"))
        self.max_drawdown_pct = Decimal(os.getenv("MAX_DRAWDOWN_PCT", "0.20"))
        self.max_market_data_age_sec = int(os.getenv("MAX_MARKET_DATA_AGE_SEC", "120"))
        self.meta_cache_ttl_sec = int(os.getenv("META_CACHE_TTL_SEC", "60"))

        self.trade_cooldown_sec = int(os.getenv("TRADE_COOLDOWN_SEC", "300"))
        self.daily_notional_limit_usd = Decimal(os.getenv("DAILY_NOTIONAL_LIMIT_USD", "5000"))

        self.enable_mainnet_trading = os.getenv("ENABLE_MAINNET_TRADING", "false").lower() == "true"
        self.allow_external_llm = os.getenv("ALLOW_EXTERNAL_LLM", "false").lower() == "true"
        self.include_portfolio_in_llm_prompt = os.getenv("LLM_INCLUDE_PORTFOLIO_CONTEXT", "false").lower() == "true"
        self.execution_mode = os.getenv("EXECUTION_MODE", "paper").lower()
        self.safe_fallback_mode = os.getenv("SAFE_FALLBACK_MODE", "de_risk").lower()
        self.paper_slippage_bps = Decimal(os.getenv("PAPER_SLIPPAGE_BPS", "3"))

        self.health_file_path = os.getenv("HEALTH_FILE_PATH", "logs/agent_health.json")
        self.state_file_path = os.getenv("STATE_FILE_PATH", "logs/agent_state.json")
        self.metrics_file_path = os.getenv("METRICS_FILE_PATH", "logs/agent_metrics.json")

        self.min_size_by_coin: Dict[str, Decimal] = {
            "BTC": Decimal("0.001"),
            "ETH": Decimal("0.001"),
            "SOL": Decimal("0.1"),
            "BNB": Decimal("0.001"),
            "ADA": Decimal("16")
        }

        self.is_running = False
        self.is_emergency_stopped = False
        self.last_cycle_timestamp = 0.0

        derived_account = Account.from_key(self.private_key)
        if derived_account.address.lower() != self.wallet_address.lower():
            raise ValueError("HYPERLIQUID_WALLET_ADDRESS does not match HYPERLIQUID_PRIVATE_KEY")

        environment = os.getenv("ENVIRONMENT", "development").lower()
        if environment == "production" and os.path.exists(".env"):
            logger.warning("Production mode detected with .env file present; prefer runtime env-injection.")

        self.exchange_client = HyperliquidExchangeClient(
            base_url=self.base_url,
            private_key=self.private_key,
            enable_mainnet_trading=self.enable_mainnet_trading,
            execution_mode=self.execution_mode,
            meta_cache_ttl_sec=self.meta_cache_ttl_sec,
            paper_slippage_bps=self.paper_slippage_bps
        )

        self.llm_engine = LLMEngine(
            session=self.exchange_client.session,
            deepseek_api_key=self.deepseek_api_key,
            allow_external_llm=self.allow_external_llm,
            include_portfolio_context=self.include_portfolio_in_llm_prompt,
            fallback_mode=self.safe_fallback_mode,
            trading_pairs=self.trading_pairs,
            min_size_by_coin=self.min_size_by_coin,
            hard_max_leverage=self.hard_max_leverage
        )

        self.risk_manager = RiskManager(
            min_size_by_coin=self.min_size_by_coin,
            hard_max_leverage=self.hard_max_leverage,
            min_confidence_open=self.min_confidence_open,
            min_confidence_manage=self.min_confidence_manage,
            max_margin_usage=self.max_margin_usage,
            max_order_margin_pct=self.max_order_margin_pct,
            trade_cooldown_sec=self.trade_cooldown_sec,
            daily_notional_limit_usd=self.daily_notional_limit_usd
        )

        self.execution_engine = ExecutionEngine(self.exchange_client)
        self.state_store = StateStore(self.state_file_path, self.metrics_file_path)

        restored_state = self.state_store.load_state()
        self.peak_portfolio_value = Decimal(str(restored_state.get("peak_portfolio_value", "0")))
        self.consecutive_failed_cycles = int(restored_state.get("consecutive_failed_cycles", 0))
        self.last_trade_timestamp_by_coin = {
            k: float(v) for k, v in restored_state.get("last_trade_timestamp_by_coin", {}).items()
        }
        self.daily_notional_by_day = {
            k: str(v) for k, v in restored_state.get("daily_notional_by_day", {}).items()
        }
        self.metrics = self.state_store.load_metrics()

        logger.info(f"Bot initialized for wallet {self._mask_wallet(self.wallet_address)}")
        logger.info(f"Execution mode: {self.execution_mode}")
        logger.info(f"Trading pairs: {self.trading_pairs}")
        logger.info(f"Fallback mode: {self.safe_fallback_mode}")

    def _mask_wallet(self, wallet: str) -> str:
        if not wallet or len(wallet) < 12:
            return "invalid_wallet"
        return f"{wallet[:6]}...{wallet[-4:]}"

    def _safe_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        return Decimal(str(value)) if value is not None else default

    def run_startup_checks(self) -> bool:
        meta = self.exchange_client.get_meta(force_refresh=True)
        if meta is None:
            logger.error("Startup check failed: meta unavailable")
            return False

        user_state = self.exchange_client.get_user_state(self.wallet_address)
        if user_state is None:
            logger.error("Startup check failed: user state unavailable")
            return False

        for coin in self.trading_pairs:
            asset_id = self.exchange_client.get_asset_id(coin)
            if asset_id is None:
                logger.error(f"Startup check failed: missing asset ID for {coin}")
                return False
            max_leverage = self.exchange_client.get_max_leverage(coin)
            if max_leverage < 1:
                logger.error(f"Startup check failed: invalid max leverage for {coin}")
                return False

        if self.allow_external_llm and not self.deepseek_api_key:
            logger.error("Startup check failed: ALLOW_EXTERNAL_LLM=true but DEEPSEEK_API_KEY missing")
            return False

        if self.execution_mode not in ["paper", "live"]:
            logger.error("Startup check failed: EXECUTION_MODE must be paper or live")
            return False

        logger.info("Startup checks passed")
        return True

    def get_all_market_data(self) -> Dict[str, MarketData]:
        market_data: Dict[str, MarketData] = {}
        now = time.time()

        for coin in self.trading_pairs:
            indicators = technical_fetcher.get_technical_indicators(coin)
            if indicators and self._safe_decimal(indicators.get("current_price", "0")) > 0:
                market_data[coin] = MarketData(
                    coin=coin,
                    last_price=self._safe_decimal(indicators.get("current_price", "0")),
                    change_24h=self._safe_decimal(indicators.get("change_24h", "0")),
                    volume_24h=self._safe_decimal(indicators.get("volume_24h", "0")),
                    funding_rate=Decimal("0.0001"),
                    timestamp=now
                )
            else:
                market_data[coin] = MarketData(
                    coin=coin,
                    last_price=Decimal("0"),
                    change_24h=Decimal("0"),
                    volume_24h=Decimal("0"),
                    funding_rate=Decimal("0"),
                    timestamp=now
                )
        return market_data

    def _market_data_is_fresh(self, data: Dict[str, MarketData]) -> bool:
        now = time.time()
        for coin, item in data.items():
            if item.last_price <= 0:
                logger.warning(f"Invalid market data for {coin}: price<=0")
                return False
            age = now - item.timestamp
            if age > self.max_market_data_age_sec:
                logger.warning(f"Stale market data for {coin}: age={age:.1f}s")
                return False
        return True

    def get_portfolio_state(self) -> PortfolioState:
        data = self.exchange_client.get_user_state(self.wallet_address)
        if data is None:
            return PortfolioState(Decimal("0"), Decimal("0"), Decimal("0"), {})

        margin_summary = data.get("marginSummary", {})
        total_balance = self._safe_decimal(margin_summary.get("accountValue", "0"))
        available_balance = self._safe_decimal(data.get("withdrawable", "0"))
        total_margin_used = self._safe_decimal(margin_summary.get("totalMarginUsed", "0"))
        margin_usage = (total_margin_used / total_balance) if total_balance > 0 else Decimal("0")

        positions: Dict[str, Dict[str, Any]] = {}
        for position in data.get("assetPositions", []):
            p = position.get("position", {})
            coin = p.get("coin", "")
            if not coin:
                continue
            size = self._safe_decimal(p.get("szi", "0"))
            if size == 0:
                continue

            entry_price = self._safe_decimal(p.get("entryPx", "0"))
            unrealized_pnl = self._safe_decimal(p.get("unrealizedPnl", "0"))
            margin_used = self._safe_decimal(p.get("marginUsed", "0"))
            leverage_data = p.get("leverage", {})
            leverage = self._safe_decimal(leverage_data.get("value", "1")) if leverage_data else Decimal("1")
            position_value = abs(size * entry_price)
            calculated_leverage = (position_value / margin_used) if margin_used > 0 else leverage

            positions[coin] = {
                "size": size,
                "entry_price": entry_price,
                "unrealized_pnl": unrealized_pnl,
                "margin_used": margin_used,
                "leverage": calculated_leverage,
                "position_value": position_value
            }

        logger.info(
            f"Portfolio | total=${total_balance:.2f} available=${available_balance:.2f} "
            f"margin={margin_usage*100:.1f}% positions={len(positions)}"
        )
        return PortfolioState(total_balance, available_balance, margin_usage, positions)

    def _update_drawdown_guard(self, portfolio_state: PortfolioState) -> bool:
        equity = portfolio_state.total_balance
        if equity <= 0:
            self.is_emergency_stopped = True
            logger.error("Emergency stop: equity <= 0")
            return False

        if equity > self.peak_portfolio_value:
            self.peak_portfolio_value = equity
            return True

        if self.peak_portfolio_value <= 0:
            self.peak_portfolio_value = equity
            return True

        drawdown = (self.peak_portfolio_value - equity) / self.peak_portfolio_value
        if drawdown >= self.max_drawdown_pct:
            self.is_emergency_stopped = True
            logger.error(
                f"Emergency stop: drawdown {drawdown*100:.2f}% >= {self.max_drawdown_pct*100:.2f}%"
            )
            return False
        return True

    def _current_day_notional(self, now_ts: float) -> Decimal:
        key = self.state_store.day_key(now_ts)
        return Decimal(str(self.daily_notional_by_day.get(key, "0")))

    def _persist_state_and_metrics(self) -> None:
        state_payload = {
            "peak_portfolio_value": str(self.peak_portfolio_value),
            "consecutive_failed_cycles": self.consecutive_failed_cycles,
            "last_trade_timestamp_by_coin": self.last_trade_timestamp_by_coin,
            "daily_notional_by_day": self.daily_notional_by_day
        }
        self.state_store.save_state(state_payload)
        self.state_store.save_metrics(self.metrics)

    def _write_health_snapshot(
        self,
        portfolio_state: PortfolioState,
        trades_executed: List[str],
        hold_decisions: List[str],
        failed_checks: List[str]
    ) -> None:
        snapshot = {
            "timestamp": int(time.time()),
            "is_running": self.is_running,
            "is_emergency_stopped": self.is_emergency_stopped,
            "execution_mode": self.execution_mode,
            "consecutive_failed_cycles": self.consecutive_failed_cycles,
            "peak_portfolio_value": str(self.peak_portfolio_value),
            "portfolio": {
                "total_balance": str(portfolio_state.total_balance),
                "available_balance": str(portfolio_state.available_balance),
                "margin_usage": str(portfolio_state.margin_usage),
                "open_positions": len(portfolio_state.positions)
            },
            "cycle": {
                "executed_trades": trades_executed,
                "hold_decisions": hold_decisions,
                "failed_checks": failed_checks
            }
        }
        with open(self.health_file_path, "w", encoding="utf-8") as file_obj:
            json.dump(snapshot, file_obj, ensure_ascii=False, indent=2)

    def _update_metrics(
        self,
        trades_executed_count: int,
        holds_count: int,
        risk_rejections: int,
        execution_failures: int,
        cycle_failed: bool,
        cycle_notional: Decimal
    ) -> None:
        self.metrics["cycles_total"] = int(self.metrics.get("cycles_total", 0)) + 1
        if cycle_failed:
            self.metrics["cycles_failed"] = int(self.metrics.get("cycles_failed", 0)) + 1
        self.metrics["trades_executed_total"] = int(self.metrics.get("trades_executed_total", 0)) + trades_executed_count
        self.metrics["holds_total"] = int(self.metrics.get("holds_total", 0)) + holds_count
        self.metrics["risk_rejections_total"] = int(self.metrics.get("risk_rejections_total", 0)) + risk_rejections
        self.metrics["execution_failures_total"] = int(self.metrics.get("execution_failures_total", 0)) + execution_failures

        running_notional = Decimal(str(self.metrics.get("daily_notional_total", "0")))
        self.metrics["daily_notional_total"] = str(running_notional + cycle_notional)

    def run_trading_cycle(self) -> None:
        if self.is_emergency_stopped:
            logger.error("Cycle skipped: emergency stopped")
            return

        self.last_cycle_timestamp = time.time()
        logger.info("Starting trading cycle")

        portfolio_state = self.get_portfolio_state()
        if not self._update_drawdown_guard(portfolio_state):
            self.is_running = False
            self._write_health_snapshot(portfolio_state, [], [], ["emergency_stop"])
            self._persist_state_and_metrics()
            return

        market_data = self.get_all_market_data()
        if not self._market_data_is_fresh(market_data):
            self.consecutive_failed_cycles += 1
            if self.consecutive_failed_cycles >= self.max_consecutive_failed_cycles:
                self.is_emergency_stopped = True
                self.is_running = False
            self._update_metrics(0, 0, 0, 0, True, Decimal("0"))
            self._write_health_snapshot(portfolio_state, [], [], ["market_data_invalid_or_stale"])
            self._persist_state_and_metrics()
            return

        orders = self.llm_engine.get_orders(market_data, portfolio_state)

        trades_executed: List[str] = []
        hold_decisions: List[str] = []
        failed_checks: List[str] = []
        risk_rejections = 0
        execution_failures = 0
        cycle_notional = Decimal("0")
        now_ts = time.time()

        for coin in self.trading_pairs:
            order = orders.get(coin, {})
            action = str(order.get("action", "hold")).lower()
            if action == TradingAction.HOLD.value:
                hold_decisions.append(coin)
                continue

            if len(trades_executed) >= self.max_trades_per_cycle:
                failed_checks.append(f"{coin}: max_trades_per_cycle_reached")
                continue

            current_day_notional = self._current_day_notional(now_ts)
            ok, reason = self.risk_manager.check_order(
                coin=coin,
                order=order,
                market_price=market_data[coin].last_price,
                portfolio_state=portfolio_state,
                last_trade_timestamp_by_coin=self.last_trade_timestamp_by_coin,
                daily_notional_used=current_day_notional,
                now_ts=now_ts
            )
            if not ok:
                risk_rejections += 1
                failed_checks.append(f"{coin}: {reason}")
                continue

            result = self.execution_engine.execute(
                coin=coin,
                order=order,
                market_data=market_data[coin],
                positions=portfolio_state.positions
            )
            if not result.get("success", False):
                execution_failures += 1
                failed_checks.append(f"{coin}: {result.get('reason', 'execution_failed')}")
                continue

            notional = Decimal(str(result.get("notional", "0")))
            trades_executed.append(f"{coin}:{action}")
            cycle_notional += notional

            open_actions = {
                TradingAction.BUY.value,
                TradingAction.SELL.value,
                TradingAction.INCREASE_POSITION.value
            }
            if action in open_actions and notional > 0:
                self.last_trade_timestamp_by_coin[coin] = now_ts
                self.daily_notional_by_day = self.state_store.add_daily_notional(
                    self.daily_notional_by_day,
                    now_ts,
                    notional
                )

        catastrophic_failure = len(trades_executed) == 0 and len(failed_checks) >= len(self.trading_pairs)
        if catastrophic_failure:
            self.consecutive_failed_cycles += 1
        else:
            self.consecutive_failed_cycles = 0

        if self.consecutive_failed_cycles >= self.max_consecutive_failed_cycles:
            self.is_emergency_stopped = True
            self.is_running = False
            logger.error("Emergency stop: max consecutive failed cycles reached")

        cycle_failed = catastrophic_failure or self.is_emergency_stopped
        self._update_metrics(
            trades_executed_count=len(trades_executed),
            holds_count=len(hold_decisions),
            risk_rejections=risk_rejections,
            execution_failures=execution_failures,
            cycle_failed=cycle_failed,
            cycle_notional=cycle_notional
        )
        self._write_health_snapshot(portfolio_state, trades_executed, hold_decisions, failed_checks)
        self._persist_state_and_metrics()

        logger.info(
            f"CYCLE SUMMARY | executed={trades_executed if trades_executed else ['none']} "
            f"holds={hold_decisions if hold_decisions else ['none']} "
            f"failed={failed_checks if failed_checks else ['none']} "
            f"daily_notional_today={self._current_day_notional(time.time())} "
            f"consecutive_failed={self.consecutive_failed_cycles}"
        )

    def start(self, cycle_interval: int = 300) -> None:
        if not self.run_startup_checks():
            logger.error("Startup checks failed, bot not started")
            return

        self.is_running = True
        logger.info(f"Starting autonomous bot loop (interval={cycle_interval}s)")

        while self.is_running and not self.is_emergency_stopped:
            cycle_start = time.time()
            self.run_trading_cycle()
            elapsed = int(time.time() - cycle_start)
            sleep_seconds = max(cycle_interval - elapsed, 1)
            logger.info(f"Sleeping {sleep_seconds}s")
            time.sleep(sleep_seconds)

        logger.warning("Bot stopped")

    def stop(self) -> None:
        self.is_running = False
        self._persist_state_and_metrics()
        logger.info("Stopping bot")


def main():
    import sys

    wallet_address = os.getenv("HYPERLIQUID_WALLET_ADDRESS")
    private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY", "")

    if not wallet_address or not private_key:
        logger.error("Missing env vars: HYPERLIQUID_WALLET_ADDRESS / HYPERLIQUID_PRIVATE_KEY")
        return

    bot = HyperliquidTradingBotExecutable(
        wallet_address=wallet_address,
        private_key=private_key,
        deepseek_api_key=deepseek_api_key,
        trading_pairs=["BTC", "ETH", "SOL", "BNB", "ADA"]
    )

    if len(sys.argv) > 1 and sys.argv[1] == "--single-cycle":
        bot.run_trading_cycle()
        logger.info("Single cycle completed")
    else:
        bot.start(cycle_interval=300)


if __name__ == "__main__":
    main()