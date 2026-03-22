from typing import Any, Dict, List, Optional


def extract_order_ids(exchange_result: Dict[str, Any]) -> List[int]:
    ids: List[int] = []

    if not isinstance(exchange_result, dict):
        return ids

    statuses = exchange_result.get("response", {}).get("data", {}).get("statuses", [])
    if not isinstance(statuses, list):
        return ids

    for status in statuses:
        if not isinstance(status, dict):
            continue

        resting = status.get("resting", {})
        if not isinstance(resting, dict):
            continue

        oid = resting.get("oid")
        if oid is None:
            continue

        try:
            ids.append(int(oid))
        except (TypeError, ValueError):
            continue

    return ids


def is_master_wallet_not_found_error(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") != "err":
        return False
    message = str(result.get("response", "")).lower()
    return "user or api wallet" in message and "does not exist" in message