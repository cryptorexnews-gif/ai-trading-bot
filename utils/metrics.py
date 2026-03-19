from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from utils.decimals import to_decimal


class MetricsCollector:
    """
    Raccoglie e gestisce metriche dell'applicazione.
    Thread-safe per operazioni di base (non per aggiornamenti ad alta frequenza).
    """
    
    def __init__(self):
        self._metrics: Dict[str, Any] = {
            # Contatori
            "cycles_total": 0,
            "cycles_failed": 0,
            "trades_executed_total": 0,
            "holds_total": 0,
            "risk_rejections_total": 0,
            "execution_failures_total": 0,
            "llm_calls_total": 0,
            "llm_errors_total": 0,
            "api_errors_total": 0,
            
            # Gauge
            "current_balance": Decimal("0"),
            "available_balance": Decimal("0"),
            "margin_usage": Decimal("0"),
            "open_positions_count": 0,
            "consecutive_failed_cycles": 0,
            
            # Istogrammi (memorizzati come liste per semplicità)
            "cycle_duration_seconds": [],
            "order_sizes": [],
            "slippage_bps": [],
            
            # Derivati
            "daily_notional_total": Decimal("0"),
            "peak_portfolio_value": Decimal("0"),
            
            # Metadati
            "started_at": datetime.utcnow().isoformat() + "Z",
            "last_updated": datetime.utcnow().isoformat() + "Z"
        }
    
    def increment(self, metric: str, value: int = 1) -> None:
        """Incrementa una metrica contatore."""
        if metric not in self._metrics:
            self._metrics[metric] = 0
        self._metrics[metric] += value
        self._metrics["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def set_gauge(self, metric: str, value: Any) -> None:
        """Imposta una metrica gauge."""
        if metric in ["current_balance", "available_balance", "margin_usage", "daily_notional_total", "peak_portfolio_value"]:
            self._metrics[metric] = to_decimal(value)
        else:
            self._metrics[metric] = value
        self._metrics["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def record_histogram(self, metric: str, value: float) -> None:
        """Registra un valore istogramma (aggiunge alla lista)."""
        if metric not in self._metrics:
            self._metrics[metric] = []
        self._metrics[metric].append(value)
        # Mantieni solo gli ultimi 1000 campioni per evitare crescita memoria
        if len(self._metrics[metric]) > 1000:
            self._metrics[metric] = self._metrics[metric][-1000:]
        self._metrics["last_updated"] = datetime.utcnow().isoformat() + "Z"
    
    def get_metric(self, metric: str, default: Any = None) -> Any:
        """Ottieni un valore metrica."""
        return self._metrics.get(metric, default)
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Ottieni tutte le metriche come dizionario."""
        return self._metrics.copy()
    
    def reset_counters(self) -> None:
        """Resetta metriche contatore a zero (ma mantiene gauge e istogrammi)."""
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
        Esporta metriche in formato testo Prometheus.
        """
        lines = []
        
        # Contatori
        counters = [
            ("cycles_total", "Numero totale di cicli di trading"),
            ("cycles_failed", "Numero totale di cicli di trading falliti"),
            ("trades_executed_total", "Numero totale di trade eseguiti"),
            ("holds_total", "Numero totale di decisioni hold"),
            ("risk_rejections_total", "Numero totale di rifiuti del risk manager"),
            ("execution_failures_total", "Numero totale di fallimenti esecuzione"),
            ("llm_calls_total", "Numero totale di chiamate API LLM"),
            ("llm_errors_total", "Numero totale di errori API LLM"),
            ("api_errors_total", "Numero totale di errori API (tutte le fonti)")
        ]
        
        for metric, help_text in counters:
            value = self._metrics.get(metric, 0)
            lines.append(f"# HELP {metric} {help_text}")
            lines.append(f"# TYPE {metric} counter")
            lines.append(f"{metric} {value}")
        
        # Gauge
        gauges = [
            ("current_balance", "Saldo totale corrente in USD", "gauge"),
            ("available_balance", "Saldo disponibile corrente in USD", "gauge"),
            ("margin_usage", "Uso margine corrente come rapporto (0-1)", "gauge"),
            ("open_positions_count", "Numero di posizioni aperte", "gauge"),
            ("consecutive_failed_cycles", "Cicli falliti consecutivi correnti", "gauge"),
            ("daily_notional_total", "Totale notionale scambiato oggi in USD", "gauge"),
            ("peak_portfolio_value", "Valore portfolio di picco in USD", "gauge")
        ]
        
        for metric, help_text, mtype in gauges:
            value = self._metrics.get(metric, 0)
            lines.append(f"# HELP {metric} {help_text}")
            lines.append(f"# TYPE {metric} {mtype}")
            lines.append(f"{metric} {float(value)}")
        
        # Istogrammi (riassunti come summary)
        histograms = [
            ("cycle_duration_seconds", "Durata ciclo di trading in secondi"),
            ("order_sizes", "Dimensioni ordini in USD"),
            ("slippage_bps", "Slippage in punti base")
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