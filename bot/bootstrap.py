import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config.bot_config import BotConfig
from correlation_engine import CorrelationEngine
from cycle_orchestrator import CycleOrchestrator
from exchange_client import HyperliquidExchangeClient
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from notifier import Notifier
from order_verifier import OrderVerifier
from portfolio_service import PortfolioService
from position_manager import PositionManager
from risk_manager import RiskManager
from runtime_config_store import RuntimeConfigStore
from state_store import StateStore
from utils.health import HealthCheckResult, HealthMonitor, HealthStatus, check_disk_space, check_file_writable
from utils.logging_config import setup_logging
from utils.metrics import MetricsCollector
from utils.rate_limiter import get_rate_limiter


@dataclass
class ServiceContainer:
    cfg: Optional[BotConfig] = None
    exchange_client: Optional[HyperliquidExchangeClient] = None
    state_store: Optional[StateStore] = None
    runtime_config_store: Optional[RuntimeConfigStore] = None
    metrics: Optional[MetricsCollector] = None
    notifier: Optional[Notifier] = None
    health_monitor: Optional[HealthMonitor] = None
    portfolio_service: Optional[PortfolioService] = None
    orchestrator: Optional[CycleOrchestrator] = None


@dataclass
class BotRuntimeContext:
    cfg: BotConfig
    exchange_client: HyperliquidExchangeClient
    state_store: StateStore
    runtime_config_store: RuntimeConfigStore
    metrics: MetricsCollector
    notifier: Notifier
    health_monitor: HealthMonitor
    portfolio_service: PortfolioService
    orchestrator: CycleOrchestrator
    base_profile: Dict[str, Any]


