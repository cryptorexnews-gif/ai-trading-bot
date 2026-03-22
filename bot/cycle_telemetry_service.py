from decimal import Decimal
from typing import Any, Dict

from bot_live_writer import write_live_status


class CycleTelemetryService:
    """Handles live status updates and metrics/phase telemetry for cycles."""

    def write_live(
        self,
        is_running: bool,
        execution_mode: str,
        cycle_count: int,
        last_cycle_duration: float,
        portfolio=None,
        current_coin: str = "",
        error: str = "",
    ) -> None:
        write_live_status(
            is_running=is_running,
            execution_mode=execution_mode,
            cycle_count=cycle_count,
            last_cycle_duration=last_cycle_duration,
            portfolio=portfolio,
            current_coin=current_coin,
            error=error,
        )

    def persist_metrics(self, metrics, state_store) -> None:
        metrics_data = metrics.get_all_metrics()
        serializable = {}
        for key, value in metrics_data.items():
            if isinstance(value, Decimal):
                serializable[key] = str(value)
            elif isinstance(value, list):
                serializable[key] = [float(v) if isinstance(v, (Decimal, float)) else v for v in value]
            else:
                serializable[key] = value
        state_store.save_metrics(serializable)

    def record_phase_duration(self, metrics, phase_name: str, duration_seconds: float) -> None:
        metric_key = f"phase_{phase_name}_seconds"
        metrics.record_histogram(metric_key, duration_seconds)

    def record_cycle_duration(self, metrics, duration_seconds: float) -> None:
        metrics.record_histogram("cycle_duration_seconds", duration_seconds)