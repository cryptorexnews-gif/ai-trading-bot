"""
Atomic file I/O utilities with restrictive permissions.
Used by state_store, position_manager, and bot_live_writer.
"""

import json
import os
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
    """
    ensure_secure_directory(path)
    tmp_path = path + ".tmp"

    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_PERMISSION)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, cls=cls)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        raise

    os.replace(tmp_path, path)
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