class BotBootstrap:
    """Wires the full bot dependency graph and returns a runtime context."""

    @staticmethod
    def _setup_health_checks(health_monitor: HealthMonitor, exchange_client: HyperliquidExchangeClient) -> None:
        def _check_exchange_health() -> HealthCheckResult:
            meta = exchange_client.get_meta(force_refresh=True)
            if meta:
                return HealthCheckResult(
                    name="exchange_connectivity",
                    status=HealthStatus.HEALTHY,
                    message="Hyperliquid API reachable",
                    details={"assets_count": len(meta.get("universe", []))}
                )
            return HealthCheckResult(
                name="exchange_connectivity",
                status=HealthStatus.UNHEALTHY,
                message="Hyperliquid API unreachable"
            )

        health_monitor.add_check("exchange_connectivity", _check_exchange_health, interval=60.0)
        health_monitor.add_check("disk_space", lambda: check_disk_space(".", min_free_gb=0.5), interval=300.0)
        health_monitor.add_check("state_writable", lambda: check_file_writable("state"), interval=300.0)

    @staticmethod
    def _build_cfg() -> BotConfig:
        cfg = BotConfig.from_env()
        setup_logging(log_level=cfg.log_level, json_format=True, log_file=cfg.log_file, console_output=True)

        warnings = cfg.validate()
        for warning in warnings:
            logging.warning(f"CONFIG WARNING: {warning}")
        return cfg

    @staticmethod
    def _build_exchange_client(cfg: BotConfig) -> HyperliquidExchangeClient:
        # Exclusive API wallet signer mode (validated in BotConfig.validate)
        api_signer_key = cfg.api_signer_private_key
        return HyperliquidExchangeClient(
            base_url=cfg.base_url,
            private_key=api_signer_key,
            enable_mainnet_trading=cfg.enable_mainnet_trading,
            execution_mode=cfg.execution_mode,
            meta_cache_ttl_sec=cfg.meta_cache_ttl_sec,
            paper_slippage_bps=cfg.paper_slippage_bps,
            info_timeout=cfg.info_timeout,
            exchange_timeout=cfg.exchange_timeout,
            trading_user_address=cfg.wallet_address,
            signer_mode=cfg.signer_mode,
        )

    @staticmethod
    def _build_state_runtime_metrics_notifier_health(
        cfg: BotConfig,
        exchange_client: HyperliquidExchangeClient,
    ):
        state_store = StateStore(cfg.state_path, cfg.metrics_path)
        runtime_config_store = RuntimeConfigStore(
            "state/runtime_config.json",
            cfg.trading_pairs,
            default_strategy_mode=cfg.default_strategy_mode,
        )
        metrics = MetricsCollector()
        notifier = Notifier(enabled=True)
        health_monitor = HealthMonitor()
        BotBootstrap._setup_health_checks(health_monitor, exchange_client)
        return state_store, runtime_config_store, metrics, notifier, health_monitor

    @staticmethod
    def _build_portfolio_service(exchange_client: HyperliquidExchangeClient, cfg: BotConfig) -> PortfolioService:
        return PortfolioService(exchange_client, cfg.wallet_address)

    @staticmethod
    def _build_orchestrator(
        cfg: BotConfig,
        exchange_client: HyperliquidExchangeClient,
        state_store: StateStore,
        metrics: MetricsCollector,
        notifier: Notifier,
        health_monitor: HealthMonitor,
        portfolio_service: PortfolioService,
    ) -> CycleOrchestrator:
        return CycleOrchestrator(
            cfg=cfg,
            exchange_client=exchange_client,
            execution_engine=ExecutionEngine(exchange_client),
            risk_manager=RiskManager(
                min_size_by_coin=dict(cfg.min_size_by_coin),
                hard_max_leverage=cfg.hard_max_leverage,
                min_confidence_open=cfg.min_confidence_open,
                min_confidence_manage=cfg.min_confidence_manage,
                max_margin_usage=cfg.max_margin_usage,
                max_order_margin_pct=cfg.max_order_margin_pct,
                max_order_notional_usd=cfg.max_order_notional_usd,
                trade_cooldown_sec=cfg.trade_cooldown_sec,
                daily_notional_limit_usd=cfg.daily_notional_limit_usd,
                volatility_multiplier=cfg.volatility_multiplier,
                max_drawdown_pct=cfg.max_drawdown_pct,
                max_single_asset_pct=cfg.max_single_asset_pct,
                emergency_margin_threshold=cfg.emergency_margin_threshold,
            ),
            state_store=state_store,
            metrics=metrics,
            position_manager=PositionManager(
                default_sl_pct=cfg.trend_sl_pct,
                default_tp_pct=cfg.trend_tp_pct,
                default_trailing_callback=cfg.trend_trailing_callback,
                enable_trailing_stop=cfg.enable_trailing_stop,
                trailing_activation_pct=cfg.trend_trailing_activation_pct,
                break_even_activation_pct=cfg.trend_break_even_activation_pct,
                break_even_offset_pct=cfg.break_even_offset_pct,
            ),
            correlation_engine=CorrelationEngine(correlation_threshold=cfg.correlation_threshold),
            order_verifier=OrderVerifier(exchange_client=exchange_client, max_wait_sec=20.0, check_interval=2.0),
            notifier=notifier,
            health_monitor=health_monitor,
            portfolio_service=portfolio_service,
            llm_engine=LLMEngine(
                api_key=cfg.openrouter_api_key,
                model=cfg.llm_model,
                max_tokens=cfg.llm_max_tokens,
                temperature=cfg.llm_temperature,
            ) if cfg.openrouter_api_key else None,
            hl_rate_limiter=get_rate_limiter("hyperliquid_api", max_tokens=20, tokens_per_second=2.0),
            llm_rate_limiter=get_rate_limiter("openrouter_api", max_tokens=5, tokens_per_second=0.5),
            trading_pairs=list(cfg.trading_pairs),
        )

    @staticmethod
    def _build_base_profile(cfg: BotConfig) -> Dict[str, Any]:
        return {
            "default_cycle_sec": cfg.default_cycle_sec,
            "min_cycle_sec": cfg.min_cycle_sec,
            "max_cycle_sec": cfg.max_cycle_sec,
            "max_trades_per_cycle": cfg.max_trades_per_cycle,
            "hard_max_leverage": cfg.hard_max_leverage,
            "min_confidence_open": cfg.min_confidence_open,
            "min_confidence_manage": cfg.min_confidence_manage,
            "max_order_margin_pct": cfg.max_order_margin_pct,
            "trade_cooldown_sec": cfg.trade_cooldown_sec,
            "daily_notional_limit_usd": cfg.daily_notional_limit_usd,
            "max_drawdown_pct": cfg.max_drawdown_pct,
            "max_single_asset_pct": cfg.max_single_asset_pct,
            "emergency_margin_threshold": cfg.emergency_margin_threshold,
            "trend_sl_pct": cfg.trend_sl_pct,
            "trend_tp_pct": cfg.trend_tp_pct,
            "trend_break_even_activation_pct": cfg.trend_break_even_activation_pct,
            "trend_trailing_activation_pct": cfg.trend_trailing_activation_pct,
            "trend_trailing_callback": cfg.trend_trailing_callback,
            "trend_position_size_pct": cfg.trend_position_size_pct,
            "volume_confirmation_threshold": cfg.volume_confirmation_threshold,
        }

    @staticmethod
    def build(container: Optional[ServiceContainer] = None) -> BotRuntimeContext:
        container = container or ServiceContainer()

        cfg = container.cfg or BotBootstrap._build_cfg()
        exchange_client = container.exchange_client or BotBootstrap._build_exchange_client(cfg)

        if all([
            container.state_store,
            container.runtime_config_store,
            container.metrics,
            container.notifier,
            container.health_monitor,
        ]):
            state_store = container.state_store
            runtime_config_store = container.runtime_config_store
            metrics = container.metrics
            notifier = container.notifier
            health_monitor = container.health_monitor
        else:
            state_store, runtime_config_store, metrics, notifier, health_monitor = (
                BotBootstrap._build_state_runtime_metrics_notifier_health(cfg, exchange_client)
            )

        portfolio_service = container.portfolio_service or BotBootstrap._build_portfolio_service(exchange_client, cfg)

        orchestrator = container.orchestrator or BotBootstrap._build_orchestrator(
            cfg=cfg,
            exchange_client=exchange_client,
            state_store=state_store,
            metrics=metrics,
            notifier=notifier,
            health_monitor=health_monitor,
            portfolio_service=portfolio_service,
        )

        base_profile = BotBootstrap._build_base_profile(cfg)

        return BotRuntimeContext(
            cfg=cfg,
            exchange_client=exchange_client,
            state_store=state_store,
            runtime_config_store=runtime_config_store,
            metrics=metrics,
            notifier=notifier,
            health_monitor=health_monitor,
            portfolio_service=portfolio_service,
            orchestrator=orchestrator,
            base_profile=base_profile,
        )

    @staticmethod
    def build_for_test(overrides: Optional[Dict[str, Any]] = None) -> BotRuntimeContext:
        ctx = BotBootstrap.build()
        if not overrides:
            return ctx

        for key, value in overrides.items():
            if hasattr(ctx, key):
                setattr(ctx, key, value)

        return ctx