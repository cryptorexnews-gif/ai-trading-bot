import json
import os
from typing import Any, Callable, Dict, List, Tuple


def _sanitize_value(value: Any, sanitizer: Callable[[str], str]) -> Any:
    if isinstance(value, str):
        return sanitizer(value)

    if isinstance(value, dict):
        sanitized_dict: Dict[str, Any] = {}
        for key, item in value.items():
            safe_key = sanitizer(str(key))
            sanitized_dict[safe_key] = _sanitize_value(item, sanitizer)
        return sanitized_dict

    if isinstance(value, list):
        return [_sanitize_value(item, sanitizer) for item in value]

    return value


def read_recent_logs(
    log_file: str,
    limit: int,
    sanitizer: Callable[[str], str],
) -> Tuple[List[Dict[str, Any]], int]:
    if not os.path.exists(log_file):
        return [], 0

    with open(log_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    recent_lines = lines[-limit:]
    log_entries: List[Dict[str, Any]] = []

    for line in recent_lines:
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
            sanitized_entry = _sanitize_value(entry, sanitizer)
            if isinstance(sanitized_entry, dict):
                log_entries.append(sanitized_entry)
            else:
                log_entries.append({
                    "message": sanitizer(str(sanitized_entry)),
                    "level": "INFO",
                })
        except json.JSONDecodeError:
            log_entries.append({
                "message": sanitizer(line),
                "level": "INFO",
            })

    return list(reversed(log_entries)), len(lines)