from decimal import Decimal
from typing import Any, Dict, Optional

from utils.decimals import (
    calculate_margin,
    calculate_position_value,
    clamp,
    is_valid_price,
    is_valid_size,
    normalize_decimal,
    percentage_of,
    quantize_price,
    to_decimal
)


class ValidationError(Exception):
    """Custom exception for validation failures."""
    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.value = value
        super().__init__(f"Validation error for '{field}': {message}")


def validate_market_data(data: Dict[str, Any]) -> bool:
    """
    Validate market data structure and values.
    Returns True if valid, raises ValidationError if invalid.
    """
    required_fields = ["coin", "last_price", "change_24h", "volume_24h", "timestamp"]
    
    for field in required_fields:
        if field not in data:
            raise ValidationError(field, "missing required field")
    
    # Validate coin
    coin = str(data.get("coin", "")).strip().upper()
    if not coin or len(coin) < 2:
        raise ValidationError("coin", "invalid coin symbol", coin)
    
    # Validate price
    price = to_decimal(data.get("last_price"))
    if not is_valid_price(price):
        raise ValidationError("last_price", "price must be positive", price)
    
    # Validate timestamp
    ts = data.get("timestamp")
    if not isinstance(ts, (int, float)) or ts <= 0:
        raise ValidationError("timestamp", "invalid timestamp", ts)
    
    # Check for stale data (age should be reasonable, e.g., < 5 minutes)
    import time
    age = time.time() - float(ts)
    if age > 300:  # 5 minutes
        raise ValidationError("timestamp", f"data is stale (age={age:.1f}s)", ts)
    
    return True


def validate_order_request(order: Dict[str, Any], coin: str, min_size: Decimal) -> bool:
    """
    Validate an order request before execution.
    Returns True if valid, raises ValidationError if invalid.
    """
    required_fields = ["action", "size", "leverage"]
    
    for field in required_fields:
        if field not in order:
            raise ValidationError(field, "missing required field")
    
    # Validate action
    action = str(order.get("action", "")).strip().lower()
    allowed_actions = [
        "buy", "sell", "hold", "close_position", 
        "increase_position", "reduce_position", "change_leverage"
    ]
    if action not in allowed_actions:
        raise ValidationError("action", f"invalid action '{action}'. Must be one of: {', '.join(allowed_actions)}", action)
    
    # Skip further validation for HOLD
    if action == "hold":
        return True
    
    # Validate size (for non-hold actions)
    size = to_decimal(order.get("size"))
    if not is_valid_size(size):
        raise ValidationError("size", "size must be non-negative", size)
    
    # Validate minimum size for open actions
    open_actions = ["buy", "sell", "increase_position"]
    if action in open_actions and size < min_size:
        raise ValidationError("size", f"size {size} below minimum {min_size} for {coin}", size)
    
    # Validate leverage
    leverage = to_decimal(order.get("leverage"))
    if leverage < 1:
        raise ValidationError("leverage", "leverage must be >= 1", leverage)
    if leverage > 100:  # Reasonable upper bound
        raise ValidationError("leverage", "leverage unreasonably high (>100)", leverage)
    
    # Validate confidence if present
    if "confidence" in order:
        confidence = to_decimal(order.get("confidence"))
        if not (0 <= confidence <= 1):
            raise ValidationError("confidence", "confidence must be between 0 and 1", confidence)
    
    return True


