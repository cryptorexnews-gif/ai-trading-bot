import os
from ipaddress import ip_address


def env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").strip().lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def is_loopback_ip(value: str) -> bool:
    if not value:
        return False

    candidate = value.strip()

    if candidate.startswith("::ffff:"):
        candidate = candidate.replace("::ffff:", "", 1)

    if candidate.count(":") == 1 and "." in candidate:
        candidate = candidate.split(":", 1)[0]

    try:
        return ip_address(candidate).is_loopback
    except ValueError:
        return candidate in ("localhost",)