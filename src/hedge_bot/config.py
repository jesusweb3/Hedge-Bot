"""Data models describing user configurable parameters for Hedge-Bot."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List


@dataclass(slots=True)
class TakeProfitConfig:
    """Configuration for a single take-profit tier."""

    price: Decimal
    quantity_pct: Decimal

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError("Take profit price must be positive")
        if not (Decimal("0") < self.quantity_pct <= Decimal("100")):
            raise ValueError("Take profit quantity percent must be in (0, 100]")


@dataclass(slots=True)
class StopLossConfig:
    """Configuration for a single stop-loss tier."""

    trigger_price: Decimal
    quantity_pct: Decimal

    def __post_init__(self) -> None:
        if self.trigger_price <= 0:
            raise ValueError("Stop loss trigger price must be positive")
        if not (Decimal("0") < self.quantity_pct <= Decimal("100")):
            raise ValueError("Stop loss quantity percent must be in (0, 100]")


@dataclass(slots=True)
class RefillConfig:
    """Configuration for averaging orders placed after partial exits."""

    enabled: bool = False
    price: Decimal | None = None
    quantity: Decimal | None = None

    def __post_init__(self) -> None:
        if self.enabled:
            if self.price is None or self.price <= 0:
                raise ValueError("Refill price must be positive when enabled")
            if self.quantity is None or self.quantity <= 0:
                raise ValueError("Refill quantity must be positive when enabled")


@dataclass(slots=True)
class SideConfig:
    """Settings that are specific to a single side (long/short)."""

    take_profits: List[TakeProfitConfig] = field(default_factory=list)
    stop_losses: List[StopLossConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.take_profits) != 2:
            raise ValueError("Exactly two take profit levels must be configured")
        total_tp_pct = sum(tp.quantity_pct for tp in self.take_profits)
        if total_tp_pct > Decimal("100") + Decimal("0.0001"):
            raise ValueError("Total take profit allocation cannot exceed 100%")
        if len(self.stop_losses) > 10:
            raise ValueError("At most 10 stop loss levels are supported")
        total_sl_pct = sum(sl.quantity_pct for sl in self.stop_losses)
        if total_sl_pct > Decimal("100") + Decimal("0.0001"):
            raise ValueError("Total stop loss allocation cannot exceed 100%")


@dataclass(slots=True)
class InstrumentConfig:
    """Full configuration required to trade a single instrument."""

    symbol: str
    entry_trigger_price: Decimal
    entry_quantity_usdt: Decimal
    trigger_by: str = "LastPrice"
    long: SideConfig = field(default_factory=SideConfig)
    short: SideConfig = field(default_factory=SideConfig)
    refill_after_tp1: RefillConfig = field(default_factory=RefillConfig)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper().strip()
        if not self.symbol:
            raise ValueError("Symbol must be provided")
        if self.entry_trigger_price <= 0:
            raise ValueError("Entry trigger price must be positive")
        if self.entry_quantity_usdt <= 0:
            raise ValueError("Entry quantity must be positive")
        trigger_by_allowed = {"LastPrice", "MarkPrice", "IndexPrice"}
        if self.trigger_by not in trigger_by_allowed:
            raise ValueError(f"trigger_by must be one of {trigger_by_allowed}")
