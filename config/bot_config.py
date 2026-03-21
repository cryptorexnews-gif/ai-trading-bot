from decimal import Decimal
from typing import Dict, List
import os


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, "").lower()
    if val in ("true", "1", "yes", "on"):
        return True
    if val in ("false", "0", "no", "off"):
        return False
    return default


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _env_decimal(key: str, default: str = "0") -> Decimal:
    try:
        return Decimal(str(os.getenv(key, default)))
    except Exception:
        return Decimal(default)


class BotConfig:
    """Configuration for the Hyperliquid Trading Bot."""

    def __init__(self):
        self.wallet_address = _env("HYPERLIQUID_WALLET_ADDRESS", "")
        self.execution_mode = _env("EXECUTION_MODE", "paper").lower()
        self.enable_mainnet_trading = _env_bool("ENABLE_MAINNET_TRADING", False)
        self.base_url = _env("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz")

        self.openrouter_api_key = _env("OPENROUTER_API_KEY", "")
        self.llm_model = _env("LLM_MODEL", "anthropic/claude-opus-4.6")
        self.llm_max_tokens = _env_int("LLM_MAX_TOKENS", 8192)
        self.llm_temperature = _env_decimal("LLM_TEMPERATURE", "0.2")

        self.hard_max_leverage = _env_decimal("HARD_MAX_LEVERAGE", "10")
        self.min_confidence_open = _env_decimal("MIN_CONFIDENCE_OPEN", "0.72")
        self.min_confidence_manage = _env_decimal("MIN_CONFIDENCE_MANAGE", "0.50")
        self.max_margin_usage = _env_decimal("MAX_MARGIN_USAGE", "0.8")
        self.max_order_margin_pct = _env_decimal("MAX_ORDER_MARGIN_PCT", "0.1")
        self.max_order_notional_usd = _env_decimal("MAX_ORDER_NOTIONAL_USD", "0")
        self.trade_cooldown_sec = _env_int("TRADE_COOLDOWN_SEC", 300)
        self.daily_notional_limit_usd = _env_decimal("DAILY_NOTIONAL_LIMIT_USD", "1000")
        self.volatility_multiplier = _env_decimal("VOLATILITY_MULTIPLIER", "1.2")
        self.max_drawdown_pct = _env_decimal("MAX_DRAWDOWN_PCT", "0.15")
        self.max_single_asset_pct = _env_decimal("MAX_SINGLE_ASSET_PCT", "0.35")
        self.emergency_margin_threshold = _env_decimal("EMERGENCY_MARGIN_THRESHOLD", "0.88")
        self.max_consecutive_failed_cycles = _env_int("MAX_CONSECUTIVE_FAILED_CYCLES", 5)

        trading_pairs_raw = _env(
            "TRADING_PAIRS",
            "BTC,ETH,SOL,BNB,ADA,DOGE,XRP,AVAX,LINK,SUI,ARB,OP,NEAR,WIF,PEPE,INJ,TIA,SEI,RENDER,FET"
        )
        self.trading_pairs = [p.strip().upper() for p in trading_pairs_raw.split(",") if p.strip()]

        min_sizes = {}
        for coin in self.trading_pairs:
            env_key = f"MIN_SIZE_{coin}"
            default_size = "0.001" if coin in ["BTC", "ETH"] else "0.01" if coin in ["SOL", "BNB", "ADA"] else "0.1"
            min_sizes[coin] = _env_decimal(env_key, default_size)
        self.min_size_by_coin = min_sizes
        self.default_min_size = _env_decimal("DEFAULT_MIN_SIZE", "0.001")

        self.default_cycle_sec = _env_int("DEFAULT_CYCLE_SEC", 1800)
        self.min_cycle_sec = _env_int("MIN_CYCLE_SEC", 900)
        self.max_cycle_sec = _env_int("MAX_CYCLE_SEC", 3600)
        self.enable_adaptive_cycle = _env_bool("ENABLE_ADAPTIVE_CYCLE", True)
        self.max_trades_per_cycle = _env_int("MAX_TRADES_PER_CYCLE", 2)

        self.info_timeout = _env_int("HYPERLIQUID_INFO_TIMEOUT", 15)
        self.exchange_timeout = _env_int("HYPERLIQUID_EXCHANGE_TIMEOUT", 30)
        self.paper_slippage_bps = _env_decimal("PAPER_SLIPPAGE_BPS", "5")

        self.log_level = _env("LOG_LEVEL", "INFO")
        self.log_file = _env("LOG_FILE", "logs/hyperliquid_bot.log")

        self.meta_cache_ttl_sec = _env_int("META_CACHE_TTL_SEC", 86400)

        self.state_path = _env("STATE_PATH", "state/bot_state.json")
        self.metrics_path = _env("METRICS_PATH", "state/bot_metrics.json")

        self.primary_timeframe = _env("PRIMARY_TIMEFRAME", "4h")
        self.secondary_timeframe = _env("SECONDARY_TIMEFRAME", "1d")
        self.entry_timeframe = _env("ENTRY_TIMEFRAME", "1h")
        self.min_trend_duration_hours = _env_int("MIN_TREND_DURATION_HOURS", 36)
        self.volume_confirmation_threshold = _env_decimal("VOLUME_CONFIRMATION_THRESHOLD", "1.6")
        self.trend_confirmation_required = _env_bool("TREND_CONFIRMATION_REQUIRED", True)
        self.max_trend_positions = _env_int("MAX_TREND_POSITIONS", 2)
        self.trend_position_size_pct = _env_decimal("TREND_POSITION_SIZE_PCT", "0.02")
        self.trend_leverage_multiplier = _env_decimal("TREND_LEVERAGE_MULTIPLIER", "0.9")
        self.trend_sl_pct = _env_decimal("TREND_SL_PCT", "0.04")
        self.trend_tp_pct = _env_decimal("TREND_TP_PCT", "0.08")
        self.trend_break_even_activation_pct = _env_decimal("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02")
        self.trend_trailing_activation_pct = _env_decimal("TREND_TRAILING_ACTIVATION_PCT", "0.03")
        self.trend_trailing_callback = _env_decimal("TREND_TRAILING_CALLBACK", "0.02")

        self.enable_trailing_stop = _env_bool("ENABLE_TRAILING_STOP", True)
        self.break_even_offset_pct = _env_decimal("BREAK_EVEN_OFFSET_PCT", "0.001")
        self.correlation_threshold = _env_decimal("CORRELATION_THRESHOLD", "0.7")

        self._normalize_runtime_values()

    def _normalize_runtime_values(self) -> None:
        """Apply safe minimums to avoid fragile live configuration."""
        if self.min_trend_duration_hours < 24:
            self.min_trend_duration_hours = 24

        # If cap is set extremely low, disable it to avoid constant false rejections.
        if self.max_order_notional_usd > 0 and self.max_order_notional_usd < Decimal("10"):
            self.max_order_notional_usd = Decimal("0")

    @classmethod
    def from_env(cls) -> "BotConfig":
        return cls()

    def validate(self) -> List[str]:
        warnings = []

        if not self.wallet_address:
            raise SystemExit("CRITICAL: HYPERLIQUID_WALLET_ADDRESS not set")

        private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
        if not private_key:
            raise SystemExit("CRITICAL: HYPERLIQUID_PRIVATE_KEY not set")

        if not self.wallet_address.startswith("0x") or len(self.wallet_address) != 42:
            raise SystemExit(
                f"CRITICAL: HYPERLIQUID_WALLET_ADDRESS has invalid format. "
                f"Expected 0x-prefixed 42-character hex string, got: {self.wallet_address[:10]}..."
            )

        from exchange_client import HyperliquidExchangeClient
        if not HyperliquidExchangeClient.validate_wallet_address(private_key, self.wallet_address):
            from eth_account import Account
            derived = Account.from_key(private_key).address
            raise SystemExit(
                f"CRITICAL: HYPERLIQUID_WALLET_ADDRESS ({self.wallet_address}) does not match "
                f"the address derived from HYPERLIQUID_PRIVATE_KEY ({derived[:6]}...{derived[-4:]}). "
                f"Fix your .env configuration."
            )

        if self.execution_mode == "live" and not self.enable_mainnet_trading:
            warnings.append("EXECUTION_MODE=live but ENABLE_MAINNET_TRADING=false — orders will be paper")
        if self.execution_mode not in ("paper", "live"):
            warnings.append(f"Unknown EXECUTION_MODE '{self.execution_mode}', defaulting to paper behavior")

        if self.min_trend_duration_hours < 24:
            warnings.append(f"MIN_TREND_DURATION_HOURS={self.min_trend_duration_hours} is low for 4H/1D strategy")
        if self.volume_confirmation_threshold < Decimal("1.0"):
            warnings.append(f"VOLUME_CONFIRMATION_THRESHOLD={self.volume_confirmation_threshold} < 1.0 may allow noisy signals")
        if self.trend_position_size_pct > Decimal("0.05"):
            warnings.append(f"TREND_POSITION_SIZE_PCT={self.trend_position_size_pct} is high (>5%) for conservative mode")
        if self.trend_sl_pct < Decimal("0.03"):
            warnings.append(f"TREND_SL_PCT={self.trend_sl_pct} may be too tight for trend trades")
        if self.trend_sl_pct > 0 and (self.trend_tp_pct / self.trend_sl_pct) < Decimal("1.5"):
            warnings.append(f"Trend R:R is low: TP={self.trend_tp_pct}, SL={self.trend_sl_pct}")

        if self.default_cycle_sec < 300:
            warnings.append(f"DEFAULT_CYCLE_SEC={self.default_cycle_sec} is very short (<5 minutes)")
        if self.default_cycle_sec > 3600:
            warnings.append(f"DEFAULT_CYCLE_SEC={self.default_cycle_sec} is very long (>60 minutes)")

        if self.max_order_notional_usd < 0:
            warnings.append("MAX_ORDER_NOTIONAL_USD < 0 is invalid; it should be 0 (disabled) or positive")
        if self.max_order_notional_usd > 0 and self.max_order_notional_usd < Decimal("10"):
            warnings.append("MAX_ORDER_NOTIONAL_USD is very low; trades may be frequently rejected")
        if self.max_trades_per_cycle < 1:
            warnings.append("MAX_TRADES_PER_CYCLE < 1 is invalid; using very restrictive setting")

        return warnings

    @staticmethod
    def mask_wallet(wallet: str) -> str:
        if not wallet or len(wallet) < 12:
            return "invalid"
        return f"{wallet[:6]}...{wallet[-4:]}"