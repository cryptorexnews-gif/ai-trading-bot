import logging
from decimal import Decimal
from typing import Any, Dict, Tuple

from technical_analyzer_simple import technical_fetcher

logger = logging.getLogger(__name__)


def late_confirm_fill(
    coin: str,
    snapshot: Dict[str, Any],
    expected_side: str,
    expected_size: Decimal,
    portfolio_service,
    tolerance_pct: Decimal = Decimal("0.05"),
) -> Tuple[bool, str]:
    latest_portfolio = portfolio_service.get_portfolio_state()

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


def log_coin_indicators(coin: str, market_data, tech_data: Dict[str, Any]) -> None:
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


def resolve_min_size(coin: str, cfg, dynamic_cache: Dict[str, Decimal]) -> Decimal:
    if coin in cfg.min_size_by_coin:
        return cfg.min_size_by_coin[coin]

    if coin in dynamic_cache:
        return dynamic_cache[coin]

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

            dynamic_cache[coin] = resolved
            logger.info(f"Dynamic min size for {coin}: {resolved} (price=${mid_price})")
            return resolved

    logger.warning(f"No min size data for {coin}, using default {cfg.default_min_size}")
    return cfg.default_min_size