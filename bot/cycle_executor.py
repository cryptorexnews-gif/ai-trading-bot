import logging
import time

from bot.contracts import CycleExecutionInput, CycleExecutionResult
from bot.cycle_error_policy import CycleErrorPolicy
from bot.cycle_state_service import CycleStateService
from bot.cycle_telemetry_service import CycleTelemetryService


class CycleExecutor:
    """Executes one bot trading cycle with state, telemetry, and error policy services."""

    def __init__(self, context):
        self.context = context
        self.state_service = CycleStateService()
        self.telemetry_service = CycleTelemetryService()
        self.error_policy = CycleErrorPolicy()

    def execute_cycle(self, execution_input: CycleExecutionInput) -> CycleExecutionResult:
        cycle_start = time.time()
        self.context.orchestrator.set_cycle_count(execution_input.cycle_count)

        try:
            logging.info("=" * 60)
            logging.info(
                f"Starting trading cycle #{execution_input.cycle_count} "
                f"({execution_input.current_next_cycle_sec}s)"
            )

            phase_start = time.time()
            self.context.orchestrator.run_health_check(execution_input.cycle_count)
            self.telemetry_service.record_phase_duration(self.context.metrics, "health_check", time.time() - phase_start)

            phase_start = time.time()
            portfolio = self.context.orchestrator.fetch_portfolio()
            self.telemetry_service.record_phase_duration(self.context.metrics, "fetch_portfolio", time.time() - phase_start)

            self.telemetry_service.write_live(
                is_running=True,
                execution_mode=self.context.cfg.execution_mode,
                cycle_count=execution_input.cycle_count,
                last_cycle_duration=execution_input.last_cycle_duration,
                portfolio=portfolio,
                current_coin="scanning...",
            )

            if portfolio.total_balance <= 0:
                logging.warning("Portfolio balance zero or negative, skipping cycle")
                return CycleExecutionResult(
                    success=True,
                    last_cycle_duration=time.time() - cycle_start,
                    last_portfolio=portfolio,
                )

            phase_start = time.time()
            loaded = self.state_service.load_cycle_state(self.context.state_store)
            state = loaded["state"]
            daily_notional_used = loaded["daily_notional_used"]
            peak = loaded["peak"]
            consecutive_losses = loaded["consecutive_losses"]
            self.state_service.add_equity_snapshot(self.context.state_store, state, portfolio)
            self.telemetry_service.record_phase_duration(self.context.metrics, "state_load_snapshot", time.time() - phase_start)

            phase_start = time.time()
            triggered = self.context.orchestrator.process_risk_triggers(portfolio)
            self.telemetry_service.record_phase_duration(self.context.metrics, "risk_triggers", time.time() - phase_start)
            if triggered > 0:
                logging.info(f"SL/TP/Trailing/BE triggered {triggered} closes, refreshing portfolio")
                phase_start = time.time()
                portfolio = self.context.orchestrator.fetch_portfolio()
                self.telemetry_service.record_phase_duration(self.context.metrics, "fetch_portfolio_after_triggers", time.time() - phase_start)

            phase_start = time.time()
            portfolio = self.context.orchestrator.handle_emergency_derisk(portfolio)
            self.telemetry_service.record_phase_duration(self.context.metrics, "emergency_derisk", time.time() - phase_start)

            phase_start = time.time()
            trades_executed, notional_added = self.context.orchestrator.analyze_and_trade(
                portfolio=portfolio,
                state=state,
                daily_notional_used=daily_notional_used,
                peak=peak,
                consecutive_losses=consecutive_losses,
                shutdown_requested=execution_input.shutdown_requested,
            )
            self.telemetry_service.record_phase_duration(self.context.metrics, "coin_analysis_execution", time.time() - phase_start)

            phase_start = time.time()
            self.state_service.persist_cycle_success(
                state_store=self.context.state_store,
                metrics=self.context.metrics,
                state=state,
                portfolio=portfolio,
                peak=peak,
                notional_added=notional_added,
            )
            self.telemetry_service.record_phase_duration(self.context.metrics, "state_persist", time.time() - phase_start)

            cycle_duration = time.time() - cycle_start
            self.telemetry_service.record_cycle_duration(self.context.metrics, cycle_duration)
            self.context.metrics.increment("cycles_total")
            self.telemetry_service.persist_metrics(self.context.metrics, self.context.state_store)

            summary = self.context.state_store.get_performance_summary(state)
            if summary["total_trades"] > 0:
                logging.info(
                    f"Performance: {summary['total_trades']} trades, "
                    f"win_rate={summary['win_rate']:.1f}%, wins={summary['wins']}, "
                    f"losses={summary['losses']}, holds={summary['holds']}"
                )

            self.telemetry_service.write_live(
                is_running=True,
                execution_mode=self.context.cfg.execution_mode,
                cycle_count=execution_input.cycle_count,
                last_cycle_duration=cycle_duration,
                portfolio=portfolio,
                current_coin="idle",
            )
            logging.info(
                f"Cycle #{execution_input.cycle_count} complete: {trades_executed} trades, "
                f"duration={cycle_duration:.1f}s"
            )

            return CycleExecutionResult(
                success=True,
                last_cycle_duration=cycle_duration,
                last_portfolio=portfolio,
            )

        except Exception as e:
            logging.error(f"Cycle failed: {type(e).__name__}: {e}", exc_info=True)
            self.error_policy.handle_cycle_error(
                context=self.context,
                telemetry_service=self.telemetry_service,
                state_service=self.state_service,
                cycle_count=execution_input.cycle_count,
                last_cycle_duration=execution_input.last_cycle_duration,
                last_portfolio=execution_input.last_portfolio,
                error=e,
            )
            return CycleExecutionResult(
                success=False,
                last_cycle_duration=execution_input.last_cycle_duration,
                last_portfolio=execution_input.last_portfolio,
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )