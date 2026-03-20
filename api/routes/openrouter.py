"""
OpenRouter proxy endpoint — forwards LLM requests from frontend to OpenRouter API.
Prevents API key exposure in client-side code.
"""

import json
import logging
import time

from flask import Blueprint, jsonify, request

from api.auth import require_api_key
from api.config import API_AUTH_KEY
from utils.circuit_breaker import get_or_create_circuit_breaker
from utils.rate_limiter import get_rate_limiter

openrouter_bp = Blueprint("openrouter", __name__)

# Get OpenRouter API key from environment
import os
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

# Circuit breaker for OpenRouter API
openrouter_cb = get_or_create_circuit_breaker(
    "openrouter_api", failure_threshold=3, recovery_timeout=60.0
)

# Rate limiter for OpenRouter API
openrouter_rate_limiter = get_rate_limiter(
    "openrouter_api_proxy", max_tokens=5, tokens_per_second=0.5
)

logger = logging.getLogger(__name__)


@openrouter_bp.route("/api/openrouter/chat", methods=["POST"])
@require_api_key
def openrouter_chat():
    """
    Proxy for OpenRouter chat completions API.
    Accepts same payload as OpenRouter API, forwards with API key.
    """
    if not OPENROUTER_API_KEY:
        return jsonify({
            "error": "openrouter_not_configured",
            "message": "OpenRouter API key not configured"
        }), 503

    # Rate limiting
    if not openrouter_rate_limiter.acquire(1, timeout=10.0):
        return jsonify({
            "error": "rate_limit_exceeded",
            "message": "OpenRouter rate limit exceeded"
        }), 429

    # Get request data
    data = request.get_json()
    if not data:
        return jsonify({"error": "invalid_request", "message": "No JSON data provided"}), 400

    # Validate required fields
    if "model" not in data or "messages" not in data:
        return jsonify({
            "error": "invalid_request",
            "message": "Missing required fields: model, messages"
        }), 400

    # Add safety limits
    safe_data = {
        "model": data.get("model", "anthropic/claude-opus-4"),
        "messages": data.get("messages", []),
        "max_tokens": min(data.get("max_tokens", 8192), 16384),
        "temperature": min(max(data.get("temperature", 0.15), 0.0), 1.0),
        "top_p": min(max(data.get("top_p", 1.0), 0.0), 1.0),
        "stream": False  # Force non-streaming for simplicity
    }

    # Remove any potentially sensitive fields
    if "user" in safe_data:
        del safe_data["user"]

    def _call_openrouter():
        import requests
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://hyperliquid-bot.local",
            "X-Title": "Hyperliquid Trading Bot"
        }
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=safe_data,
            headers=headers,
            timeout=90
        )
        
        if response.status_code != 200:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        return response.json()

    try:
        # Use circuit breaker
        result = openrouter_cb.call(_call_openrouter)
        
        # Sanitize response - remove any internal OpenRouter metadata
        if "choices" in result and len(result["choices"]) > 0:
            choice = result["choices"][0]
            if "message" in choice:
                # Ensure we only return the content
                sanitized_choice = {
                    "index": choice.get("index", 0),
                    "message": {
                        "role": choice["message"].get("role", "assistant"),
                        "content": choice["message"].get("content", "")
                    },
                    "finish_reason": choice.get("finish_reason", "stop")
                }
                result["choices"] = [sanitized_choice]
        
        # Remove usage data if present (could reveal costs)
        if "usage" in result:
            del result["usage"]
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"OpenRouter proxy error: {str(e)}")
        return jsonify({
            "error": "openrouter_error",
            "message": f"OpenRouter API error: {str(e)}"
        }), 500


@openrouter_bp.route("/api/openrouter/models", methods=["GET"])
@require_api_key
def openrouter_models():
    """
    Get available models from OpenRouter.
    """
    if not OPENROUTER_API_KEY:
        return jsonify({
            "error": "openrouter_not_configured",
            "message": "OpenRouter API key not configured"
        }), 503

    def _get_models():
        import requests
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        }
        
        response = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"OpenRouter models error: {response.status_code}")
            response.raise_for_status()
        
        return response.json()

    try:
        result = openrouter_cb.call(_get_models)
        
        # Filter to only return model IDs and basic info
        filtered_models = []
        if "data" in result:
            for model in result["data"]:
                filtered_models.append({
                    "id": model.get("id"),
                    "name": model.get("name"),
                    "description": model.get("description", ""),
                    "context_length": model.get("context_length"),
                    "pricing": {
                        "prompt": model.get("pricing", {}).get("prompt"),
                        "completion": model.get("pricing", {}).get("completion")
                    } if model.get("pricing") else None
                })
        
        return jsonify({"models": filtered_models})
        
    except Exception as e:
        logger.error(f"OpenRouter models error: {str(e)}")
        # Return a default list if API fails
        return jsonify({
            "models": [
                {
                    "id": "anthropic/claude-opus-4",
                    "name": "Claude Opus 4",
                    "description": "Anthropic's most powerful model",
                    "context_length": 200000
                },
                {
                    "id": "anthropic/claude-sonnet-3.5",
                    "name": "Claude Sonnet 3.5",
                    "description": "Anthropic's balanced model",
                    "context_length": 200000
                },
                {
                    "id": "openai/gpt-4o",
                    "name": "GPT-4o",
                    "description": "OpenAI's latest model",
                    "context_length": 128000
                }
            ]
        })