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


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass
class StopLossConfig:
    """Configurazione stop-loss per una posizione."""
    enabled: bool = True
    percentage: Decimal = Decimal("0.03")  # 3% predefinito
    price: Optional[Decimal] = None  # Livello prezzo assoluto
    trailing: bool = False

    def calculate_stop_price(self, entry_price: Decimal, is_long: bool) -> Decimal:
        if self.price is not None:
            return self.price
        if is_long:
            return entry_price * (Decimal("1") - self.percentage)
        else:
            return entry_price * (Decimal("1") + self.percentage)


@dataclass
class TakeProfitConfig:
    """Configurazione take-profit per una posizione."""
    enabled: bool = True
    percentage: Decimal = Decimal("0.05")  # 5% predefinito
    price: Optional[Decimal] = None  # Livello prezzo assoluto

    def calculate_tp_price(self, entry_price: Decimal, is_long: bool) -> Decimal:
        if self.price is not None:
            return self.price
        if is_long:
            return entry_price * (Decimal("1") + self.percentage)
        else:
            return entry_price * (Decimal("1") - self.percentage)


@dataclass
class TrailingStopConfig:
    """Configurazione trailing stop."""
    enabled: bool = False
    callback_rate: Decimal = Decimal("0.02")  # 2% callback
    activation_price: Optional[Decimal] = None  # Prezzo di attivazione
    highest_price: Optional[Decimal] = None  # Prezzo più alto tracciato (per long)
    lowest_price: Optional[Decimal] = None  # Prezzo più basso tracciato (per short)

    def update_extreme(self, current_price: Decimal, is_long: bool) -> None:
        """Aggiorna il prezzo estremo tracciato."""
        if is_long:
            if self.highest_price is None or current_price > self.highest_price:
                self.highest_price = current_price
        else:
            if self.lowest_price is None or current_price < self.lowest_price:
                self.lowest_price = current_price

    def get_trailing_stop_price(self, is_long: bool) -> Optional[Decimal]:
        """Calcola prezzo corrente trailing stop."""
        if is_long and self.highest_price is not None:
            return self.highest_price * (Decimal("1") - self.callback_rate)
        elif not is_long and self.lowest_price is not None:
            return self.lowest_price * (Decimal("1") + self.callback_rate)
        return None

    def should_trigger(self, current_price: Decimal, is_long: bool) -> bool:
        """Controlla se trailing stop dovrebbe scattare."""
        if not self.enabled:
            return False
        # Controlla soglia attivazione
        if self.activation_price is not None:
            if is_long and current_price < self.activation_price:
                return False
            if not is_long and current_price > self.activation_price:
                return False
        stop_price = self.get_trailing_stop_price(is_long)
        if stop_price is None:
            return False
        if is_long:
            return current_price <= stop_price
        else:
            return current_price >= stop_price


@dataclass
class BreakEvenConfig:
    """Configurazione break-even stop — sposta SL a entry quando in profitto."""
    enabled: bool = True
    activation_pct: Decimal = Decimal("0.015")  # Attiva dopo +1.5% profitto
    offset_pct: Decimal = Decimal("0.001")  # Sposta SL a entry + 0.1% (piccolo profitto garantito)
    activated: bool = False  # Stato: se break-even è già stato attivato

    def should_activate(self, entry_price: Decimal, current_price: Decimal, is_long: bool) -> bool:
        """Controlla se il break-even dovrebbe attivarsi."""
        if not self.enabled or self.activated:
            return False
        if entry_price <= 0:
            return False
        if is_long:
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price
        return pnl_pct >= self.activation_pct

    def get_break_even_price(self, entry_price: Decimal, is_long: bool) -> Decimal:
        """Calcola prezzo break-even (entry + piccolo offset)."""
        if is_long:
            return entry_price * (Decimal("1") + self.offset_pct)
        else:
            return entry_price * (Decimal("1") - self.offset_pct)


