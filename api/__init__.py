"""
API Server package for Hyperliquid Trading Bot Dashboard.
Assembles Flask app from modular route blueprints.
"""

from flask import Flask, jsonify
from flask_cors import CORS

from api.config import CORS_ORIGINS, SECURITY_HEADERS
from api.json_provider import CustomJSONProvider
from api.routes.health import health_bp
from api.routes.bot import bot_bp
from api.routes.trading import trading_bp
from api.routes.market import market_bp
from api.routes.logs import logs_bp
from api.routes.metrics import metrics_bp


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # CORS
    CORS(app, origins=[o.strip() for o in CORS_ORIGINS if o.strip()])

    # Custom JSON provider for Decimal serialization
    app.json_provider_class = CustomJSONProvider
    app.json = CustomJSONProvider(app)

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
    app.register_blueprint(bot_bp)
    app.register_blueprint(trading_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(metrics_bp)

    return app