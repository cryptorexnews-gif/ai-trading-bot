import time

from flask import Blueprint, jsonify

from api.auth import require_api_key
from api.bot_process_manager import bot_process_manager
from api.rate_limit_utils import build_rate_limiter, rate_limited_response

bot_control_bp = Blueprint("bot_control", __name__)
_bot_control_rl = build_rate_limiter("api_bot_control_endpoints", max_tokens=60, tokens_per_second=2.0)


@bot_control_bp.route("/api/bot-control/status", methods=["GET"])
@require_api_key
def bot_control_status():
    rate_limit_resp = rate_limited_response(_bot_control_rl)
    if rate_limit_resp:
        return rate_limit_resp
    return jsonify({"controller": bot_process_manager.status(), "timestamp": time.time()})


@bot_control_bp.route("/api/bot-control/start", methods=["POST"])
@require_api_key
def bot_control_start():
    rate_limit_resp = rate_limited_response(_bot_control_rl)
    if rate_limit_resp:
        return rate_limit_resp

    result = bot_process_manager.start()
    if result.get("ok"):
        return jsonify({"ok": True, "controller": bot_process_manager.status(), "message": "bot_started"})
    if result.get("reason") == "already_running":
        return jsonify({"ok": False, "error": "already_running"}), 409
    return jsonify({"ok": False, "error": "start_failed"}), 500


@bot_control_bp.route("/api/bot-control/stop", methods=["POST"])
@require_api_key
def bot_control_stop():
    rate_limit_resp = rate_limited_response(_bot_control_rl)
    if rate_limit_resp:
        return rate_limit_resp

    result = bot_process_manager.stop()
    if result.get("ok"):
        return jsonify({"ok": True, "controller": bot_process_manager.status(), "message": "bot_stopped"})
    if result.get("reason") == "not_running":
        return jsonify({"ok": False, "error": "not_running"}), 409
    return jsonify({"ok": False, "error": "stop_failed"}), 500