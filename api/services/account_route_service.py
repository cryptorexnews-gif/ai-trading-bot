import os
import time
from decimal import Decimal
from typing import Any, Dict

from api.helpers import read_json_file
from api.services.account_snapshot_service import get_hyperliquid_account_snapshot
from api.services.managed_positions_service import build_managed_positions_payload


def build_portfolio_response(wallet: str) -> Dict[str, Any]:
    account_snapshot = get_hyperliquid_account_snapshot(wallet)
    return {
        "portfolio": account_snapshot.get("portfolio", {}),
        "source": "hyperliquid_account",
        "timestamp": time.time(),
    }


def build_positions_response(wallet: str) -> Dict[str, Any]:
    account_snapshot = get_hyperliquid_account_snapshot(wallet)
    return {
        "positions": account_snapshot.get("portfolio", {}).get("positions", {}),
        "source": "hyperliquid_account",
        "timestamp": time.time(),
    }


def build_managed_positions_response(wallet: str, managed_positions_path: str) -> Dict[str, Any]:
    account_snapshot = get_hyperliquid_account_snapshot(wallet)
    exchange_positions = account_snapshot.get("portfolio", {}).get("positions", {}) or {}
    managed_data = read_json_file(managed_positions_path) or {}

    default_sl_pct = Decimal(str(os.getenv("TREND_SL_PCT", "0.04")))
    default_tp_pct = Decimal(str(os.getenv("TREND_TP_PCT", "0.08")))
    default_be_activation_pct = Decimal(str(os.getenv("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02")))
    default_trailing_callback = Decimal(str(os.getenv("TREND_TRAILING_CALLBACK", "0.02")))

    positions_list = build_managed_positions_payload(
        exchange_positions=exchange_positions,
        managed_data=managed_data,
        default_sl_pct=default_sl_pct,
        default_tp_pct=default_tp_pct,
        default_be_activation_pct=default_be_activation_pct,
        default_trailing_callback=default_trailing_callback,
    )

    return {
        "managed_positions": positions_list,
        "source": "hyperliquid_account_with_managed_overlays",
        "timestamp": time.time(),
    }