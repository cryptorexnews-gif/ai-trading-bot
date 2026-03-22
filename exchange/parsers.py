from typing import Any, Dict, List, Optional


def extract_statuses(exchange_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(exchange_result, dict):
        return []

    statuses = exchange_result.get("response", {}).get("data", {}).get("statuses", [])
    if not isinstance(statuses, list):
        return []

    return [status for status in statuses if isinstance(status, dict)]


def _extract_oid_from_status(status: Dict[str, Any]) -> Optional[int]:
    if not isinstance(status, dict):
        return None

    # Common Hyperliquid shape: {"resting": {"oid": ...}}
    resting = status.get("resting", {})
    if isinstance(resting, dict):
        oid = resting.get("oid")
        if oid is not None:
            try:
                return int(oid)
            except (TypeError, ValueError):
                pass

    # Another possible shape: {"filled": {"oid": ...}}
    filled = status.get("filled", {})
    if isinstance(filled, dict):
        oid = filled.get("oid")
        if oid is not None:
            try:
                return int(oid)
            except (TypeError, ValueError):
                pass

    # Fallback direct field
    direct_oid = status.get("oid")
    if direct_oid is not None:
        try:
            return int(direct_oid)
        except (TypeError, ValueError):
            pass

    return None


def extract_order_ids(exchange_result: Dict[str, Any]) -> List[int]:
    ids: List[int] = []
    statuses = extract_statuses(exchange_result)

    for status in statuses:
        oid = _extract_oid_from_status(status)
        if oid is not None:
            ids.append(oid)

    return ids


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