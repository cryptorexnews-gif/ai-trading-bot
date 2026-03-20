"""
BotConfig — single source of truth for all bot configuration.
Reads from environment variables with sensible defaults.
Validates critical settings at construction time.
"""

import os
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    return _env(key, str(default).lower()).lower() == "true"


def _env_int(key: str, default: int = 0) -> int:
    return int(_env(key, str(default)))


def _env_float(key: str, default: float = 0.0) -> float:
    return float(_env(key, str(default)))


def _env_decimal(key: str, default: str = "0") -> Decimal:
    return Decimal(_env(key, default))


@dataclass
class BotConfig:
    """All bot configuration in one place. No env vars read elsewhere."""

    # ─── Credentials & Connection ─────────────────────────────────────────
    wallet_address: str = ""
    base_url: str = "https://api.hyperliquid.xyz"
    info_timeout: int = 15
    exchange_timeout: int = 30

    # ─── Execution Mode ───────────────────────────────────────────────────
    execution_mode: str = "paper"
    enable_mainnet_trading: bool = False

    # ─── LLM ──────────────────────────────────────────────────────────────
    openrouter_api_key: str = ""
    llm_model: str = "anthropic/claude-opus-4"
    llm_max_tokens: int = 8192
    llm_temperature: float = 0.15

    # ─── Trading Pairs ────────────────────────────────────────────────────
    trading_pairs: List[str] = field(default_factory=list)

    # ─── Risk Management ──────────────────────────────────────────────────
    max_order_margin_pct: Decimal = Decimal("0.08")
    hard_max_leverage: Decimal = Decimal("7")
    min_confidence_open: Decimal = Decimal("0.72")
    min_confidence_manage: Decimal = Decimal("0.50")
    max_margin_usage: Decimal = Decimal("0.70")
    max_drawdown_pct: Decimal = Decimal("0.12")
    max_single_asset_pct: Decimal = Decimal("0.35")
    emergency_margin_threshold: Decimal = Decimal("0.85")
    trade_cooldown_sec: int = 300
    daily_notional_limit_usd: Decimal = Decimal("500")
    max_trades_per_cycle: int = 2
    max_consecutive_failed_cycles: int = 5
    paper_slippage_bps: Decimal = Decimal("5")
    volatility_multiplier: Decimal = Decimal("1.2")
    safe_fallback_mode: str = "hold"

    # ─── Position Management ──────────────────────────────────────────────
    default_sl_pct: Decimal = Decimal("0.03")
    default_tp_pct: Decimal = Decimal("0.05")
    default_trailing_callback: Decimal = Decimal("0.02")
    enable_trailing_stop: bool = True
    trailing_activation_pct: Decimal = Decimal("0.02")
    break_even_activation_pct: Decimal = Decimal("0.015")
    break_even_offset_pct: Decimal = Decimal("0.001")

    # ─── Adaptive Cycle ───────────────────────────────────────────────────
    enable_adaptive_cycle: bool = True
    default_cycle_sec: int = 120
    min_cycle_sec: int = 30
    max_cycle_sec: int = 300

    # ─── Correlation ──────────────────────────────────────────────────────
    correlation_threshold: Decimal = Decimal("0.7")

    # ─── Cache ────────────────────────────────────────────────────────────
    meta_cache_ttl_sec: int = 120

    # ─── Logging ──────────────────────────────────────────────────────────
    log_level: str = "INFO"
    log_file: str = "logs/hyperliquid_bot.log"

    # ─── State Paths ──────────────────────────────────────────────────────
    state_path: str = "state/bot_state.json"
    metrics_path: str = "state/bot_metrics.json"

    # ─── Min Sizes ────────────────────────────────────────────────────────
    min_size_by_coin: Dict[str, Decimal] = field(default_factory=dict)
    default_min_size: Decimal = Decimal("1")

    # ─── Trend 4h/1d Specific Parameters ──────────────────────────────────
    primary_timeframe: str = "4h"
    secondary_timeframe: str = "1d"
    entry_timeframe: str = "1h"
    min_trend_duration_hours: int = 24
    volume_confirmation_threshold: Decimal = Decimal("1.5")

    @classmethod
    def from_env(cls) -> "BotConfig":
        """Create BotConfig from environment variables."""
        pairs_raw = _env("TRADING_PAIRS", "BTC,ETH,SOL")
        trading_pairs = [p.strip().upper() for p in pairs_raw.split(",") if p.strip()]

        min_sizes: Dict[str, Decimal] = {
            "BTC": Decimal("0.001"), "ETH": Decimal("0.01"), "SOL": Decimal("0.1"),
            "BNB": Decimal("0.01"), "XRP": Decimal("1"), "ADA": Decimal("10"),
            "DOGE": Decimal("10"), "AVAX": Decimal("0.1"), "LINK": Decimal("0.1"),
            "NEAR": Decimal("1"), "SUI": Decimal("1"), "ARB": Decimal("1"),
            "OP": Decimal("1"), "SEI": Decimal("1"), "TIA": Decimal("0.1"),
            "INJ": Decimal("0.01"), "WIF": Decimal("1"), "PEPE": Decimal("100000"),
            "RENDER": Decimal("0.1"), "FET": Decimal("1"),
        }

        return cls(
            wallet_address=_env("HYPERLIQUID_WALLET_ADDRESS"),
            base_url=_env("HYPERLIQUID_BASE_URL", "https://api.hyperliquid.xyz"),
            info_timeout=_env_int("HYPERLIQUID_INFO_TIMEOUT", 15),
            exchange_timeout=_env_int("HYPERLIQUID_EXCHANGE_TIMEOUT", 30),
            execution_mode=_env("EXECUTION_MODE", "paper").lower(),
            enable_mainnet_trading=_env_bool("ENABLE_MAINNET_TRADING"),
            openrouter_api_key=_env("OPENROUTER_API_KEY"),
            llm_model=_env("LLM_MODEL", "anthropic/claude-opus-4"),
            llm_max_tokens=_env_int("LLM_MAX_TOKENS", 8192),
            llm_temperature=_env_float("LLM_TEMPERATURE", 0.15),
            trading_pairs=trading_pairs,
            max_order_margin_pct=_env_decimal("MAX_ORDER_MARGIN_PCT", "0.08"),
            hard_max_leverage=_env_decimal("HARD_MAX_LEVERAGE", "7"),
            min_confidence_open=_env_decimal("MIN_CONFIDENCE_OPEN", "0.72"),
            min_confidence_manage=_env_decimal("MIN_CONFIDENCE_MANAGE", "0.50"),
            max_margin_usage=_env_decimal("MAX_MARGIN_USAGE", "0.70"),
            max_drawdown_pct=_env_decimal("MAX_DRAWDOWN_PCT", "0.12"),
            max_single_asset_pct=_env_decimal("MAX_SINGLE_ASSET_PCT", "0.35"),
            emergency_margin_threshold=_env_decimal("EMERGENCY_MARGIN_THRESHOLD", "0.85"),
            trade_cooldown_sec=_env_int("TRADE_COOLDOWN_SEC", 300),
            daily_notional_limit_usd=_env_decimal("DAILY_NOTIONAL_LIMIT_USD", "500"),
            max_trades_per_cycle=_env_int("MAX_TRADES_PER_CYCLE", 2),
            max_consecutive_failed_cycles=_env_int("MAX_CONSECUTIVE_FAILED_CYCLES", 5),
            paper_slippage_bps=_env_decimal("PAPER_SLIPPAGE_BPS", "5"),
            volatility_multiplier=_env_decimal("VOLATILITY_MULTIPLIER", "1.2"),
            safe_fallback_mode=_env("SAFE_FALLBACK_MODE", "hold").lower(),
            default_sl_pct=_env_decimal("DEFAULT_SL_PCT", "0.03"),
            default_tp_pct=_env_decimal("DEFAULT_TP_PCT", "0.05"),
            default_trailing_callback=_env_decimal("DEFAULT_TRAILING_CALLBACK", "0.02"),
            enable_trailing_stop=_env_bool("ENABLE_TRAILING_STOP", True),
            trailing_activation_pct=_env_decimal("TRAILING_ACTIVATION_PCT", "0.02"),
            break_even_activation_pct=_env_decimal("BREAK_EVEN_ACTIVATION_PCT", "0.015"),
            break_even_offset_pct=_env_decimal("BREAK_EVEN_OFFSET_PCT", "0.001"),
            enable_adaptive_cycle=_env_bool("ENABLE_ADAPTIVE_CYCLE", True),
            default_cycle_sec=_env_int("DEFAULT_CYCLE_SEC", 120),
            min_cycle_sec=_env_int("MIN_CYCLE_SEC", 30),
            max_cycle_sec=_env_int("MAX_CYCLE_SEC", 300),
            correlation_threshold=_env_decimal("CORRELATION_THRESHOLD", "0.7"),
            meta_cache_ttl_sec=_env_int("META_CACHE_TTL_SEC", 120),
            log_level=_env("LOG_LEVEL", "INFO"),
            log_file=_env("LOG_FILE", "logs/hyperliquid_bot.log"),
            min_size_by_coin=min_sizes,
            # Trend 4h/1d specific parameters
            primary_timeframe=_env("PRIMARY_TIMEFRAME", "4h"),
            secondary_timeframe=_env("SECONDARY_TIMEFRAME", "1d"),
            entry_timeframe=_env("ENTRY_TIMEFRAME", "1h"),
            min_trend_duration_hours=_env_int("MIN_TREND_DURATION_HOURS", 24),
            volume_confirmation_threshold=_env_decimal("VOLUME_CONFIRMATION_THRESHOLD", "1.5"),
        )

    def validate(self) -> List[str]:
        """Validate config, return list of warnings. Raises SystemExit on critical errors."""
        warnings = []

        if not self.wallet_address:
            raise SystemExit("CRITICAL: HYPERLIQUID_WALLET_ADDRESS not set")

        private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY", "")
        if not private_key:
            raise SystemExit("CRITICAL: HYPERLIQUID_PRIVATE_KEY not set")

        # Validate wallet address format
        if not self.wallet_address.startswith("0x") or len(self.wallet_address) != 42:
            raise SystemExit(
                f"CRITICAL: HYPERLIQUID_WALLET_ADDRESS has invalid format. "
                f"Expected 0x-prefixed 42-character hex string, got: {self.wallet_address[:10]}..."
            )

        # Validate wallet matches private key
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
        if self.max_drawdown_pct > Decimal("0.30"):
            warnings.append(f"MAX_DRAWDOWN_PCT={self.max_drawdown_pct} is very high (>30%)")
        if self.hard_max_leverage > Decimal("20"):
            warnings.append(f"HARD_MAX_LEVERAGE={self.hard_max_leverage} is very high (>20x)")
        if not self.openrouter_api_key:
            warnings.append("OPENROUTER_API_KEY not set — LLM disabled, using fallback only")
        if self.daily_notional_limit_usd < Decimal("10"):
            warnings.append(f"DAILY_NOTIONAL_LIMIT_USD={self.daily_notional_limit_usd} is very low")

        # Trend-specific validations
        if self.min_trend_duration_hours < 6:
            warnings.append(f"MIN_TREND_DURATION_HOURS={self.min_trend_duration_hours} is very low for 4h/1d strategy")
        if self.volume_confirmation_threshold < Decimal("1.0"):
            warnings.append(f"VOLUME_CONFIRMATION_THRESHOLD={self.volume_confirmation_threshold} < 1.0 may generate false signals")

        return warnings

    @staticmethod
    def mask_wallet(wallet: str) -> str:
        if not wallet or len(wallet) < 12:
            return "invalid"
        return f"{wallet[:6]}...{wallet[-4:]}"