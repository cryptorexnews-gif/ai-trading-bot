from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class TradingAction(Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE_POSITION = "close_position"
    INCREASE_POSITION = "increase_position"
    REDUCE_POSITION = "reduce_position"
    CHANGE_LEVERAGE = "change_leverage"


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


@dataclass
class MarketData:
    coin: str
    last_price: Decimal
    change_24h: Decimal
    volume_24h: Decimal
    funding_rate: Decimal
    timestamp: float


@dataclass
class PortfolioState:
    total_balance: Decimal
    available_balance: Decimal
    margin_usage: Decimal
    positions: Dict[str, Dict[str, Any]]

    def get_position_side(self, coin: str) -> PositionSide:
        """Get the side of an existing position."""
        if coin not in self.positions:
            return PositionSide.NONE
        size = Decimal(str(self.positions[coin].get("size", 0)))
        if size > 0:
            return PositionSide.LONG
        elif size < 0:
            return PositionSide.SHORT
        return PositionSide.NONE

    def get_total_exposure(self) -> Decimal:
        """Get total notional exposure across all positions."""
        total = Decimal("0")
        for coin, pos in self.positions.items():
            size = abs(Decimal(str(pos.get("size", 0))))
            entry = Decimal(str(pos.get("entry_price", 0)))
            total += size * entry
        return total

    def get_total_unrealized_pnl(self) -> Decimal:
        """Get total unrealized PnL across all positions."""
        total = Decimal("0")
        for coin, pos in self.positions.items():
            total += Decimal(str(pos.get("unrealized_pnl", 0)))
        return total


@dataclass
class TradeRecord:
    """Record of an executed trade for history tracking."""
    timestamp: float
    coin: str
    action: str
    side: str
    size: str
    price: str
    notional: str
    leverage: int
    confidence: float
    reasoning: str
    success: bool
    mode: str  # 'paper' or 'live'