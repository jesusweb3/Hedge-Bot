"""Runtime state tracking for instruments managed by Hedge-Bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class InstrumentStatus(str, Enum):
    """High level lifecycle status for an instrument."""

    IDLE = "idle"
    WAITING_ENTRY = "waiting_entry"
    POSITION_OPEN = "position_open"
    STOPPED = "stopped"
    ERROR = "error"


class OrderType(str, Enum):
    """Different types of orders that compose the hedging strategy."""

    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    REFILL = "refill"


@dataclass(slots=True)
class OrderInfo:
    """Minimal order representation tracked by the bot."""

    order_id: str
    order_type: OrderType
    side: str
    position_side: str
    qty: float
    price: float | None
    tag: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None


@dataclass(slots=True)
class InstrumentState:
    """Mutable state of a managed instrument."""

    status: InstrumentStatus = InstrumentStatus.IDLE
    orders: Dict[str, OrderInfo] = field(default_factory=dict)
    long_position_size: float = 0.0
    short_position_size: float = 0.0
    last_error: Optional[str] = None
    activity_log: List[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        timestamp = datetime.utcnow().isoformat(timespec="seconds")
        entry = f"[{timestamp}] {message}"
        self.activity_log.append(entry)
        if len(self.activity_log) > 500:
            self.activity_log = self.activity_log[-500:]

    def add_order(self, info: OrderInfo) -> None:
        self.orders[info.order_id] = info

    def mark_order_filled(self, order_id: str) -> None:
        order = self.orders.get(order_id)
        if order:
            order.filled_at = datetime.utcnow()

    def remove_order(self, order_id: str) -> None:
        self.orders.pop(order_id, None)
