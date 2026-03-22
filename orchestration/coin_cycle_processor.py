import logging
import time
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from config.bot_config import BotConfig
from correlation_engine import CorrelationEngine
from execution_engine import ExecutionEngine
from llm_engine import LLMEngine
from models import MarketData, PortfolioState
from notifier import Notifier
from order_verifier import OrderVerifier
from portfolio_service import PortfolioService
from position_manager import PositionManager
from risk_manager import RiskManager
from state_store import StateStore
from technical_analyzer_simple import technical_fetcher
from utils.metrics import MetricsCollector
from utils.rate_limiter import TokenBucketRateLimiter

logger = logging.getLogger(__name__)


class CoinCycleProcessor:
    """Gestisce l'intero flusso per singola coin: dati → decisione → risk → esecuzione."""

    def __init__(
        self,
        cfg: BotConfig,
        execution_engine: ExecutionEngine,
        risk_manager: RiskManager,
        state_store: StateStore,
        metrics: MetricsCollector,
        position_manager: PositionManager,
        correlation_engine: CorrelationEngine,
        order_verifier: OrderVerifier,
        notifier: Notifier,
        portfolio_service: PortfolioService,
        llm_engine: Optional[LLMEngine],
        hl_rate_limiter: TokenBucketRateLimiter,
        llm_rate_limiter: TokenBucketRateLimiter,
        update_protection_without_trade: Callable[[str, Dict[str, Any]], bool],
        sync_exchange_protective_orders: Callable[[str], bool],
        cancel_exchange_protective_orders: Callable[[str], None],
    ):
        self.cfg = cfg
        self.execution_engine = execution_engine
        self.risk_manager = risk_manager
        self.state_store = state_store
        self.metrics = metrics
        self.position_manager = position_manager
        self.correlation_engine = correlation_engine
        self.order_verifier = order_verifier
        self.notifier = notifier
        self.portfolio_service = portfolio_service
        self.llm_engine = llm_engine
        self.hl_rate_limiter = hl_rate_limiter
        self.llm_rate_limiter = llm_rate_limiter
        self.update_protection_without_trade = update_protection_without_trade
        self.sync_exchange_protective_orders = sync_exchange_protective_orders
        self.cancel_exchange_protective_orders = cancel_exchange_protective_orders

        self._dynamic_min_sizes: Dict[str, Decimal] = {}

    def process_single_coin(
        self,
        coin: str,
        portfolio: PortfolioState,
        state: Dict[str, Any],
        daily_notional_used: Decimal,
        peak: Decimal,
        consecutive_losses: int,
        all_mids: Optional[Dict[str, str]],
        recent_trades: List[Dict[str, Any]],
        correlations: Dict[str, Dict[str, Decimal]],
    ) -> Optional[Dict[str, Any]]:
        self.hl_rate_limiter.acquire(3)
        tech_data = technical_fetcher.get_technical_indicators(coin)
        if not tech_data:
            logger.warning(f"Skipping {coin}: no market data")
            return None

        market_data = MarketData(
            coin=coin,
            last_price=tech_data["current_price"],
            change_24h=tech_data["change_24h"],
            volume_24h=tech_data["volume_24h"],
            funding_rate=tech_data["funding_rate"],
            timestamp=time.time(),
        )

        self._log_coin_indicators(coin, market_data, tech_data)

        funding_data = technical_fetcher.get_funding_for_coin(coin)
        decision = self._get_decision(
            coin=coin,
            market_data=market_data,
            portfolio=portfolio,
            tech_data=tech_data,
            all_mids=all_mids,
            funding_data=funding_data,
            recent_trades=recent_trades,
            peak=peak,
            consecutive_losses=consecutive_losses,
        )

        logger.info(
            f"{coin} decision: action={decision['action']}, size={decision['size']}, "
            f"leverage={decision['leverage']}, confidence={decision['confidence']}, "
            f"sl_pct={decision.get('stop_loss_pct')}, tp_pct={decision.get('take_profit_pct')}"
        )

        corr_ok, corr_reason = self.correlation_engine.check_correlation_risk(
            coin, decision["action"], portfolio.positions, correlations
        )
        if not corr_ok and decision["action"] in ["buy", "sell", "increase_position"]:
            logger.info(f"{coin} blocked by correlation risk: {corr_reason}")
            self.metrics.increment("risk_rejections_total")
            return None

        min_size = self._resolve_min_size(coin)
        self.risk_manager.min_size_by_coin[coin] = min_size

        volatility = Decimal("0")
        if tech_data.get("intraday_atr", Decimal("0")) > 0 and market_data.last_price > 0:
            volatility = tech_data["intraday_atr"] / market_data.last_price

        # RISK CHECK (soft/bypass mode): non blocchiamo più i segnali LLM.
        risk_ok, risk_reason = self.risk_manager.check_order(
            coin,
            decision,
            market_data.last_price,
            portfolio,
            state.get("last_trade_timestamps_by_coin", state.get("last_trade_timestamp_by_coin", {})),
            daily_notional_used,
            time.time(),
            volatility,
            peak,
        )
        if not risk_ok:
            logger.warning(f"{coin} risk manager rejection bypassed: {risk_reason}")

        if decision["action"] == "hold" and coin in portfolio.positions:
            updated = self.update_protection_without_trade(coin, decision)
            if updated:
                logger.info(f"{coin} hold with SL/TP update applied")
            self.metrics.increment("holds_total")
            return {"trades": 0, "notional": Decimal("0"), "failed": False}

        snapshot = None
        if self.cfg.execution_mode == "live" and self.cfg.enable_mainnet_trading:
            snapshot = self.order_verifier.snapshot_position(self.cfg.wallet_address, coin)

        result = self.execution_engine.execute(coin, decision, market_data, portfolio.positions)

        executed_price = Decimal(str(result.get("filled_price", market_data.last_price)))
        if executed_price <= 0:
            executed_price = market_data.last_price

        executed_size = Decimal(str(result.get("executed_size", decision["size"])))
        if executed_size <= 0:
            executed_size = Decimal(str(decision["size"]))

        fill_status = "unknown"
        if snapshot and result["success"] and decision["action"] in ["buy", "sell", "increase_position"]:
            expected_side = "buy" if decision["action"] in ["buy", "increase_position"] else "sell"
            expected_size = Decimal(str(executed_size))

            verification = self.order_verifier.verify_fill(
                self.cfg.wallet_address, coin, expected_side, expected_size, snapshot
            )
            fill_status = verification.get("fill_status", "unknown")

            if fill_status == "not_filled":
                late_confirmed, late_status = self._late_confirm_fill(
                    coin=coin,
                    snapshot=snapshot,
                    expected_side=expected_side,
                    expected_size=expected_size,
                )
                if late_confirmed:
                    fill_status = late_status
                    logger.info(f"{coin} late fill confirmation succeeded: {late_status}")
                else:
                    logger.warning(f"{coin} order NOT FILLED — marking as failed")
                    result["success"] = False
                    result["reason"] = "order_not_filled"

        trade_record = {
            "timestamp": time.time(),
            "coin": coin,
            "action": decision["action"],
            "size": str(executed_size),
            "price": str(executed_price),
            "notional": str(result.get("notional", "0")),
            "leverage": decision["leverage"],
            "confidence": decision["confidence"],
            "reasoning": decision.get("reasoning", ""),
            "success": result["success"],
            "mode": self.cfg.execution_mode,
            "trigger": "ai",
            "order_status": fill_status,
        }
        self.state_store.add_trade_record(state, trade_record)

        if result["success"]:
            notional = Decimal(str(result["notional"]))
            if notional > 0:
                state.setdefault("last_trade_timestamp_by_coin", {})[coin] = time.time()
                self.metrics.increment("trades_executed_total")

                if decision["action"] in ["buy", "sell", "increase_position"]:
                    is_long = decision["action"] in ["buy", "increase_position"]
                    sl_pct = decision.get("stop_loss_pct")
                    tp_pct = decision.get("take_profit_pct")

                    self.position_manager.register_position(
                        coin=coin,
                        size=executed_size,
                        entry_price=executed_price,
                        is_long=is_long,
                        leverage=decision["leverage"],
                        sl_pct=sl_pct if isinstance(sl_pct, Decimal) else None,
                        tp_pct=tp_pct if isinstance(tp_pct, Decimal) else None,
                    )
                    self.sync_exchange_protective_orders(coin)

                elif decision["action"] == "close_position":
                    self.cancel_exchange_protective_orders(coin)
                    self.position_manager.remove_position(coin)

                elif decision["action"] == "reduce_position":
                    self.sync_exchange_protective_orders(coin)

                self.notifier.notify_trade(trade_record)
                logger.info(f"{coin} executed: reason={result['reason']}, notional=${notional}")
                return {"trades": 1, "notional": notional, "failed": False}

            self.metrics.increment("holds_total")
            logger.info(f"{coin}: hold (no trade)")
            return {"trades": 0, "notional": Decimal("0"), "failed": False}

        self.metrics.increment("execution_failures_total")
        logger.warning(f"{coin} execution failed: {result.get('reason', 'unknown')}")
        return {"trades": 0, "notional": Decimal("0"), "failed": True}

    def _get_decision(
        self,
        coin: str,
        market_data: MarketData,
        portfolio: PortfolioState,
        tech_data: Dict[str, Any],
        all_mids: Optional[Dict[str, str]],
        funding_data: Optional[Dict[str, Any]],
        recent_trades: List[Dict[str, Any]],
        peak: Decimal,
        consecutive_losses: int,
    ) -> Dict[str, Any]:
        if self.llm_engine:
            self.llm_rate_limiter.acquire(1)
            self.metrics.increment("llm_calls_total")

            managed_position = self._build_managed_position_context(coin)
            protective_orders = self._extract_protective_orders_for_coin(coin)

            decision = self.llm_engine.get_trading_decision(
                market_data=market_data,
                portfolio_state=portfolio,
                technical_data=tech_data,
                all_mids=all_mids,
                funding_data=funding_data,
                recent_trades=recent_trades,
                peak_portfolio_value=peak,
                consecutive_losses=consecutive_losses,
                managed_position=managed_position,
                protective_orders=protective_orders,
            )
            if not decision:
                self.metrics.increment("llm_errors_total")
                logger.warning(f"LLM failed for {coin}, using fallback")
                return self._fallback_decision()
            return decision
        return self._fallback_decision()

    @staticmethod
    def _fallback_decision() -> Dict[str, Any]:
        return {
            "action": "hold",
            "size": Decimal("0"),
            "leverage": 1,
            "confidence": 0.0,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "reasoning": "LLM unavailable — safe fallback to hold",
        }

    def _late_confirm_fill(
        self,
        coin: str,
        snapshot: Dict[str, Any],
        expected_side: str,
        expected_size: Decimal,
        tolerance_pct: Decimal = Decimal("0.05"),
    ) -> Tuple[bool, str]:
        latest_portfolio = self.portfolio_service.get_portfolio_state()

        size_before = Decimal(str(snapshot.get("size_before", "0")))
        current_size = Decimal("0")
        if coin in latest_portfolio.positions:
            current_size = Decimal(str(latest_portfolio.positions[coin].get("size", 0)))

        actual_change = current_size - size_before
        expected_change = expected_size if expected_side == "buy" else -expected_size

        if expected_change == 0:
            return False, "not_filled"

        fill_ratio = abs(actual_change) / abs(expected_change)
        if fill_ratio >= (Decimal("1") - tolerance_pct):
            return True, "filled_late"
        if fill_ratio >= Decimal("0.1"):
            return True, "partially_filled_late"
        return False, "not_filled"

    def _build_managed_position_context(self, coin: str) -> Optional[Dict[str, Any]]:
        managed = self.position_manager.get_position(coin)
        if not managed:
            return None

        sl_price = managed.stop_loss.calculate_stop_price(managed.entry_price, managed.is_long)
        if managed.break_even.activated and managed.stop_loss.price is not None:
            sl_price = managed.stop_loss.price
        tp_price = managed.take_profit.calculate_tp_price(managed.entry_price, managed.is_long)

        return {
            "coin": managed.coin,
            "is_long": managed.is_long,
            "size": str(managed.size),
            "entry_price": str(managed.entry_price),
            "stop_loss_pct": str(managed.stop_loss.percentage),
            "take_profit_pct": str(managed.take_profit.percentage),
            "stop_loss_price": str(sl_price),
            "take_profit_price": str(tp_price),
            "break_even_activated": bool(managed.break_even.activated),
            "stop_loss_order_id": managed.stop_loss_order_id,
            "take_profit_order_id": managed.take_profit_order_id,
        }

    @staticmethod
    def _extract_order_coin(order: Dict[str, Any]) -> str:
        if not isinstance(order, dict):
            return ""
        coin = str(order.get("coin", order.get("symbol", ""))).strip().upper()
        if coin:
            return coin
        nested = order.get("order", {})
        if isinstance(nested, dict):
            return str(nested.get("coin", nested.get("symbol", ""))).strip().upper()
        return ""

    @staticmethod
    def _extract_order_oid(order: Dict[str, Any]) -> Optional[int]:
        if not isinstance(order, dict):
            return None
        direct = order.get("oid")
        if direct is not None:
            return int(direct)

        nested = order.get("order", {})
        if isinstance(nested, dict):
            nested_oid = nested.get("oid")
            if nested_oid is not None:
                return int(nested_oid)

        resting = order.get("resting", {})
        if isinstance(resting, dict):
            resting_oid = resting.get("oid")
            if resting_oid is not None:
                return int(resting_oid)
        return None

    @staticmethod
    def _extract_order_side(order: Dict[str, Any]) -> str:
        def norm(v: Any) -> str:
            raw = str(v or "").strip().lower()
            if raw in {"b", "buy", "bid", "long", "true"}:
                return "buy"
            if raw in {"a", "s", "sell", "ask", "short", "false"}:
                return "sell"
            return ""

        if not isinstance(order, dict):
            return ""

        for candidate in [order.get("side"), order.get("dir"), order.get("b")]:
            side = norm(candidate)
            if side:
                return side

        nested = order.get("order", {})
        if isinstance(nested, dict):
            for candidate in [nested.get("side"), nested.get("dir"), nested.get("b")]:
                side = norm(candidate)
                if side:
                    return side

        return ""

    @staticmethod
    def _extract_order_tpsl(order: Dict[str, Any]) -> str:
        if not isinstance(order, dict):
            return ""

        candidates: List[Any] = [order.get("tpsl"), order.get("triggerType")]
        trigger_obj = order.get("trigger", {})
        if isinstance(trigger_obj, dict):
            candidates.append(trigger_obj.get("tpsl"))
            candidates.append(trigger_obj.get("triggerType"))

        order_type = order.get("orderType", {})
        if isinstance(order_type, dict):
            trigger_obj_2 = order_type.get("trigger", {})
            if isinstance(trigger_obj_2, dict):
                candidates.append(trigger_obj_2.get("tpsl"))
                candidates.append(trigger_obj_2.get("triggerType"))

        nested = order.get("order", {})
        if isinstance(nested, dict):
            candidates.append(nested.get("tpsl"))
            candidates.append(nested.get("triggerType"))
            nested_trigger = nested.get("trigger", {})
            if isinstance(nested_trigger, dict):
                candidates.append(nested_trigger.get("tpsl"))
                candidates.append(nested_trigger.get("triggerType"))

        for candidate in candidates:
            value = str(candidate or "").strip().lower()
            if value in {"tp", "sl"}:
                return value

        if bool(order.get("isTp")):
            return "tp"
        if bool(order.get("isSl")):
            return "sl"

        return ""

    @staticmethod
    def _extract_order_trigger_px(order: Dict[str, Any]) -> Decimal:
        if not isinstance(order, dict):
            return Decimal("0")

        def d(v: Any) -> Decimal:
            if v is None:
                return Decimal("0")
            return Decimal(str(v))

        candidates: List[Any] = [order.get("triggerPx"), order.get("tpTriggerPx"), order.get("slTriggerPx")]

        trigger_obj = order.get("trigger", {})
        if isinstance(trigger_obj, dict):
            candidates.append(trigger_obj.get("triggerPx"))

        order_type = order.get("orderType", {})
        if isinstance(order_type, dict):
            trigger_obj_2 = order_type.get("trigger", {})
            if isinstance(trigger_obj_2, dict):
                candidates.append(trigger_obj_2.get("triggerPx"))

        nested = order.get("order", {})
        if isinstance(nested, dict):
            candidates.extend([nested.get("triggerPx"), nested.get("tpTriggerPx"), nested.get("slTriggerPx")])
            nested_trigger = nested.get("trigger", {})
            if isinstance(nested_trigger, dict):
                candidates.append(nested_trigger.get("triggerPx"))
            nested_order_type = nested.get("orderType", {})
            if isinstance(nested_order_type, dict):
                nested_trigger_2 = nested_order_type.get("trigger", {})
                if isinstance(nested_trigger_2, dict):
                    candidates.append(nested_trigger_2.get("triggerPx"))

        for c in candidates:
            px = d(c)
            if px > 0:
                return px

        return Decimal("0")

    @staticmethod
    def _extract_order_reduce_only(order: Dict[str, Any]) -> bool:
        if not isinstance(order, dict):
            return False

        candidates: List[Any] = [order.get("r"), order.get("reduceOnly"), order.get("isReduceOnly")]
        nested = order.get("order", {})
        if isinstance(nested, dict):
            candidates.extend([nested.get("r"), nested.get("reduceOnly"), nested.get("isReduceOnly")])

        for c in candidates:
            if isinstance(c, bool) and c:
                return True
            if str(c).strip().lower() in {"true", "1"}:
                return True

        return False

    def _extract_protective_orders_for_coin(self, coin: str) -> List[Dict[str, Any]]:
        exchange_client = self.execution_engine.exchange_client
        trading_user = exchange_client.get_trading_user_address()
        open_orders = exchange_client.get_open_orders(trading_user, force_refresh=True)

        protective_orders: List[Dict[str, Any]] = []
        target_coin = str(coin or "").strip().upper()

        for order in open_orders:
            order_coin = self._extract_order_coin(order)
            if order_coin != target_coin:
                continue

            tpsl = self._extract_order_tpsl(order)
            if tpsl not in {"tp", "sl"}:
                continue

            protective_orders.append({
                "oid": self._extract_order_oid(order),
                "coin": order_coin,
                "tpsl": tpsl,
                "trigger_px": str(self._extract_order_trigger_px(order)),
                "side": self._extract_order_side(order),
                "reduce_only": self._extract_order_reduce_only(order),
            })

        protective_orders.sort(key=lambda o: (o.get("tpsl", ""), o.get("oid") or 0))
        return protective_orders

    @staticmethod
    def _log_coin_indicators(coin: str, market_data: MarketData, tech_data: Dict[str, Any]) -> None:
        trends_aligned = tech_data.get("trends_aligned", False)
        intraday_trend = tech_data.get("intraday_trend", "unknown")
        hourly_ctx = tech_data.get("hourly_context", {})
        hourly_trend = hourly_ctx.get("trend", "unknown")

        logger.info(
            f"{coin}: price=${market_data.last_price}, "
            f"RSI14={float(tech_data.get('current_rsi_14', 50)):.1f}, "
            f"BB={float(tech_data.get('bb_position', 0.5)):.2f}, "
            f"vol_ratio={float(tech_data.get('volume_ratio', 1)):.2f}, "
            f"trends={'ALIGNED' if trends_aligned else 'DIVERGENT'} "
            f"(1h={intraday_trend}, 4h={hourly_trend})"
        )

    def _resolve_min_size(self, coin: str) -> Decimal:
        if coin in self.cfg.min_size_by_coin:
            return self.cfg.min_size_by_coin[coin]

        if coin in self._dynamic_min_sizes:
            return self._dynamic_min_sizes[coin]

        mids = technical_fetcher.get_all_mids()
        if mids and coin in mids:
            mid_price = Decimal(str(mids[coin]))
            if mid_price > 0:
                raw_min = Decimal("1") / mid_price
                if raw_min < Decimal("0.001"):
                    resolved = Decimal("0.001")
                elif raw_min < Decimal("0.01"):
                    resolved = Decimal("0.01")
                elif raw_min < Decimal("0.1"):
                    resolved = Decimal("0.1")
                elif raw_min < Decimal("1"):
                    resolved = Decimal("1")
                elif raw_min < Decimal("10"):
                    resolved = Decimal("10")
                elif raw_min < Decimal("100"):
                    resolved = Decimal("100")
                elif raw_min < Decimal("1000"):
                    resolved = Decimal("1000")
                else:
                    resolved = Decimal("10000")

                self._dynamic_min_sizes[coin] = resolved
                logger.info(f"Dynamic min size for {coin}: {resolved} (price=${mid_price})")
                return resolved

        logger.warning(f"No min size data for {coin}, using default {self.cfg.default_min_size}")
        return self.cfg.default_min_size