from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional


@dataclass
class TradeDecision:
    action: str
    size: Decimal
    leverage: int
    confidence: float
    stop_loss_pct: Optional[Decimal]
    take_profit_pct: Optional[Decimal]
    reasoning: str

    @classmethod
    def from_order_dict(cls, order: Dict[str, Any]) -> "TradeDecision":
        sl_raw = order.get("stop_loss_pct")
        tp_raw = order.get("take_profit_pct")
        sl = Decimal(str(sl_raw)) if sl_raw is not None else None
        tp = Decimal(str(tp_raw)) if tp_raw is not None else None

        return cls(
            action=str(order.get("action", "hold")),
            size=Decimal(str(order.get("size", "0"))),
            leverage=int(order.get("leverage", 1)),
            confidence=float(order.get("confidence", 0.0)),
            stop_loss_pct=sl,
            take_profit_pct=tp,
            reasoning=str(order.get("reasoning", "")),
        )

    def to_order_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "size": self.size,
            "leverage": self.leverage,
            "confidence": self.confidence,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "reasoning": self.reasoning,
        }


@dataclass
class TradeExecutionOutcome:
    raw_result: Dict[str, Any]
    executed_price: Decimal
    executed_size: Decimal
    fill_status: str

    @property
    def success(self) -> bool:
        return bool(self.raw_result.get("success", False))

    @property
    def reason(self) -> str:
        return str(self.raw_result.get("reason", ""))

    @property
    def notional(self) -> Decimal:
        return Decimal(str(self.raw_result.get("notional", "0")))