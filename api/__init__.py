"""
API Server package for Hyperliquid Trading Bot Dashboard.
Assembles Flask app from modular route blueprints.
"""

from flask import Flask, jsonify
from flask_cors import CORS

from api.config import CORS_ORIGINS, SECURITY_HEADERS
from api.json_provider import CustomJSONProvider
from api.routes.health import health_bp
from api.routes.account import account_bp
from api.routes.bot_control import bot_control_bp
from api.routes.runtime_config import runtime_config_bp
from api.routes.trading import trading_bp
from api.routes.market import market_bp
from api.routes.logs import logs_bp
from api.routes.metrics import metrics_bp
from api.websocket import sock


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # CORS
    CORS(app, origins=[o.strip() for o in CORS_ORIGINS if o.strip()])

    # Custom JSON provider for Decimal serialization
    app.json_provider_class = CustomJSONProvider
    app.json = CustomJSONProvider(app)

    # WebSocket support
    sock.init_app(app)

    # Security headers
    @app.after_request
    def add_security_headers(response):
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    # Uniform JSON error responses
    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "not_found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return jsonify({"error": "method_not_allowed"}), 405

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({"error": "internal_error"}), 500

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(bot_control_bp)
    app.register_blueprint(runtime_config_bp)
    app.register_blueprint(trading_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(metrics_bp)

    return app