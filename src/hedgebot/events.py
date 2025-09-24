# src/hedgebot/events.py
"""
Система событий для передачи данных между торговым движком и UI.
Определяет базовые и специализированные события для статусов, логирования и ордеров.
Все события содержат временные метки и привязаны к конкретному торговому символу.
Используются для асинхронной коммуникации через очереди событий.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

from .state import InstrumentStatus, ManagedOrder


@dataclass(slots=True)
class InstrumentEvent:
    """Базовое событие, привязанное к торговому инструменту."""

    symbol: str  # Торговый символ (например, BTCUSDT)
    timestamp: datetime  # Время возникновения события


@dataclass(slots=True)
class StatusEvent(InstrumentEvent):
    """Событие изменения статуса торгового инструмента."""

    status: InstrumentStatus  # Новый статус инструмента
    details: str | None = None  # Дополнительная информация о статусе


@dataclass(slots=True)
class LogEvent(InstrumentEvent):
    """Событие записи в лог торгового инструмента."""

    level: str  # Уровень логирования (info, warning, error, debug)
    message: str  # Текст сообщения для логирования


@dataclass(slots=True)
class OrdersEvent(InstrumentEvent):
    """Событие обновления списка ордеров торгового инструмента."""

    orders: List[ManagedOrder]  # Актуальный список всех ордеров