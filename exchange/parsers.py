from typing import Any, Dict, List, Optional


def extract_order_ids(exchange_result: Dict[str, Any]) -> List[int]:
    ids: List[int] = []
    statuses = exchange_result.get("response", {}).get("data", {}).get("statuses", [])
    for status in statuses:
        resting = status.get("resting", {})
        oid = resting.get("oid")
        if oid is not None:
            ids.append(int(oid))
    return ids


def is_vault_not_registered_error(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") != "err":
        return False
    message = str(result.get("response", "")).lower()
    return "vault not registered" in message


def is_user_or_api_wallet_not_found_error(result: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(result, dict):
        return False
    if result.get("status") != "err":
        return False
    message = str(result.get("response", "")).lower()
    return "user or api wallet" in message and "does not exist" in message