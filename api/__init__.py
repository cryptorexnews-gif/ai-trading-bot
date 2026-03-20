"""
API Server package for Hyperliquid Trading Bot Dashboard.
Assembles Flask app from modular route blueprints.
"""

from flask import Flask
from flask_cors import CORS

from api.config import CORS_ORIGINS
from api.json_provider import CustomJSONProvider
from api.routes.health import health_bp
from api.routes.bot import bot_bp
from api.routes.trading import trading_bp
from api.routes.market import market_bp
from api.routes.logs import logs_bp
from api.routes.metrics import metrics_bp
from api.routes.openrouter import openrouter_bp
from api.routes.hyperliquid import hyperliquid_bp


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # CORS
    CORS(app, origins=[o.strip() for o in CORS_ORIGINS if o.strip()])

    # Custom JSON provider for Decimal serialization
    app.json_provider_class = CustomJSONProvider
    app.json = CustomJSONProvider(app)

    # Register blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(bot_bp)
    app.register_blueprint(trading_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(openrouter_bp)
    app.register_blueprint(hyperliquid_bp)

    return app