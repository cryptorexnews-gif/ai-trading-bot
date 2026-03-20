from decimal import Decimal
from typing import Any, Dict, Optional

from utils.decimals import is_valid_price, is_valid_size, to_decimal


class ValidationError(Exception):
    """Eccezione personalizzata per fallimenti di validazione."""
    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.value = value
        super().__init__(f"Errore di validazione per '{field}': {message}")


def validate_market_data(data: Dict[str, Any]) -> bool:
    """
    Valida la struttura e i valori dei dati di mercato.
    Restituisce True se valido, solleva ValidationError se invalido.
    """
    required_fields = ["coin", "last_price", "change_24h", "volume_24h", "timestamp"]

    for field in required_fields:
        if field not in data:
            raise ValidationError(field, "campo richiesto mancante")

    # Valida coin
    coin = str(data.get("coin", "")).strip().upper()
    if not coin or len(coin) < 2:
        raise ValidationError("coin", "simbolo coin invalido", coin)

    # Valida prezzo
    price = to_decimal(data.get("last_price"))
    if not is_valid_price(price):
        raise ValidationError("last_price", "il prezzo deve essere positivo", price)

    # Valida timestamp
    ts = data.get("timestamp")
    if not isinstance(ts, (int, float)) or ts <= 0:
        raise ValidationError("timestamp", "timestamp invalido", ts)

    # Controlla dati obsoleti (età dovrebbe essere ragionevole, es. < 5 minuti)
    import time
    age = time.time() - float(ts)
    if age > 300:  # 5 minuti
        raise ValidationError("timestamp", f"dati obsoleti (età={age:.1f}s)", ts)

    return True


def validate_order_request(order: Dict[str, Any], coin: str, min_size: Decimal) -> bool:
    """
    Valida una richiesta di ordine prima dell'esecuzione.
    Restituisce True se valido, solleva ValidationError se invalido.
    """
    required_fields = ["action", "size", "leverage"]

    for field in required_fields:
        if field not in order:
            raise ValidationError(field, "campo richiesto mancante")

    # Valida action
    action = str(order.get("action", "")).strip().lower()
    allowed_actions = [
        "buy", "sell", "hold", "close_position",
        "increase_position", "reduce_position", "change_leverage"
    ]
    if action not in allowed_actions:
        raise ValidationError("action", f"azione invalida '{action}'. Deve essere una di: {', '.join(allowed_actions)}", action)

    # Salta ulteriore validazione per HOLD
    if action == "hold":
        return True

    # Valida size (per azioni non-hold)
    size = to_decimal(order.get("size"))
    if not is_valid_size(size):
        raise ValidationError("size", "la dimensione deve essere non negativa", size)

    # Valida dimensione minima per azioni di apertura
    open_actions = ["buy", "sell", "increase_position"]
    if action in open_actions and size < min_size:
        raise ValidationError("size", f"dimensione {size} sotto il minimo {min_size} per {coin}", size)

    # Valida leverage
    leverage = to_decimal(order.get("leverage"))
    if leverage < 1:
        raise ValidationError("leverage", "leverage deve essere >= 1", leverage)
    if leverage > 100:  # Limite superiore ragionevole
        raise ValidationError("leverage", "leverage irragionevolmente alto (>100)", leverage)

    # Valida confidence se presente
    if "confidence" in order:
        confidence = to_decimal(order.get("confidence"))
        if not (0 <= confidence <= 1):
            raise ValidationError("confidence", "confidence deve essere tra 0 e 1", confidence)

    return True


def validate_portfolio_state(state: Dict[str, Any]) -> bool:
    """
    Valida la struttura e i valori dello stato del portfolio.
    """
    required_fields = ["total_balance", "available_balance", "margin_usage", "positions"]

    for field in required_fields:
        if field not in state:
            raise ValidationError(field, "campo richiesto mancante")

    # Valida bilanci
    total_balance = to_decimal(state.get("total_balance"))
    available_balance = to_decimal(state.get("available_balance"))
    margin_usage = to_decimal(state.get("margin_usage"))

    if total_balance < 0:
        raise ValidationError("total_balance", "non può essere negativo", total_balance)
    if available_balance < 0:
        raise ValidationError("available_balance", "non può essere negativo", available_balance)
    if not (0 <= margin_usage <= 1):
        raise ValidationError("margin_usage", "deve essere tra 0 e 1", margin_usage)

    # Valida struttura posizioni
    positions = state.get("positions", {})
    if not isinstance(positions, dict):
        raise ValidationError("positions", "deve essere un dizionario", positions)

    for coin, pos in positions.items():
        if not isinstance(pos, dict):
            raise ValidationError(f"positions.{coin}", "deve essere un dizionario", pos)

        # Controlla campi richiesti per posizione
        pos_required = ["size", "entry_price", "margin_used"]
        for field in pos_required:
            if field not in pos:
                raise ValidationError(f"positions.{coin}.{field}", "campo richiesto mancante")

        # Valida valori posizione
        size = to_decimal(pos.get("size"))
        entry_price = to_decimal(pos.get("entry_price"))
        margin_used = to_decimal(pos.get("margin_used"))

        if size == 0:
            raise ValidationError(f"positions.{coin}.size", "non può essere zero per posizione aperta", size)
        if entry_price <= 0:
            raise ValidationError(f"positions.{coin}.entry_price", "deve essere positivo", entry_price)
        if margin_used < 0:
            raise ValidationError(f"positions.{coin}.margin_used", "non può essere negativo", margin_used)

    return True


def validate_configuration(config: Dict[str, Any]) -> bool:
    """
    Valida la configurazione del bot all'avvio.
    """
    # Variabili d'ambiente richieste
    required_env_vars = [
        "HYPERLIQUID_WALLET_ADDRESS",
        "HYPERLIQUID_PRIVATE_KEY"
    ]

    import os
    missing = [var for var in required_env_vars if not os.getenv(var)]
    if missing:
        raise ValidationError("environment", f"variabili richieste mancanti: {', '.join(missing)}")

    # Valida configurazioni numeriche
    numeric_configs = {
        "MAX_ORDER_MARGIN_PCT": (Decimal("0"), Decimal("1")),
        "HARD_MAX_LEVERAGE": (Decimal("1"), Decimal("100")),
        "MIN_CONFIDENCE_OPEN": (Decimal("0"), Decimal("1")),
        "MIN_CONFIDENCE_MANAGE": (Decimal("0"), Decimal("1")),
        "MAX_DRAWDOWN_PCT": (Decimal("0"), Decimal("1")),
        "PAPER_SLIPPAGE_BPS": (Decimal("0"), Decimal("10000")),
        "TRADE_COOLDOWN_SEC": (Decimal("0"), Decimal("86400")),  # 0 a 24 ore
        "DAILY_NOTIONAL_LIMIT_USD": (Decimal("0"), None),  # Nessun limite superiore
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
                raise ValidationError(key, f"deve essere >= {min_val}", dec_value)
            if max_val is not None and dec_value > max_val:
                raise ValidationError(key, f"deve essere <= {max_val}", dec_value)

    # Valida enumerazioni stringa
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
            raise ValidationError(key, f"deve essere una di: {', '.join(allowed_values)}", value)

    return True


def validate_asset_id(coin: str, asset_id: Optional[int]) -> bool:
    """
    Valida che un ID asset sia valido per una coin data.
    """
    if asset_id is None:
        raise ValidationError("asset_id", "ID asset è None")
    if not isinstance(asset_id, int) or asset_id < 0:
        raise ValidationError("asset_id", "deve essere un intero non negativo", asset_id)
    return True