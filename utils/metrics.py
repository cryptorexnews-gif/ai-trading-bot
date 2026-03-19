from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from utils.decimals import to_decimal


class MetricsCollector:
    """
    Collect and manage application metrics.
    Thread-safe for basic operations (not for high-frequency updates).
    """
    
    def __init__(self):
        self._metrics: Dict[str, Any] = {
            # Counters
            "cycles_total": 0,
            "cycles_failed": 0,
            "trades_executed_total": 0,
            "holds_total": 0,
            "risk_rejections_total": 0,
            "execution_failures_total": 0,
            "llm_calls_total": 0,
            "llm_errors_total": 0,
            "api_errors_total": 0,
            
            # Gauges
            "current_balance": Decimal("0"),
            "available_balance": Decimal("0"),
            "margin_usage": Decimal("0"),
            "open_positions_count": 0,
            "consecutive_failed_cycles": 0,
            
            # Histograms (stored as lists for simplicity)
            "cycle_duration_seconds": [],
            "order_sizes": [],
            "slippage_bps": [],
            
            # Derived
            "daily_notional_total": Decimal("0"),
            "peak_portfolio_value": Decimal("0"),
            
            # Metadata
            "started_at": datetime.utcnow().isoformat() + "Z",
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
    
    def increment(self, metric: str, value: int = 1) -> None:
        """Increment a counter metric."""
        if metric not in self._metrics:
            self._metrics[metric] = 0
        self._metrics[metric] += value
        self._metrics["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def set_gauge(self, metric: str, value: Any) -> None:
        """Set a gauge metric."""
        if metric in ["current_balance", "available_balance", "margin_usage", "daily_notional_total", "peak_portfolio_value"]:
            self._metrics[metric] = to_decimal(value)
        else:
            self._metrics[metric] = value
        self._metrics["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def record_histogram(self, metric: str, value: float) -> None:
        """Record a histogram value (append to list)."""
        if metric not in self._metrics:
            self._metrics[metric] = []
        self._metrics[metric].append(value)
        # Keep only last 1000 samples to prevent memory growth
        if len(self._metrics[metric]) > 1000:
            self._metrics[metric] = self._metrics[metric][-1000:]
        self._metrics["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def get_metric(self, metric: str, default: Any = None) -> Any:
        """Get a metric value."""
        return self._metrics.get(metric, default)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all metrics as a dictionary."""
        return self._metrics.copy()
    
    def reset_counters(self) -> None:
        """Reset counter metrics to zero (but keep gauges and histograms)."""
        counters = [
            "cycles_total", "cycles_failed", "trades_executed_total",
            "holds_total", "risk_rejections_total", "execution_failures_total",
            "llm_calls_total", "llm_errors_total", "api_errors_total"
        ]
        for counter in counters:
            self._metrics[counter] = 0
        self._metrics["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def to_prometheus_format(self) -> str:
        """
        Export metrics in Prometheus text format.
        """
        lines = []
        
        # Counters
        counters = [
            ("cycles_total", "Total number of trading cycles"),
            ("cycles_failed", "Total number of failed trading cycles"),
            ("trades_executed_total", "Total number of trades executed"),
            ("holds_total", "Total number of hold decisions"),
            ("risk_rejections_total", "Total number of risk manager rejections"),
            ("execution_failures_total", "Total number of execution failures"),
            ("llm_calls_total", "Total number of LLM API calls"),
            ("llm_errors_total", "Total number of LLM API errors"),
            ("api_errors_total", "Total number of API errors (all sources)")
        ]
        
        for metric, help_text in counters:
            value = self._metrics.get(metric, 0)
            lines.append(f"# HELP {metric} {help_text}")
            lines.append(f"# TYPE {metric} counter")
            lines.append(f"{metric} {value}")
        
        # Gauges
        gauges = [
            ("current_balance", "Current total balance in USD", "gauge"),
            ("available_balance", "Current available balance in USD", "gauge"),
            ("margin_usage", "Current margin usage as ratio (0-1)", "gauge"),
            ("open_positions_count", "Number of open positions", "gauge"),
            ("consecutive_failed_cycles", "Current consecutive failed cycles", "gauge"),
            ("daily_notional_total", "Total notional traded today in USD", "gauge"),
            ("peak_portfolio_value", "Peak portfolio value in USD", "gauge")
        ]
        
        for metric, help_text, mtype in gauges:
            value = self._metrics.get(metric, 0)
            lines.append(f"# HELP {metric} {help_text}")
            lines.append(f"# TYPE {metric} {mtype}")
            lines.append(f"{metric} {float(value)}")
        
        # Histograms (summarized as summary)
        histograms = [
            ("cycle_duration_seconds", "Trading cycle duration in seconds"),
            ("order_sizes", "Order sizes in USD"),
            ("slippage_bps", "Slippage in basis points")
        ]
        
        for metric, help_text in histograms:
            values = self._metrics.get(metric, [])
            if values:
                count = len(values)
                total = sum(values)
                avg = total / count if count > 0 else 0
                lines.append(f"# HELP {metric} {help_text}")
                lines.append(f"# TYPE {metric} summary")
                lines.append(f"{metric}_count {count}")
                lines.append(f"{metric}_sum {total}")
                lines.append(f"{metric}_average {avg}")
        
        return "\n".join(lines) + "\n"