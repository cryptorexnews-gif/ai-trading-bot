import logging
from typing import Any, Dict, List

from bot.runtime_loader import load_runtime_config_payload, runtime_has_changes
from bot.runtime_profile import apply_runtime_param_overrides, apply_strategy_profile


class RuntimeConfigApplier:
    """Applies runtime strategy mode, trading pairs, and runtime params safely."""

    def __init__(self, context):
        self.context = context
        self.active_strategy_mode = context.cfg.default_strategy_mode
        self.active_runtime_pairs: List[str] = list(context.cfg.trading_pairs)
        self.active_runtime_params: Dict[str, str] = {}
        self.next_cycle_sec = context.cfg.default_cycle_sec

    def _validate_trading_pairs(self, pairs: List[str]) -> List[str]:
        meta = self.context.exchange_client.get_meta(force_refresh=True)
        if not meta:
            logging.warning("Cannot validate trading pairs — meta unavailable")
            return pairs

        available = {asset.get("name") for asset in meta.get("universe", [])}
        valid = [coin for coin in pairs if coin in available]
        invalid = [coin for coin in pairs if coin not in available]

        if invalid:
            logging.warning(f"Trading pairs NOT found on Hyperliquid (removed): {invalid}")
        logging.info(f"Validated {len(valid)} trading pairs: {valid}")
        return valid

    def _apply_strategy_profile(self, strategy_mode: str) -> None:
        apply_strategy_profile(
            cfg=self.context.cfg,
            risk_manager=self.context.orchestrator.risk_manager,
            position_manager=self.context.orchestrator.position_manager,
            base_profile=self.context.base_profile,
            strategy_mode=strategy_mode,
        )
        self.next_cycle_sec = self.context.cfg.default_cycle_sec

    def _apply_runtime_param_overrides(self, params: Dict[str, str]) -> None:
        apply_runtime_param_overrides(
            cfg=self.context.cfg,
            risk_manager=self.context.orchestrator.risk_manager,
            position_manager=self.context.orchestrator.position_manager,
            params=params,
        )
        self.next_cycle_sec = self.context.cfg.default_cycle_sec

    def apply(self, force: bool = False) -> None:
        payload = load_runtime_config_payload(self.context.runtime_config_store, self.context.cfg)
        runtime_mode = payload["strategy_mode"]
        runtime_pairs = payload["trading_pairs"]
        runtime_params = payload["strategy_params"]

        if not force and not runtime_has_changes(
            payload=payload,
            active_mode=self.active_strategy_mode,
            active_pairs=self.active_runtime_pairs,
            active_params=self.active_runtime_params,
        ):
            return

        validated_pairs = self._validate_trading_pairs(runtime_pairs)
        if not validated_pairs:
            validated_pairs = self._validate_trading_pairs(list(self.context.cfg.trading_pairs))

        self._apply_strategy_profile(runtime_mode)
        self._apply_runtime_param_overrides(runtime_params)

        self.context.orchestrator.trading_pairs = validated_pairs
        self.context.cfg.trading_pairs = list(validated_pairs)

        self.active_strategy_mode = runtime_mode
        self.active_runtime_pairs = list(validated_pairs)
        self.active_runtime_params = dict(runtime_params)

        logging.info(
            f"Runtime config applied: strategy_mode={runtime_mode}, "
            f"pairs={validated_pairs}, cycle={self.context.cfg.default_cycle_sec}s, "
            f"max_trades_per_cycle={self.context.cfg.max_trades_per_cycle}, "
            f"runtime_params={len(runtime_params)}"
        )