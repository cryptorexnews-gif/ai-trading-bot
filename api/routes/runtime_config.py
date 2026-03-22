import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import COIN_PATTERN, KNOWN_TRADING_PAIRS, RUNTIME_CONFIG_PATH
from api.rate_limit_utils import build_rate_limiter, rate_limited_response
from api.services.account_snapshot_service import fetch_hyperliquid_universe
from api.services.available_pairs_service import AvailablePairsService
from api.services.runtime_config_service import (
    default_strategy_params,
    normalize_strategy_params,
    strategy_presets,
)
from runtime_config_store import RuntimeConfigStore

runtime_config_bp = Blueprint("runtime_config", __name__)

_runtime_store = RuntimeConfigStore(
    RUNTIME_CONFIG_PATH,
    [p for p in KNOWN_TRADING_PAIRS],
)
_runtime_rl = build_rate_limiter("api_runtime_config_endpoints", max_tokens=100, tokens_per_second=3.0)

_available_pairs_service = AvailablePairsService(
    fetch_universe_fn=fetch_hyperliquid_universe,
    coin_pattern=COIN_PATTERN,
    fallback_pairs=KNOWN_TRADING_PAIRS,
    cache_ttl_sec=300.0,
)


@runtime_config_bp.route("/api/runtime-config", methods=["GET"])
@require_api_key
def runtime_config():
    rate_limit_resp = rate_limited_response(_runtime_rl)
    if rate_limit_resp:
        return rate_limit_resp

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
def update_runtime_config():
    rate_limit_resp = rate_limited_response(_runtime_rl)
    if rate_limit_resp:
        return rate_limit_resp

    payload = request.get_json(silent=True) or {}
    strategy_mode = str(payload.get("strategy_mode", "trend")).strip().lower()
    if strategy_mode not in {"trend", "scalping"}:
        return jsonify({"error": "invalid_strategy_mode"}), 400

    raw_pairs = payload.get("trading_pairs", [])
    if not isinstance(raw_pairs, list):
        return jsonify({"error": "invalid_trading_pairs"}), 400

    live_allowed = _available_pairs_service.get_live_allowed_pairs_set()

    normalized_pairs = []
    for coin in raw_pairs:
        c = str(coin).strip().upper()
        if not c:
            continue
        if not COIN_PATTERN.match(c):
            return jsonify({"error": f"invalid_coin_{c}"}), 400

        if live_allowed and c not in live_allowed:
            return jsonify({"error": f"coin_not_available_on_hyperliquid_{c}"}), 400

        if c not in normalized_pairs:
            normalized_pairs.append(c)

    if len(normalized_pairs) == 0:
        return jsonify({"error": "at_least_one_coin_required"}), 400
    if len(normalized_pairs) > 20:
        return jsonify({"error": "too_many_coins_max_20"}), 400

    preset_params = default_strategy_params(strategy_mode)
    provided_params = payload.get("strategy_params", None)

    if provided_params is None:
        merged_params = dict(preset_params)
    elif isinstance(provided_params, dict):
        merged_params = {**preset_params, **provided_params}
    else:
        return jsonify({"error": "invalid_strategy_params"}), 400

    normalized_params, params_error = normalize_strategy_params(merged_params)
    if params_error:
        return jsonify({"error": params_error}), 400

    saved = _runtime_store.save({
        "strategy_mode": strategy_mode,
        "trading_pairs": normalized_pairs,
        "strategy_params": normalized_params,
    })

    return jsonify({
        "ok": True,
        "runtime_config": saved,
        "message": "runtime_config_updated"
    })