@dataclass
class ManagedPosition:
    """Una posizione con gestione rischio attaccata."""
    coin: str
    size: Decimal
    entry_price: Decimal
    is_long: bool
    leverage: int
    stop_loss: StopLossConfig = field(default_factory=StopLossConfig)
    take_profit: TakeProfitConfig = field(default_factory=TakeProfitConfig)
    trailing_stop: TrailingStopConfig = field(default_factory=TrailingStopConfig)
    break_even: BreakEvenConfig = field(default_factory=BreakEvenConfig)
    opened_at: float = 0.0

    def should_stop_loss(self, current_price: Decimal) -> bool:
        if not self.stop_loss.enabled:
            return False
        stop_price = self.stop_loss.calculate_stop_price(self.entry_price, self.is_long)
        if self.is_long:
            return current_price <= stop_price
        else:
            return current_price >= stop_price

    def should_take_profit(self, current_price: Decimal) -> bool:
        if not self.take_profit.enabled:
            return False
        tp_price = self.take_profit.calculate_tp_price(self.entry_price, self.is_long)
        if self.is_long:
            return current_price >= tp_price
        else:
            return current_price <= tp_price

    def should_trailing_stop(self, current_price: Decimal) -> bool:
        if not self.trailing_stop.enabled:
            return False
        self.trailing_stop.update_extreme(current_price, self.is_long)
        return self.trailing_stop.should_trigger(current_price, self.is_long)

    def check_break_even(self, current_price: Decimal) -> bool:
        """
        Check and activate break-even if conditions met.
        Returns True if break-even was just activated (SL moved to entry).
        """
        if not self.break_even.enabled or self.break_even.activated:
            return False
        if self.break_even.should_activate(self.entry_price, current_price, self.is_long):
            be_price = self.break_even.get_break_even_price(self.entry_price, self.is_long)
            self.stop_loss.price = be_price
            self.break_even.activated = True
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "coin": self.coin,
            "size": str(self.size),
            "entry_price": str(self.entry_price),
            "is_long": self.is_long,
            "leverage": self.leverage,
            "opened_at": self.opened_at,
            "stop_loss": {
                "enabled": self.stop_loss.enabled,
                "percentage": str(self.stop_loss.percentage),
                "price": str(self.stop_loss.price) if self.stop_loss.price else None,
            },
            "take_profit": {
                "enabled": self.take_profit.enabled,
                "percentage": str(self.take_profit.percentage),
                "price": str(self.take_profit.price) if self.take_profit.price else None,
            },
            "trailing_stop": {
                "enabled": self.trailing_stop.enabled,
                "callback_rate": str(self.trailing_stop.callback_rate),
                "highest_price": str(self.trailing_stop.highest_price) if self.trailing_stop.highest_price else None,
                "lowest_price": str(self.trailing_stop.lowest_price) if self.trailing_stop.lowest_price else None,
            },
            "break_even": {
                "enabled": self.break_even.enabled,
                "activation_pct": str(self.break_even.activation_pct),
                "offset_pct": str(self.break_even.offset_pct),
                "activated": self.break_even.activated,
            }
        }
        return result

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ManagedPosition":
        sl_data = data.get("stop_loss", {})
        tp_data = data.get("take_profit", {})
        ts_data = data.get("trailing_stop", {})
        be_data = data.get("break_even", {})

        return ManagedPosition(
            coin=data["coin"],
            size=Decimal(str(data["size"])),
            entry_price=Decimal(str(data["entry_price"])),
            is_long=data["is_long"],
            leverage=int(data.get("leverage", 1)),
            opened_at=float(data.get("opened_at", 0)),
            stop_loss=StopLossConfig(
                enabled=sl_data.get("enabled", True),
                percentage=Decimal(str(sl_data.get("percentage", "0.03"))),
                price=Decimal(str(sl_data["price"])) if sl_data.get("price") else None,
            ),
            take_profit=TakeProfitConfig(
                enabled=tp_data.get("enabled", True),
                percentage=Decimal(str(tp_data.get("percentage", "0.05"))),
                price=Decimal(str(tp_data["price"])) if tp_data.get("price") else None,
            ),
            trailing_stop=TrailingStopConfig(
                enabled=ts_data.get("enabled", False),
                callback_rate=Decimal(str(ts_data.get("callback_rate", "0.02"))),
                highest_price=Decimal(str(ts_data["highest_price"])) if ts_data.get("highest_price") else None,
                lowest_price=Decimal(str(ts_data["lowest_price"])) if ts_data.get("lowest_price") else None,
            ),
            break_even=BreakEvenConfig(
                enabled=be_data.get("enabled", True),
                activation_pct=Decimal(str(be_data.get("activation_pct", "0.015"))),
                offset_pct=Decimal(str(be_data.get("offset_pct", "0.001"))),
                activated=be_data.get("activated", False),
            ),
        )


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
        if coin not in self.positions:
            return PositionSide.NONE
        size = Decimal(str(self.positions[coin].get("size", 0)))
        if size > 0:
            return PositionSide.LONG
        elif size < 0:
            return PositionSide.SHORT
        return PositionSide.NONE

    def get_total_exposure(self) -> Decimal:
        total = Decimal("0")
        for coin, pos in self.positions.items():
            size = abs(Decimal(str(pos.get("size", 0))))
            entry = Decimal(str(pos.get("entry_price", 0)))
            total += size * entry
        return total

    def get_total_unrealized_pnl(self) -> Decimal:
        total = Decimal("0")
        for coin, pos in self.positions.items():
            total += Decimal(str(pos.get("unrealized_pnl", 0)))
        return total


@dataclass
class TradeRecord:
    """Record di un trade eseguito per tracking storia."""
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
    mode: str  # 'paper' o 'live'
    trigger: str = ""  # 'ai', 'stop_loss', 'take_profit', 'trailing_stop', 'emergency', 'break_even'
    order_status: str = "unknown"  # filled, partially_filled, etc.


@dataclass
class AssetCorrelation:
    """Dati correlazione tra asset."""
    coin_a: str
    coin_b: str
    correlation: Decimal  # -1 a 1
    period: str  # es. "4h", "1d"
    sample_count: int = 0


@dataclass
class TrendSignal:
    """Segnale trend per strategia 4h/1d."""
    coin: str
    primary_trend: str  # "bullish", "bearish", "neutral"
    secondary_trend: str  # "bullish", "bearish", "neutral"
    entry_trend: str  # "bullish", "bearish", "neutral"
    trend_strength: int  # 0-3 (numero di timeframes allineati)
    volume_confirmation: bool
    rsi_signal: str  # "oversold", "overbought", "neutral"
    bb_position: Decimal  # 0-1 (posizione nelle bande)
    vwap_distance: Decimal  # % sopra/sotto VWAP
    confidence_score: Decimal  # 0-1
    entry_price: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    timestamp: float = 0.0