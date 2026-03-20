from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from utils.decimals import to_decimal


class HealthStatus:
    """Costanti stato salute."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"


class HealthCheckResult:
    """Risultato di un singolo controllo salute."""

    def __init__(
        self,
        name: str,
        status: str,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None
    ):
        self.name = name
        self.status = status
        self.message = message
        self.details = details or {}
        self.timestamp = timestamp or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat() + "Z"
        }


class HealthMonitor:
    """
    Monitora salute generale del sistema con controlli multipli.
    """

    def __init__(self):
        self._checks: List[Dict[str, Any]] = []
        self._last_check_time: Optional[datetime] = None
        self._overall_status = HealthStatus.STARTING

    def add_check(
        self,
        name: str,
        check_func: Callable[[], HealthCheckResult],
        interval: float = 60.0,
        timeout: float = 10.0
    ) -> None:
        """
        Aggiungi un controllo salute.

        Args:
            name: Nome unico per il controllo
            check_func: Funzione che restituisce HealthCheckResult
            interval: Ogni quanto eseguire questo controllo (secondi)
            timeout: Timeout per il controllo (secondi)
        """
        self._checks.append({
            "name": name,
            "func": check_func,
            "interval": interval,
            "timeout": timeout,
            "last_run": None,
            "last_result": None
        })

    def run_check(self, check: Dict[str, Any]) -> HealthCheckResult:
        """Esegui un singolo controllo salute."""
        try:
            result = check["func"]()
            check["last_result"] = result
            check["last_run"] = datetime.utcnow()
            return result
        except Exception as e:
            result = HealthCheckResult(
                name=check["name"],
                status=HealthStatus.UNHEALTHY,
                message=f"Controllo fallito con eccezione: {str(e)}",
                details={"exception": type(e).__name__, "error": str(e)}
            )
            check["last_result"] = result
            check["last_run"] = datetime.utcnow()
            return result

    def run_all_checks(self) -> Dict[str, Any]:
        """
        Esegui tutti i controlli salute e restituisci stato generale.
        """
        results = []
        overall_status = HealthStatus.HEALTHY

        for check in self._checks:
            result = self.run_check(check)
            results.append(result.to_dict())

            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED

        self._overall_status = overall_status
        self._last_check_time = datetime.utcnow()

        return {
            "status": overall_status,
            "timestamp": self._last_check_time.isoformat() + "Z",
            "checks": results,
            "summary": {
                "total": len(results),
                "healthy": sum(1 for r in results if r["status"] == HealthStatus.HEALTHY),
                "degraded": sum(1 for r in results if r["status"] == HealthStatus.DEGRADED),
                "unhealthy": sum(1 for r in results if r["status"] == HealthStatus.UNHEALTHY)
            }
        }

    def get_overall_status(self) -> str:
        """Ottieni stato salute generale."""
        return self._overall_status

    def is_healthy(self) -> bool:
        """Controlla se sistema è completamente healthy."""
        return self._overall_status == HealthStatus.HEALTHY

    def is_degraded(self) -> bool:
        """Controlla se sistema è degradato ma non unhealthy."""
        return self._overall_status == HealthStatus.DEGRADED

    def is_unhealthy(self) -> bool:
        """Controlla se sistema è unhealthy."""
        return self._overall_status == HealthStatus.UNHEALTHY


def check_exchange_connectivity(exchange_client) -> HealthCheckResult:
    """Controlla se API exchange è raggiungibile."""
    try:
        meta = exchange_client.get_meta(force_refresh=True)
        if meta:
            return HealthCheckResult(
                name="exchange_connectivity",
                status=HealthStatus.HEALTHY,
                message="API exchange raggiungibile",
                details={"assets_count": len(meta.get("universe", []))}
            )
        return HealthCheckResult(
            name="exchange_connectivity",
            status=HealthStatus.UNHEALTHY,
            message="API exchange ha restituito nessun metadato"
        )
    except Exception as e:
        return HealthCheckResult(
            name="exchange_connectivity",
            status=HealthStatus.UNHEALTHY,
            message=f"API exchange irraggiungibile: {str(e)}",
            details={"exception": type(e).__name__}
        )


def check_wallet_balance(exchange_client, wallet_address: str) -> HealthCheckResult:
    """Controlla se saldo wallet è accessibile e positivo."""
    try:
        state = exchange_client.get_user_state(wallet_address)
        if state is None:
            return HealthCheckResult(
                name="wallet_balance",
                status=HealthStatus.UNHEALTHY,
                message="Impossibile recuperare stato wallet"
            )

        margin_summary = state.get("marginSummary", {})
        total_balance = to_decimal(margin_summary.get("accountValue", 0))

        if total_balance <= 0:
            return HealthCheckResult(
                name="wallet_balance",
                status=HealthStatus.UNHEALTHY,
                message="Saldo wallet zero o negativo",
                details={"balance": str(total_balance)}
            )

        return HealthCheckResult(
            name="wallet_balance",
            status=HealthStatus.HEALTHY,
            message="Saldo wallet positivo",
            details={"balance": str(total_balance)}
        )
    except Exception as e:
        return HealthCheckResult(
            name="wallet_balance",
            status=HealthStatus.UNHEALTHY,
            message=f"Errore nel recupero saldo wallet: {str(e)}"
        )


def check_disk_space(path: str, min_free_gb: float = 1.0) -> HealthCheckResult:
    """Controlla se c'è abbastanza spazio disco."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        free_gb = free / (1024**3)

        if free_gb < min_free_gb:
            return HealthCheckResult(
                name="disk_space",
                status=HealthStatus.UNHEALTHY,
                message=f"Spazio disco basso: {free_gb:.2f} GB liberi (min {min_free_gb} GB)",
                details={"free_gb": free_gb, "total_gb": total / (1024**3), "used_gb": used / (1024**3)}
            )

        return HealthCheckResult(
            name="disk_space",
            status=HealthStatus.HEALTHY,
            message=f"Spazio disco sufficiente: {free_gb:.2f} GB liberi",
            details={"free_gb": free_gb}
        )
    except Exception as e:
        return HealthCheckResult(
            name="disk_space",
            status=HealthStatus.UNHEALTHY,
            message=f"Impossibile controllare spazio disco: {str(e)}"
        )


def check_file_writable(path: str) -> HealthCheckResult:
    """Controlla se un file/directory è scrivibile."""
    try:
        import os
        test_file = os.path.join(path, ".health_check_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return HealthCheckResult(
            name="file_writable",
            status=HealthStatus.HEALTHY,
            message=f"Percorso {path} è scrivibile"
        )
    except Exception as e:
        return HealthCheckResult(
            name="file_writable",
            status=HealthStatus.UNHEALTHY,
            message=f"Percorso {path} non è scrivibile: {str(e)}"
        )