def validate_portfolio_state(state: Dict[str, Any]) -> bool:
    """
    Validate portfolio state structure and values.
    """
    required_fields = ["total_balance", "available_balance", "margin_usage", "positions"]
    
    for field in required_fields:
        if field not in state:
            raise ValidationError(field, "missing required field")
    
    # Validate balances
    total_balance = to_decimal(state.get("total_balance"))
    available_balance = to_decimal(state.get("available_balance"))
    margin_usage = to_decimal(state.get("margin_usage"))
    
    if total_balance < 0:
        raise ValidationError("total_balance", "cannot be negative", total_balance)
    if available_balance < 0:
        raise ValidationError("available_balance", "cannot be negative", available_balance)
    if not (0 <= margin_usage <= 1):
        raise ValidationError("margin_usage", "must be between 0 and 1", margin_usage)
    
    # Validate positions structure
    positions = state.get("positions", {})
    if not isinstance(positions, dict):
        raise ValidationError("positions", "must be a dictionary", positions)
    
    for coin, pos in positions.items():
        if not isinstance(pos, dict):
            raise ValidationError(f"positions.{coin}", "must be a dictionary", pos)
        
        # Check required position fields
        pos_required = ["size", "entry_price", "margin_used"]
        for field in pos_required:
            if field not in pos:
                raise ValidationError(f"positions.{coin}.{field}", "missing required field")
        
        # Validate position values
        size = to_decimal(pos.get("size"))
        entry_price = to_decimal(pos.get("entry_price"))
        margin_used = to_decimal(pos.get("margin_used"))
        
        if size == 0:
            raise ValidationError(f"positions.{coin}.size", "cannot be zero for open position", size)
        if entry_price <= 0:
            raise ValidationError(f"positions.{coin}.entry_price", "must be positive", entry_price)
        if margin_used < 0:
            raise ValidationError(f"positions.{coin}.margin_used", "cannot be negative", margin_used)
    
    return True


def validate_configuration(config: Dict[str, Any]) -> bool:
    """
    Validate bot configuration at startup.
    """
    # Required environment variables
    required_env_vars = [
        "HYPERLIQUID_WALLET_ADDRESS",
        "HYPERLIQUID_PRIVATE_KEY"
    ]
    
    import os
    missing = [var for var in required_env_vars if not os.getenv(var)]
    if missing:
        raise ValidationError("environment", f"missing required variables: {', '.join(missing)}")
    
    # Validate numeric configurations
    numeric_configs = {
        "MAX_ORDER_MARGIN_PCT": (Decimal("0"), Decimal("1")),
        "HARD_MAX_LEVERAGE": (Decimal("1"), Decimal("100")),
        "MIN_CONFIDENCE_OPEN": (Decimal("0"), Decimal("1")),
        "MIN_CONFIDENCE_MANAGE": (Decimal("0"), Decimal("1")),
        "MAX_DRAWDOWN_PCT": (Decimal("0"), Decimal("1")),
        "PAPER_SLIPPAGE_BPS": (Decimal("0"), Decimal("10000")),
        "TRADE_COOLDOWN_SEC": (Decimal("0"), Decimal("86400")),  # 0 to 24 hours
        "DAILY_NOTIONAL_LIMIT_USD": (Decimal("0"), None),  # No upper bound
        "MAX_TRADES_PER_CYCLE": (Decimal("1"), Decimal("50")),
        "MAX_CONSECUTIVE_FAILED_CYCLES": (Decimal("1"), Decimal("100")),
        "META_CACHE_TTL_SEC": (Decimal("1"), Decimal("3600")),
        "MAX_MARKET_DATA_AGE_SEC": (Decimal("1"), Decimal("600"))
    }
    
    for key, (min_val, max_val) in numeric_configs.items():
        value = config.get(key)
        if value is not None:
            dec_value = to_decimal(value)
            if dec_value < min_val:
                raise ValidationError(key, f"must be >= {min_val}", dec_value)
            if max_val is not None and dec_value > max_val:
                raise ValidationError(key, f"must be <= {max_val}", dec_value)
    
    # Validate string enumerations
    enum_configs = {
        "EXECUTION_MODE": ["paper", "live"],
        "SAFE_FALLBACK_MODE": ["de_risk", "hold"],
        "ALLOW_EXTERNAL_LLM": ["true", "false"],
        "LLM_INCLUDE_PORTFOLIO_CONTEXT": ["true", "false"],
        "ENABLE_MAINNET_TRADING": ["true", "false"]
    }
    
    for key, allowed_values in enum_configs.items():
        value = str(config.get(key, "")).lower()
        if value and value not in allowed_values:
            raise ValidationError(key, f"must be one of: {', '.join(allowed_values)}", value)
    
    return True


def validate_asset_id(coin: str, asset_id: Optional[int]) -> bool:
    """
    Validate that an asset ID is valid for a given coin.
    """
    if asset_id is None:
        raise ValidationError("asset_id", "asset ID is None")
    if not isinstance(asset_id, int) or asset_id < 0:
        raise ValidationError("asset_id", "must be a non-negative integer", asset_id)
    return True