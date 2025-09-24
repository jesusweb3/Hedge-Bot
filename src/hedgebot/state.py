from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class InstrumentStatus(str, Enum):
    CONFIGURED = "configured"
    WAITING_ENTRY = "waiting_entry"
    ACTIVE = "active"
    STOPPED = "stopped"
    COMPLETED = "completed"
    ERROR = "error"


class OrderKind(str, Enum):
    ENTRY = "entry"
    TAKE_PROFIT = "take_profit"
    FINAL_TAKE_PROFIT = "final_take_profit"
    STOP_LOSS = "stop_loss"
    REFILL = "refill"


@dataclass(slots=True)
class ManagedOrder:
    order_id: str
    symbol: str
    side: str
    position_side: str
    kind: OrderKind
    quantity: float
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    level: Optional[int] = None
    status: str = "New"
    reduce_only: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "position_side": self.position_side,
            "kind": self.kind.value,
            "quantity": self.quantity,
            "price": self.price,
            "trigger_price": self.trigger_price,
            "level": self.level,
            "status": self.status,
            "reduce_only": self.reduce_only,
            "updated_at": self.updated_at.isoformat(timespec="seconds"),
        }

    def mark_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.utcnow()
