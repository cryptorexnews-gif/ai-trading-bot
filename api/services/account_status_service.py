from typing import Any, Dict

from api.services.account_snapshot_service import get_hyperliquid_account_snapshot
from api.services.bot_payload_service import build_status_payload
from api.services.status_snapshot_service import load_status_snapshot


def build_account_status_response(
    state_store,
    live_status_path: str,
    wallet: str,
) -> Dict[str, Any]:
    snapshot = load_status_snapshot(state_store, live_status_path)
    account_snapshot = get_hyperliquid_account_snapshot(wallet)

    return build_status_payload(
        live_status=snapshot["live_status"],
        state=snapshot["state"],
        metrics=snapshot["metrics"],
        account_snapshot=account_snapshot,
        circuit_breakers=snapshot["circuit_breakers"],
        rate_limiters=snapshot["rate_limiters"],
    )