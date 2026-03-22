import argparse
import logging
import signal
import time
from typing import Optional

from bot.cycle_executor import CycleExecutor
from bot_live_writer import write_live_status
from models import PortfolioState


class BotRunner:
    """Runs the bot lifecycle loop and delegates single-cycle execution to CycleExecutor."""

    def __init__(self, context, runtime_applier):
        self.context = context
        self.runtime_applier = runtime_applier
        self.cycle_executor = CycleExecutor(context)

        self.cycle_count = 0
        self.last_cycle_duration = 0.0
        self.shutdown_requested = False
        self.last_portfolio: Optional[PortfolioState] = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, _frame):
        logging.info(f"Received {signal.Signals(signum).name}, requesting graceful shutdown...")
        self.shutdown_requested = True

    def _format_cycle_label(self, cycle_seconds: int) -> str:
        if cycle_seconds <= 0:
            return "0s"
        if cycle_seconds % 60 == 0:
            minutes = cycle_seconds // 60
            return "1 minuto" if minutes == 1 else f"{minutes} minuti"
        return f"{cycle_seconds}s"

    def _calculate_adaptive_cycle(self) -> int:
        if not self.context.cfg.enable_adaptive_cycle:
            return self.context.cfg.default_cycle_sec
        return self.context.cfg.default_cycle_sec

    def run(self, single_cycle: bool = False) -> None:
        logging.info("=" * 60)
        logging.info("HYPERLIQUID TRADING BOT STARTED - TREND 4H/1D ULTRA-CONSERVATIVO")
        logging.info("=" * 60)
        logging.info(f"Wallet: {self.context.cfg.mask_wallet(self.context.cfg.wallet_address)}")
        logging.info(f"Execution mode: {self.context.cfg.execution_mode}")
        logging.info(f"Mainnet trading: {self.context.cfg.enable_mainnet_trading}")
        logging.info(f"LLM model: {self.context.cfg.llm_model}")
        logging.info(f"Trading pairs ({len(self.context.cfg.trading_pairs)}): {self.context.cfg.trading_pairs}")
        logging.info(
            f"Strategy: Trend/Scalping runtime\n"
            f"  • Ciclo base: {self._format_cycle_label(self.context.cfg.default_cycle_sec)}\n"
            f"  • SL: {float(self.context.cfg.trend_sl_pct)*100}% / TP: {float(self.context.cfg.trend_tp_pct)*100}%\n"
            f"  • Position Size: {float(self.context.cfg.trend_position_size_pct)*100}%\n"
            f"  • Max Leverage: {self.context.cfg.hard_max_leverage}x\n"
            f"  • Max Drawdown: {float(self.context.cfg.max_drawdown_pct)*100}%\n"
            f"  • Daily Limit: ${self.context.cfg.daily_notional_limit_usd}"
        )
        logging.info(
            f"Adaptive cycle: {self.context.cfg.enable_adaptive_cycle} "
            f"({self.context.cfg.min_cycle_sec}-{self.context.cfg.max_cycle_sec}s)"
        )
        logging.info(f"Telegram: {'enabled' if self.context.notifier.telegram_enabled else 'disabled'}")
        logging.info("=" * 60)

        health_result = self.context.health_monitor.run_all_checks()
        logging.info(f"Startup health check: {health_result['status']} ({health_result['summary']})")

        self.context.notifier.notify_bot_started(self.context.cfg.execution_mode, self.context.cfg.trading_pairs)
        write_live_status(
            is_running=True,
            execution_mode=self.context.cfg.execution_mode,
            cycle_count=0,
            last_cycle_duration=0.0,
            current_coin="starting..."
        )

        meta = self.context.exchange_client.get_meta(force_refresh=True)
        if meta:
            logging.info(f"Hyperliquid connected: {len(meta.get('universe', []))} assets available")
        else:
            logging.error("FAILED to connect to Hyperliquid API at startup!")
            self.context.notifier.notify_error("Failed to connect to Hyperliquid API at startup")
            if not single_cycle:
                write_live_status(
                    is_running=False,
                    execution_mode=self.context.cfg.execution_mode,
                    cycle_count=0,
                    last_cycle_duration=0.0,
                    error="Failed to connect to Hyperliquid API"
                )
                return

        self.runtime_applier.apply(force=True)
        consecutive_failures = 0

        while not self.shutdown_requested:
            self.runtime_applier.apply()

            self.cycle_count += 1
            cycle_result = self.cycle_executor.execute_cycle(
                cycle_count=self.cycle_count,
                current_next_cycle_sec=self.runtime_applier.next_cycle_sec,
                shutdown_requested=self.shutdown_requested,
                last_cycle_duration=self.last_cycle_duration,
                last_portfolio=self.last_portfolio,
            )

            self.last_cycle_duration = cycle_result["last_cycle_duration"]
            self.last_portfolio = cycle_result["last_portfolio"]

            if cycle_result["success"]:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logging.warning(
                    f"Consecutive failures: {consecutive_failures}/"
                    f"{self.context.cfg.max_consecutive_failed_cycles}"
                )
                if consecutive_failures >= self.context.cfg.max_consecutive_failed_cycles:
                    logging.error("Too many consecutive failures, shutting down")
                    self.context.notifier.notify_error(
                        f"Bot shutdown: {consecutive_failures} consecutive failures"
                    )
                    break

            self.runtime_applier.next_cycle_sec = self._calculate_adaptive_cycle()

            if single_cycle:
                logging.info("Single cycle mode: exiting")
                break

            for _ in range(self.runtime_applier.next_cycle_sec):
                if self.shutdown_requested:
                    break
                time.sleep(1)

        logging.info("=" * 60)
        logging.info("BOT GRACEFUL SHUTDOWN")
        state = self.context.state_store.load_state()
        self.context.state_store.save_state(state)
        self.context.notifier.notify_bot_stopped("graceful_shutdown")
        write_live_status(
            is_running=False,
            execution_mode=self.context.cfg.execution_mode,
            cycle_count=self.cycle_count,
            last_cycle_duration=self.last_cycle_duration,
            portfolio=self.last_portfolio,
            current_coin="stopped"
        )
        logging.info("State saved. Goodbye.")
        logging.info("=" * 60)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hyperliquid Trading Bot — DeepSeek v3.2 - runtime strategy params"
    )
    parser.add_argument("--single-cycle", action="store_true", help="Run single cycle and exit")
    return parser.parse_args()