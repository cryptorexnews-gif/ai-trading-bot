meta_cache_ttl_sec=_env_int("META_CACHE_TTL_SEC", 86400),
            log_level=_env("LOG_LEVEL", "INFO"),
            log_file=_env("LOG_FILE", "logs/hyperliquid_bot.log"),
            min_size_by_coin=min_sizes,
            # Trend 4h/1d specific parameters
            primary_timeframe=_env("PRIMARY_TIMEFRAME", "4h"),
            secondary_timeframe=_env("SECONDARY_TIMEFRAME", "1d"),
            entry_timeframe=_env("ENTRY_TIMEFRAME", "1h"),
            min_trend_duration_hours=_env_int("MIN_TREND_DURATION_HOURS", 36),
            volume_confirmation_threshold=_env_decimal("VOLUME_CONFIRMATION_THRESHOLD", "1.6"),
            trend_confirmation_required=_env_bool("TREND_CONFIRMATION_REQUIRED", True),
            max_trend_positions=_env_int("MAX_TREND_POSITIONS", 2),
            trend_position_size_pct=_env_decimal("TREND_POSITION_SIZE_PCT", "0.02"),
            trend_leverage_multiplier=_env_decimal("TREND_LEVERAGE_MULTIPLIER", "0.9"),
            trend_sl_pct=_env_decimal("TREND_SL_PCT", "0.04"),
            trend_tp_pct=_env_decimal("TREND_TP_PCT", "0.08"),
            trend_break_even_activation_pct=_env_decimal("TREND_BREAK_EVEN_ACTIVATION_PCT", "0.02"),
            trend_trailing_activation_pct=_env_decimal("TREND_TRAILING_ACTIVATION_PCT", "0.03"),
            trend_trailing_callback=_env_decimal("TREND_TRAILING_CALLBACK", "0.02"),
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
        
        # Trend-specific validations
        if self.min_trend_duration_hours < 24:
            warnings.append(f"MIN_TREND_DURATION_HOURS={self.min_trend_duration_hours} è basso per trend 4H/1D")
        if self.volume_confirmation_threshold < Decimal("1.0"):
            warnings.append(f"VOLUME_CONFIRMATION_THRESHOLD={self.volume_confirmation_threshold} < 1.0 può generare falsi segnali")
        if self.trend_position_size_pct > Decimal("0.05"):
            warnings.append(f"TREND_POSITION_SIZE_PCT={self.trend_position_size_pct} è alto (>5%) per trend trading ultra-conservativo")
        if self.trend_sl_pct < Decimal("0.03"):
            warnings.append(f"TREND_SL_PCT={self.trend_sl_pct} è molto stretto per trend trading")
        if self.trend_tp_pct / self.trend_sl_pct < Decimal("1.5"):
            warnings.append(f"Trend R:R ratio è basso: TP={self.trend_tp_pct}, SL={self.trend_sl_pct}")
        
        # Cycle validation
        if self.default_cycle_sec < 300:
            warnings.append(f"DEFAULT_CYCLE_SEC={self.default_cycle_sec} è molto breve (<5 minuti)")
        if self.default_cycle_sec > 3600:
            warnings.append(f"DEFAULT_CYCLE_SEC={self.default_cycle_sec} è molto lungo (>60 minuti)")

        return warnings

    @staticmethod
    def mask_wallet(wallet: str) -> str:
        if not wallet or len(wallet) < 12:
            return "invalid"
        return f"{wallet[:6]}...{wallet[-4:]}"