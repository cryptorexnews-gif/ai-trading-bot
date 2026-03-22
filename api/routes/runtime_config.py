import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import COIN_PATTERN, KNOWN_TRADING_PAIRS, RUNTIME_CONFIG_PATH
from api.rate_limit import rate_limited
from api.services.account_snapshot_service import fetch_hyperliquid_universe
from api.services.available_pairs_service import AvailablePairsService
from api.services.runtime_config_service import (
    default_strategy_params,
    strategy_presets,
    validate_runtime_update_payload,
)
from runtime_config_store import RuntimeConfigStore

runtime_config_bp = Blueprint("runtime_config", __name__)

_runtime_store = RuntimeConfigStore(
    RUNTIME_CONFIG_PATH,
    [p for p in KNOWN_TRADING_PAIRS],
)

_available_pairs_service = AvailablePairsService(
    fetch_universe_fn=fetch_hyperliquid_universe,
    coin_pattern=COIN_PATTERN,
    fallback_pairs=KNOWN_TRADING_PAIRS,
    cache_ttl_sec=300.0,
)


@runtime_config_bp.route("/api/runtime-config", methods=["GET"])
@require_api_key
@rate_limited("api_runtime_config_endpoints", max_tokens=100, tokens_per_second=3.0)
def runtime_config():
    runtime = _runtime_store.load()
    mode = str(runtime.get("strategy_mode", "trend")).strip().lower()
    presets = strategy_presets()

    return jsonify({
        "runtime_config": runtime,
        "default_strategy_params": default_strategy_params(mode),
        "strategy_presets": presets,
        "available_pairs": _available_pairs_service.get_available_pairs(),
        "timestamp": time.time()
    })


@runtime_config_bp.route("/api/runtime-config", methods=["POST"])
@require_api_key
@rate_limited("api_runtime_config_endpoints", max_tokens=100, tokens_per_second=3.0)
def update_runtime_config():
    payload = request.get_json(silent=True) or {}
    validated, error = validate_runtime_update_payload(
        payload=payload,
        coin_pattern=COIN_PATTERN,
        live_allowed_pairs=_available_pairs_service.get_live_allowed_pairs_set(),
    )
    if error:
        return jsonify({"error": error}), 400

    saved = _runtime_store.save(validated)

    return jsonify({
        "ok": True,
        "runtime_config": saved,
        "message": "runtime_config_updated"
    })