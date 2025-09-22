"""Domain models for Hedg-Bot."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, validator


class OrderSide(str, Enum):
    """Represents the order side."""

    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    """Supported order types."""

    ENTRY = "ENTRY"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    DCA = "DCA"


class OrderStatus(str, Enum):
    """High-level order status."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class LogLevel(str, Enum):
    """Log severity."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class TakeProfitLevel(BaseModel):
    """Take-profit description."""

    label: str = Field(..., description="Human readable name (TP1/TP2).")
    offset_percent: float = Field(
        ..., gt=0, description="Distance from the entry in percent.")
    volume_percent: float = Field(
        ..., gt=0, le=100, description="Portion of the initial volume to close.")


class StopLossLevel(BaseModel):
    """Stop-loss configuration."""

    offset_percent: float = Field(
        ..., gt=0, description="Distance from the entry in percent.")
    volume_percent: float = Field(
        ..., gt=0, le=100, description="Portion of the initial volume to close.")


class TP1DcaSettings(BaseModel):
    """Settings for DCA order created after TP1."""

    enabled: bool = False
    offset_percent: Optional[float] = Field(
        None,
        gt=0,
        description="Distance from TP1 fill price for the limit order.",
    )
    quantity: Optional[float] = Field(
        None,
        gt=0,
        description="Absolute size of the DCA order in contracts.",
    )

    @validator("offset_percent", always=True)
    def _validate_offset(cls, value, values):  # type: ignore[override]
        enabled = values.get("enabled")
        if enabled and value is None:
            raise ValueError("Offset percent must be set when DCA is enabled")
        return value

    @validator("quantity", always=True)
    def _validate_quantity(cls, value, values):  # type: ignore[override]
        enabled = values.get("enabled")
        if enabled and value is None:
            raise ValueError("Quantity must be set when DCA is enabled")
        return value


class InstrumentConfig(BaseModel):
    """Complete instrument configuration."""

    symbol: str
    entry_amount: float = Field(..., gt=0, description="Entry size per side in USDT")
    take_profits: List[TakeProfitLevel] = Field(..., min_items=2, max_items=2)
    stop_losses: List[StopLossLevel] = Field(default_factory=list, max_items=10)
    tp1_dca: TP1DcaSettings = Field(default_factory=TP1DcaSettings)

    @validator("take_profits")
    def _validate_tp_labels(cls, value: List[TakeProfitLevel]) -> List[TakeProfitLevel]:
        labels = [level.label for level in value]
        if labels != ["TP1", "TP2"]:
            raise ValueError("Two take-profit levels TP1 and TP2 must be provided")
        return value


class Order(BaseModel):
    """Simplified order representation."""

    id: str
    type: OrderType
    side: OrderSide
    price: Optional[float]
    quantity: float
    status: OrderStatus = OrderStatus.PENDING


class LogEntry(BaseModel):
    """Structured log entry."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
    level: LogLevel = LogLevel.INFO
    message: str


class InstrumentState(BaseModel):
    """Runtime state for a particular instrument."""

    symbol: str
    is_running: bool
    positions: dict[OrderSide, float]
    open_orders: List[Order]
    dca_orders: List[Order]
    logs: List[LogEntry]
    config: InstrumentConfig


class ManagerState(BaseModel):
    """Snapshot of the entire bot fleet."""

    instruments: List[InstrumentState]
