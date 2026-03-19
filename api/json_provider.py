"""
Custom JSON provider for Flask — handles Decimal types.
"""

from decimal import Decimal

from flask.json.provider import DefaultJSONProvider


class CustomJSONProvider(DefaultJSONProvider):
    """JSON provider that converts Decimal to float for serialization."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)