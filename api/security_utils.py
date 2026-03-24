import os
from ipaddress import ip_address, ip_network
from typing import Any, List


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


def parse_ip_allowlist(raw: str) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def get_request_client_ip(request_obj: Any, trust_proxy_headers: bool = True) -> str:
    """
    Return client IP.
    - Uses X-Forwarded-For only when request arrives from loopback (local reverse proxy).
    - Falls back to request.remote_addr.
    """
    remote_addr = str(getattr(request_obj, "remote_addr", "") or "").strip()

    if trust_proxy_headers and is_loopback_ip(remote_addr):
        xff = str(getattr(request_obj, "headers", {}).get("X-Forwarded-For", "") or "").strip()
        if xff:
            first_hop = xff.split(",")[0].strip()
            if first_hop:
                return first_hop

    return remote_addr or "unknown"


def ip_in_allowlist(client_ip: str, allowlist: List[str]) -> bool:
    """
    Supports exact IP and CIDR notation.
    Examples:
      - 203.0.113.10
      - 203.0.113.0/24
      - 2001:db8::/32
    """
    if not allowlist:
        return True

    try:
        client = ip_address(client_ip)
    except ValueError:
        return False

    for entry in allowlist:
        raw = str(entry).strip()
        if not raw:
            continue

        try:
            if "/" in raw:
                if client in ip_network(raw, strict=False):
                    return True
            else:
                if client == ip_address(raw):
                    return True
        except ValueError:
            continue

    return False