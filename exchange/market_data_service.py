import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from exchange.market_rules import (
    default_tick_size_for_asset,
    get_tick_size_for_known_coin,
    infer_tick_size_from_price,
    infer_tick_size_and_precision_from_mid,
)
from utils.decimals import safe_decimal

logger = logging.getLogger(__name__)


class ExchangeMarketDataService:
    """Provides metadata/mids/open-orders access and market rule helpers."""

    def __init__(self, api_client):
        self.api_client = api_client

    @staticmethod
    def _normalize_meta(meta: Optional[Any]) -> Optional[Dict[str, Any]]:
        if isinstance(meta, dict):
            return meta
        if isinstance(meta, list) and meta and isinstance(meta[0], dict) and "universe" in meta[0]:
            return meta[0]
        return None

    @staticmethod
    def _get_universe(meta: Optional[Any]) -> List[Dict[str, Any]]:
        normalized = ExchangeMarketDataService._normalize_meta(meta)
        if not normalized:
            return []
        universe = normalized.get("universe", [])
        return universe if isinstance(universe, list) else []

    @staticmethod
    def _asset_int(asset: Dict[str, Any], keys: List[str]) -> Optional[int]:
        for key in keys:
            if key not in asset:
                continue
            raw = asset.get(key)
            if raw is None:
                continue
            try:
                return int(str(raw))
            except (TypeError, ValueError):
                continue
        return None

    def get_meta(self, force_refresh: bool, fetcher) -> Optional[Dict[str, Any]]:
        return self.api_client.get_meta(force_refresh=force_refresh, fetcher=fetcher)

    def get_all_mids(self, force_refresh: bool, fetcher) -> Optional[Dict[str, str]]:
        return self.api_client.get_all_mids(force_refresh=force_refresh, fetcher=fetcher)

    def get_user_state(self, user: str, fetcher) -> Optional[Dict[str, Any]]:
        return self.api_client.get_user_state(user=user, fetcher=fetcher)

    def get_open_orders(self, user: str, force_refresh: bool, fetcher) -> List[Dict[str, Any]]:
        return self.api_client.get_open_orders(user=user, force_refresh=force_refresh, fetcher=fetcher)

    def get_asset_id(self, coin: str, meta: Optional[Dict[str, Any]]) -> Optional[int]:
        universe = self._get_universe(meta)
        for index, asset in enumerate(universe):
            if str(asset.get("name", "")).strip().upper() == str(coin).strip().upper():
                return index
        return None

    def get_max_leverage(self, coin: str, meta: Optional[Dict[str, Any]]) -> int:
        universe = self._get_universe(meta)
        for asset in universe:
            if str(asset.get("name", "")).strip().upper() == str(coin).strip().upper():
                max_lev = self._asset_int(asset, ["maxLeverage", "max_leverage"])
                return max_lev if max_lev is not None else 10
        return 10

    def get_sz_decimals(self, coin: str, meta: Optional[Dict[str, Any]]) -> Optional[int]:
        universe = self._get_universe(meta)
        for asset in universe:
            if str(asset.get("name", "")).strip().upper() == str(coin).strip().upper():
                return self._asset_int(asset, ["szDecimals", "sizeDecimals", "qtyDecimals"])
        return None

    def get_reference_price(self, coin: str, fallback_price: Decimal, mids: Optional[Dict[str, str]]) -> Decimal:
        if mids and coin in mids:
            mid_price = safe_decimal(mids[coin], Decimal("0"))
            if mid_price > 0:
                return mid_price
        return fallback_price

    def get_tick_size_and_precision(
        self,
        asset_id: int,
        meta: Optional[Dict[str, Any]],
        mids: Optional[Dict[str, str]],
    ) -> Tuple[Decimal, int]:
        universe = self._get_universe(meta)
        if not universe:
            return Decimal("0.01"), 2

        if not (0 <= asset_id < len(universe)):
            return Decimal("0.01"), 2

        asset = universe[asset_id]
        coin = str(asset.get("name", "")).strip().upper()

        # Priority 1: pxDecimals from Hyperliquid metadata (if present)
        px_decimals = self._asset_int(asset, ["pxDecimals", "priceDecimals", "pricePrecision"])
        if px_decimals is not None and px_decimals >= 0:
            tick_size = Decimal("1").scaleb(-px_decimals) if px_decimals > 0 else Decimal("1")
            return tick_size, px_decimals

        # Priority 2: Known tick sizes table (verified against exchange)
        known = get_tick_size_for_known_coin(coin)
        if known is not None:
            tick_size, precision = known
            logger.debug(f"{coin} tick size from known table: tick={tick_size}, precision={precision}")
            return tick_size, precision

        # Priority 3: Infer from current mid price using 5 significant figures rule
        if mids is not None and coin in mids:
            mid_str = str(mids.get(coin, "0"))
            try:
                mid_price = Decimal(mid_str)
            except Exception:
                mid_price = Decimal("0")

            if mid_price > 0:
                tick_size, precision = infer_tick_size_from_price(mid_price, max_sig_figs=5)
                logger.info(
                    f"{coin} tick size inferred from mid price ${mid_price}: "
                    f"tick={tick_size}, precision={precision} (5 sig figs rule)"
                )
                return tick_size, precision

        # Priority 4: Last-resort fallback by asset_id
        tick_size, precision = default_tick_size_for_asset(asset_id)
        logger.warning(f"{coin} using last-resort tick size fallback: tick={tick_size}, precision={precision}")
        return tick_size, precision