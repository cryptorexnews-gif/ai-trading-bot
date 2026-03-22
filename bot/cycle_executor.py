import logging
import time
from decimal import Decimal
from typing import Any, Dict, Optional

from bot_live_writer import write_live_status


class CycleExecutor:
    """Executes one bot trading cycle with state/metrics persistence."""

    def __init__(self, context):
        self.context = context

    def _persist_metrics(self) -> None:
        metrics_data = self.context.metrics.get_all_metrics()
        serializable = {}
        for key, value in metrics_data.items():
            if isinstance(value, Decimal):
                serializable[key] = str(value)
            elif isinstance(value, list):
                serializable[key] = [float(v) if isinstance(v, (Decimal, float)) else v for v in value]
            else:
                serializable[key] = value
        self.context.state_store.save_metrics(serializable)

    def execute_cycle(
        self,
        cycle_count: int,
        current_next_cycle_sec: int,
        shutdown_requested: bool,
        last_cycle_duration: float,
        last_portfolio: Optional[Any],
    ) -> Dict[str, Any]:
        cycle_start = time.time()
        self.context.orchestrator.set_cycle_count(cycle_count)

        try:
            logging.info("=" * 60)
            logging.info(f"Starting trading cycle #{cycle_count} ({current_next_cycle_sec}s)")

            self.context.orchestrator._run_health_check(cycle_count)

            portfolio = self.context.orchestrator._fetch_portfolio()

            write_live_status(
                is_running=True,
                execution_mode=self.context.cfg.execution_mode,
                cycle_count=cycle_count,
                last_cycle_duration=last_cycle_duration,
                portfolio=portfolio,
                current_coin="scanning..."
            )

            if portfolio.total_balance <= 0:
                logging.warning("Portfolio balance zero or negative, skipping cycle")
                return {
                    "success": True,
                    "last_cycle_duration": time.time() - cycle_start,
                    "last_portfolio": portfolio,
                }

            state = self.context.state_store.load_state()
            self.context.state_store.add_equity_snapshot(
                state,
                balance=portfolio.total_balance,
                unrealized_pnl=portfolio.get_total_unrealized_pnl(),
                position_count=len(portfolio.positions),
                margin_usage=portfolio.margin_usage,
            )

            daily_key = self.context.state_store.day_key(time.time())
            daily_notional_used = Decimal(str(state.get("daily_notional_by_day", {}).get(daily_key, "0")))
            peak = Decimal(str(state.get("peak_portfolio_value", "0")))
            consecutive_losses = state.get("consecutive_losses", 0)

            triggered = self.context.orchestrator._process_risk_triggers(portfolio)
            if triggered > 0:
                logging.info(f"SL/TP/Trailing/BE triggered {triggered} closes, refreshing portfolio")
                portfolio = self.context.orchestrator._fetch_portfolio()

            portfolio = self.context.orchestrator._handle_emergency_derisk(portfolio)

            trades_executed, notional_added = self.context.orchestrator._analyze_and_trade(
                portfolio=portfolio,
                state=state,
                daily_notional_used=daily_notional_used,
                peak=peak,
                consecutive_losses=consecutive_losses,
                shutdown_requested=shutdown_requested,
            )

            if notional_added > 0:
                state["daily_notional_by_day"] = self.context.state_store.add_daily_notional(
                    state.get("daily_notional_by_day", {}),
                    time.time(),
                    notional_added
                )
            if portfolio.total_balance > peak:
                state["peak_portfolio_value"] = str(portfolio.total_balance)
                self.context.metrics.set_gauge("peak_portfolio_value", portfolio.total_balance)

            state["consecutive_failed_cycles"] = 0
            self.context.state_store.save_state(state)

            cycle_duration = time.time() - cycle_start
            self.context.metrics.record_histogram("cycle_duration_seconds", cycle_duration)
            self.context.metrics.increment("cycles_total")
            self._persist_metrics()

            summary = self.context.state_store.get_performance_summary(state)
            if summary["total_trades"] > 0:
                logging.info(
                    f"Performance: {summary['total_trades']} trades, "
                    f"win_rate={summary['win_rate']:.1f}%, wins={summary['wins']}, "
                    f"losses={summary['losses']}, holds={summary['holds']}"
                )

            write_live_status(
                is_running=True,
                execution_mode=self.context.cfg.execution_mode,
                cycle_count=cycle_count,
                last_cycle_duration=cycle_duration,
                portfolio=portfolio,
                current_coin="idle"
            )
            logging.info(
                f"Cycle #{cycle_count} complete: {trades_executed} trades, "
                f"duration={cycle_duration:.1f}s"
            )

            return {
                "success": True,
                "last_cycle_duration": cycle_duration,
                "last_portfolio": portfolio,
            }

        except Exception as e:
            logging.error(f"Cycle failed: {type(e).__name__}: {e}", exc_info=True)
            self.context.metrics.increment("cycles_failed")
            self.context.notifier.notify_error(f"Cycle failed: {type(e).__name__}: {str(e)[:200]}")
            write_live_status(
                is_running=True,
                execution_mode=self.context.cfg.execution_mode,
                cycle_count=cycle_count,
                last_cycle_duration=last_cycle_duration,
                portfolio=last_portfolio,
                error=f"{type(e).__name__}: {str(e)[:200]}"
            )
            state = self.context.state_store.load_state()
            state["consecutive_failed_cycles"] = state.get("consecutive_failed_cycles", 0) + 1
            self.context.state_store.save_state(state)
            return {
                "success": False,
                "last_cycle_duration": last_cycle_duration,
                "last_portfolio": last_portfolio,
            }