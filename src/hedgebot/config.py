# src/hedgebot/config.py
"""
Конфигурационные классы для настройки торговых инструментов.
Определяет структуры данных для тейк-профитов, стоп-лоссов, доливок и общих настроек.
Включает валидацию параметров и методы клонирования для безопасной работы с настройками.
Все классы используют slots для оптимизации памяти и производительности.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class TakeProfitLevel:
    """Настройки одного уровня тейк-профита."""

    offset_percent: float    # Смещение от цены входа в процентах
    quantity_percent: float  # Процент от позиции для закрытия

    def clamp(self) -> "TakeProfitLevel":
        """Возвращает копию с приведенными к float значениями."""
        return TakeProfitLevel(
            offset_percent=float(self.offset_percent),
            quantity_percent=float(self.quantity_percent),
        )


@dataclass(slots=True)
class StopLossLevel:
    """Настройки одного уровня стоп-лосса."""

    offset_percent: float    # Смещение от цены входа в процентах
    quantity_percent: float  # Процент от позиции для закрытия

    def clamp(self) -> "StopLossLevel":
        """Возвращает копию с приведенными к float значениями."""
        return StopLossLevel(
            offset_percent=float(self.offset_percent),
            quantity_percent=float(self.quantity_percent),
        )


@dataclass(slots=True)
class RefillConfig:
    """Настройки системы доливок позиции."""

    enabled_after_tp1: bool = False      # Включить доливку после первого TP
    price_offset_percent: float = 0.0    # Смещение цены доливки от входа в %
    quantity_percent: float = 0.0        # Размер доливки в % от базового объёма

    def clamp(self) -> "RefillConfig":
        """Возвращает копию с приведенными к правильным типам значениями."""
        return RefillConfig(
            enabled_after_tp1=bool(self.enabled_after_tp1),
            price_offset_percent=float(self.price_offset_percent),
            quantity_percent=float(self.quantity_percent),
        )


@dataclass(slots=True)
class InstrumentSettings:
    """Полный набор пользовательских настроек для торгового инструмента."""

    symbol: str                                    # Торговая пара (например, BTCUSDT)
    base_quantity: float                           # Базовый объём позиции
    entry_trigger_price: float                     # Цена срабатывания входа
    entry_trigger_direction: int = 2               # Направление триггера (1=выше, 2=ниже)
    trigger_by: str = "LastPrice"                  # Тип цены для триггера
    take_profits: List[TakeProfitLevel] = field(default_factory=list)  # Список тейк-профитов (всегда 2)
    stop_losses: List[StopLossLevel] = field(default_factory=list)     # Список стоп-лоссов (до 10)
    refill: RefillConfig = field(default_factory=RefillConfig)         # Настройки доливок

    def clamp(self) -> "InstrumentSettings":
        """Возвращает копию настроек с приведенными к правильным типам значениями."""
        return InstrumentSettings(
            symbol=self.symbol.strip().upper(),
            base_quantity=float(self.base_quantity),
            entry_trigger_price=float(self.entry_trigger_price),
            entry_trigger_direction=int(self.entry_trigger_direction),
            trigger_by=self.trigger_by,
            take_profits=[tp.clamp() for tp in self.take_profits],
            stop_losses=[sl.clamp() for sl in self.stop_losses],
            refill=self.refill.clamp(),
        )

    def validate(self) -> None:
        """Валидирует корректность всех настроек."""
        if not self.symbol:
            raise ValueError("Символ не может быть пустым")
        if self.base_quantity <= 0:
            raise ValueError("Базовый объём должен быть больше нуля")
        if self.entry_trigger_price <= 0:
            raise ValueError("Цена входа должна быть больше нуля")
        if self.entry_trigger_direction not in {1, 2}:
            raise ValueError("Направление триггера может быть только 1 или 2")
        if len(self.take_profits) != 2:
            raise ValueError("Должно быть настроено два тейк-профита")
        if any(tp.offset_percent <= 0 for tp in self.take_profits):
            raise ValueError("Процент смещения TP должен быть положительным")
        if abs(sum(tp.quantity_percent for tp in self.take_profits) - 100.0) > 1e-6:
            raise ValueError("Сумма процентов объёма для TP должна быть равна 100")
        if not self.stop_losses:
            raise ValueError("Нужно настроить хотя бы один стоп-лосс")
        if len(self.stop_losses) > 10:
            raise ValueError("Количество стоп-лоссов не может превышать 10")
        if any(sl.offset_percent <= 0 for sl in self.stop_losses):
            raise ValueError("Процент смещения SL должен быть положительным")
        if any(sl.quantity_percent <= 0 for sl in self.stop_losses):
            raise ValueError("Процент объёма SL должен быть положительным")

    @property
    def stop_losses_sorted(self) -> List[StopLossLevel]:
        """Возвращает стоп-лоссы, отсортированные по проценту смещения."""
        return sorted(self.stop_losses, key=lambda sl: sl.offset_percent)

    def clone(self) -> "InstrumentSettings":
        """Создаёт глубокую копию настроек для безопасного использования."""
        return InstrumentSettings(
            symbol=self.symbol,
            base_quantity=self.base_quantity,
            entry_trigger_price=self.entry_trigger_price,
            entry_trigger_direction=self.entry_trigger_direction,
            trigger_by=self.trigger_by,
            take_profits=[tp.clamp() for tp in self.take_profits],
            stop_losses=[sl.clamp() for sl in self.stop_losses],
            refill=self.refill.clamp(),
        )