from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from utils.decimals import to_decimal


class HealthStatus:
    """Health status constants."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"


class HealthCheckResult:
    """Result of a single health check."""

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
    Monitor overall system health with multiple checks.
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
        Add a health check.

        Args:
            name: Unique name for the check
            check_func: Function that returns HealthCheckResult
            interval: How often to run this check (seconds)
            timeout: Timeout for the check (seconds)
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
        """Run a single health check."""
        try:
            result = check["func"]()
            check["last_result"] = result
            check["last_run"] = datetime.utcnow()
            return result
        except Exception as e:
            result = HealthCheckResult(
                name=check["name"],
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed with exception: {str(e)}",
                details={"exception": type(e).__name__, "error": str(e)}
            )
            check["last_result"] = result
            check["last_run"] = datetime.utcnow()
            return result

    def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all health checks and return overall status.
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
        """Get the overall health status."""
        return self._overall_status

    def is_healthy(self) -> bool:
        """Check if system is fully healthy."""
        return self._overall_status == HealthStatus.HEALTHY

    def is_degraded(self) -> bool:
        """Check if system is degraded but not unhealthy."""
        return self._overall_status == HealthStatus.DEGRADED

    def is_unhealthy(self) -> bool:
        """Check if system is unhealthy."""
        return self._overall_status == HealthStatus.UNHEALTHY


def check_exchange_connectivity(exchange_client) -> HealthCheckResult:
    """Check if exchange API is reachable."""
    try:
        meta = exchange_client.get_meta(force_refresh=True)
        if meta:
            return HealthCheckResult(
                name="exchange_connectivity",
                status=HealthStatus.HEALTHY,
                message="Exchange API reachable",
                details={"assets_count": len(meta.get("universe", []))}
            )
        return HealthCheckResult(
            name="exchange_connectivity",
            status=HealthStatus.UNHEALTHY,
            message="Exchange API returned no metadata"
        )
    except Exception as e:
        return HealthCheckResult(
            name="exchange_connectivity",
            status=HealthStatus.UNHEALTHY,
            message=f"Exchange API unreachable: {str(e)}",
            details={"exception": type(e).__name__}
        )


def check_wallet_balance(exchange_client, wallet_address: str) -> HealthCheckResult:
    """Check if wallet balance is accessible and positive."""
    try:
        state = exchange_client.get_user_state(wallet_address)
        if state is None:
            return HealthCheckResult(
                name="wallet_balance",
                status=HealthStatus.UNHEALTHY,
                message="Could not fetch wallet state"
            )

        margin_summary = state.get("marginSummary", {})
        total_balance = to_decimal(margin_summary.get("accountValue", 0))

        if total_balance <= 0:
            return HealthCheckResult(
                name="wallet_balance",
                status=HealthStatus.UNHEALTHY,
                message="Wallet balance is zero or negative",
                details={"balance": str(total_balance)}
            )

        return HealthCheckResult(
            name="wallet_balance",
            status=HealthStatus.HEALTHY,
            message="Wallet balance positive",
            details={"balance": str(total_balance)}
        )
    except Exception as e:
        return HealthCheckResult(
            name="wallet_balance",
            status=HealthStatus.UNHEALTHY,
            message=f"Error fetching wallet balance: {str(e)}"
        )


def check_disk_space(path: str, min_free_gb: float = 1.0) -> HealthCheckResult:
    """Check if there's enough disk space."""
    try:
        import shutil
        total, used, free = shutil.disk_usage(path)
        free_gb = free / (1024**3)

        if free_gb < min_free_gb:
            return HealthCheckResult(
                name="disk_space",
                status=HealthStatus.UNHEALTHY,
                message=f"Low disk space: {free_gb:.2f} GB free (min {min_free_gb} GB)",
                details={"free_gb": free_gb, "total_gb": total / (1024**3), "used_gb": used / (1024**3)}
            )

        return HealthCheckResult(
            name="disk_space",
            status=HealthStatus.HEALTHY,
            message=f"Sufficient disk space: {free_gb:.2f} GB free",
            details={"free_gb": free_gb}
        )
    except Exception as e:
        return HealthCheckResult(
            name="disk_space",
            status=HealthStatus.UNHEALTHY,
            message=f"Could not check disk space: {str(e)}"
        )


def check_file_writable(path: str) -> HealthCheckResult:
    """Check if a file/directory is writable."""
    try:
        import os
        test_file = os.path.join(path, ".health_check_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return HealthCheckResult(
            name="file_writable",
            status=HealthStatus.HEALTHY,
            message=f"Path {path} is writable"
        )
    except Exception as e:
        return HealthCheckResult(
            name="file_writable",
            status=HealthStatus.UNHEALTHY,
            message=f"Path {path} is not writable: {str(e)}"
        )