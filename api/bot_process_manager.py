import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional


class BotProcessManager:
    """Gestisce il processo del bot lanciato dal server API."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._started_at: Optional[float] = None

    def is_running(self) -> bool:
        with self._lock:
            if self._process is None:
                return False
            if self._process.poll() is not None:
                self._process = None
                self._started_at = None
                return False
            return True

    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return {"ok": False, "reason": "already_running"}

            cmd = [sys.executable, "hyperliquid_bot_executable_orders.py"]
            self._process = subprocess.Popen(cmd)
            self._started_at = time.time()

            return {
                "ok": True,
                "pid": self._process.pid,
                "started_at": self._started_at
            }

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._process = None
                self._started_at = None
                return {"ok": False, "reason": "not_running"}

            process = self._process
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

            pid = process.pid
            self._process = None
            self._started_at = None

            return {"ok": True, "pid": pid}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            return {
                "is_running": running,
                "pid": self._process.pid if running else None,
                "started_at": self._started_at
            }


bot_process_manager = BotProcessManager()