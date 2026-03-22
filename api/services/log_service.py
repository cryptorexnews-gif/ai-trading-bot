import json
import os
from typing import Any, Callable, Dict, List, Tuple


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
            if "message" in entry:
                entry["message"] = sanitizer(str(entry["message"]))
            if "exception" in entry:
                entry["exception"] = sanitizer(str(entry["exception"]))
            log_entries.append(entry)
        except json.JSONDecodeError:
            log_entries.append({
                "message": sanitizer(line),
                "level": "INFO",
            })

    return list(reversed(log_entries)), len(lines)