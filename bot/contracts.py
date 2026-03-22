from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class CycleExecutionInput:
    cycle_count: int
    current_next_cycle_sec: int
    shutdown_requested: bool
    last_cycle_duration: float
    last_portfolio: Optional[Any]


@dataclass
class CycleExecutionResult:
    success: bool
    last_cycle_duration: float
    last_portfolio: Optional[Any]
    error: str = ""