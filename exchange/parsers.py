import re
from typing import Any, Dict, List, Optional


def extract_statuses(exchange_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(exchange_result, dict):
        return []

    statuses = exchange_result.get("response", {}).get("data", {}).get("statuses", [])
    if not isinstance(statuses, list):
        return []

    return [status for status in statuses if isinstance(status, dict)]


def _extract_oid_from_string(value: str) -> Optional[int]:
    if not isinstance(value, str):
        return None

    # Examples:
    # "oid: 123456"
    # "order oid=123456 accepted"
    # "123456"
    patterns = [
        r"(?i)\boid\s*[:=]\s*(\d+)\b",
        r"(?<!\d)(\d{3,})(?!\d)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            try:
                return int(match.group(1))
            except (TypeError, ValueError):
                continue
    return None


def _extract_oid_recursive(obj: Any, depth: int = 0) -> Optional[int]:
    if depth > 4:
        return None

    if isinstance(obj, int):
        return obj

    if isinstance(obj, str):
        return _extract_oid_from_string(obj)

    if isinstance(obj, dict):
        direct = obj.get("oid")
        if direct is not None:
            try:
                return int(direct)
            except (TypeError, ValueError):
                pass

        # Common Hyperliquid nested shapes
        for key in ("resting", "filled", "order", "data", "response"):
            if key in obj:
                nested_oid = _extract_oid_recursive(obj.get(key), depth + 1)
                if nested_oid is not None:
                    return nested_oid

        # Fallback: scan all dict values
        for value in obj.values():
            nested_oid = _extract_oid_recursive(value, depth + 1)
            if nested_oid is not None:
                return nested_oid

    if isinstance(obj, list):
        for item in obj:
            nested_oid = _extract_oid_recursive(item, depth + 1)
            if nested_oid is not None:
                return nested_oid

    return None


def extract_order_ids(exchange_result: Dict[str, Any]) -> List[int]:
    ids: List[int] = []
    statuses_raw = []

    if isinstance(exchange_result, dict):
        statuses_raw = exchange_result.get("response", {}).get("data", {}).get("statuses", [])

    if not isinstance(statuses_raw, list):
        return ids

    for status in statuses_raw:
        oid = _extract_oid_recursive(status)
        if oid is not None:
            ids.append(oid)

    # De-duplicate preserving order
    deduped: List[int] = []
    seen = set()
    for oid in ids:
        if oid in seen:
            continue
        seen.add(oid)
        deduped.append(oid)
    return deduped


def get_first_status_error(statuses: List[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(statuses, list):
        return None

    for status in statuses:
        if not isinstance(status, dict):
            continue
        if "error" in status:
            return str(status.get("error", "status_error"))
    return None


def has_acknowledged_order_status(statuses: List[Dict[str, Any]]) -> bool:
    """
    True when Hyperliquid status confirms order ack via known keys:
    - resting (order accepted and resting on book)
    - filled (immediate/market-like fill)
    """
    if not isinstance(statuses, list):
        return False

    for status in statuses:
        if not isinstance(status, dict):
            continue
        if isinstance(status.get("resting"), dict):
            return True
        if isinstance(status.get("filled"), dict):
            return True
        if status.get("oid") is not None:
            return True

    return False


def is_master_wallet_not_found_error(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") != "err":
        return False
    message = str(result.get("response", "")).lower()
    return "user or api wallet" in message and "does not exist" in message