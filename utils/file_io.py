"""
Atomic file I/O utilities with restrictive permissions.
Used by state_store, position_manager, and bot_live_writer.
"""

import json
import os
import time
from typing import Any, Dict

# Restrictive file permissions
FILE_PERMISSION = 0o600  # Owner read/write only
DIR_PERMISSION = 0o700   # Owner read/write/execute only


def ensure_secure_directory(path: str) -> None:
    """Create directory with restrictive permissions if it doesn't exist."""
    dir_path = os.path.dirname(path) or "."
    if dir_path != ".":
        os.makedirs(dir_path, mode=DIR_PERMISSION, exist_ok=True)
        try:
            os.chmod(dir_path, DIR_PERMISSION)
        except OSError:
            pass


def atomic_write_json(path: str, data: Dict[str, Any], cls: type = None) -> None:
    """
    Write JSON to file atomically (write to .tmp then rename).
    Sets restrictive file permissions (0o600).
    On Windows, retries os.replace on transient file-lock PermissionError.
    """
    ensure_secure_directory(path)

    # Use unique temp file to avoid collisions across close-in-time writes
    tmp_path = f"{path}.{os.getpid()}.{time.time_ns()}.tmp"

    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_PERMISSION)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, cls=cls)
        f.flush()
        os.fsync(f.fileno())

    replace_attempts = 10
    last_error: Exception = None

    for attempt in range(replace_attempts):
        try:
            os.replace(tmp_path, path)
            last_error = None
            break
        except PermissionError as e:
            last_error = e
            if attempt == replace_attempts - 1:
                break
            # Short backoff for transient Windows file lock
            time.sleep(0.05 * (attempt + 1))

    if last_error is not None:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise last_error

    try:
        os.chmod(path, FILE_PERMISSION)
    except OSError:
        pass


def read_json_file(path: str, default: Any = None) -> Any:
    """Read a JSON file, returning default on failure."""
    if default is None:
        default = {}
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default