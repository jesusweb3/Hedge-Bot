from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

from .state import InstrumentStatus, ManagedOrder


@dataclass(slots=True)
class InstrumentEvent:
    symbol: str
    timestamp: datetime


@dataclass(slots=True)
class StatusEvent(InstrumentEvent):
    status: InstrumentStatus
    details: str | None = None


@dataclass(slots=True)
class LogEvent(InstrumentEvent):
    level: str
    message: str


@dataclass(slots=True)
class OrdersEvent(InstrumentEvent):
    orders: List[ManagedOrder]