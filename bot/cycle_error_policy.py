class CycleErrorPolicy:
    """Defines cycle failure behavior in one place."""

    def handle_cycle_error(
        self,
        context,
        telemetry_service,
        state_service,
        cycle_count: int,
        last_cycle_duration: float,
        last_portfolio,
        error: Exception,
    ) -> None:
        context.metrics.increment("cycles_failed")
        context.notifier.notify_error(f"Cycle failed: {type(error).__name__}: {str(error)[:200]}")
        telemetry_service.write_live(
            is_running=True,
            execution_mode=context.cfg.execution_mode,
            cycle_count=cycle_count,
            last_cycle_duration=last_cycle_duration,
            portfolio=last_portfolio,
            error=f"{type(error).__name__}: {str(error)[:200]}",
        )
        state_service.persist_cycle_failure(context.state_store)