from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from exchange.market_rules import default_tick_size_for_asset, infer_tick_size_and_precision_from_mid
from utils.decimals import safe_decimal


class ExchangeMarketDataService:
    """Provides metadata/mids/open-orders access and market rule helpers."""

    def __init__(self, api_client):
        self.api_client = api_client

    def get_meta(self, force_refresh: bool, fetcher) -> Optional[Dict[str, Any]]:
        return self.api_client.get_meta(force_refresh=force_refresh, fetcher=fetcher)

    def get_all_mids(self, force_refresh: bool, fetcher) -> Optional[Dict[str, str]]:
        return self.api_client.get_all_mids(force_refresh=force_refresh, fetcher=fetcher)

    def get_user_state(self, user: str, fetcher) -> Optional[Dict[str, Any]]:
        return self.api_client.get_user_state(user=user, fetcher=fetcher)

    def get_open_orders(self, user: str, force_refresh: bool, fetcher) -> List[Dict[str, Any]]:
        return self.api_client.get_open_orders(user=user, force_refresh=force_refresh, fetcher=fetcher)

    def get_asset_id(self, coin: str, meta: Optional[Dict[str, Any]]) -> Optional[int]:
        if meta is None:
            return None
        for index, asset in enumerate(meta.get("universe", [])):
            if asset.get("name") == coin:
                return index
        return None

    def get_max_leverage(self, coin: str, meta: Optional[Dict[str, Any]]) -> int:
        if meta is None:
            return 10
        for asset in meta.get("universe", []):
            if asset.get("name") == coin:
                return int(asset.get("maxLeverage", 10))
        return 10

    def get_sz_decimals(self, coin: str, meta: Optional[Dict[str, Any]]) -> Optional[int]:
        if meta is None:
            return None
        for asset in meta.get("universe", []):
            if asset.get("name") == coin:
                return asset.get("szDecimals")
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
        if meta is None:
            return Decimal("0.01"), 2

        universe = meta.get("universe", [])
        if not (0 <= asset_id < len(universe)):
            return Decimal("0.01"), 2

        coin = universe[asset_id].get("name", "")
        if mids is not None and coin in mids:
            return infer_tick_size_and_precision_from_mid(str(mids.get(coin, "0")))
        return default_tick_size_for_asset(asset_id)