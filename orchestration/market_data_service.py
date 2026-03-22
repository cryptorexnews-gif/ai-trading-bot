import time

from models import MarketData


def build_market_data(coin: str, technical_data) -> MarketData:
    return MarketData(
        coin=coin,
        last_price=technical_data["current_price"],
        change_24h=technical_data["change_24h"],
        volume_24h=technical_data["volume_24h"],
        funding_rate=technical_data["funding_rate"],
        timestamp=time.time(),
    )