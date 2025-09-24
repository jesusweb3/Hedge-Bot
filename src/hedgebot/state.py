# src/hedgebot/state.py
"""
Определения состояний и структур данных для торговой системы.
Включает перечисления статусов инструментов и типов ордеров,
а также класс для управления ордерами с временными метками и сериализацией.
Все временные метки используют UTC для обеспечения совместимости.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
from typing import Optional


class InstrumentStatus(str, Enum):
    """Статусы торгового инструмента в жизненном цикле торговли."""

    CONFIGURED = "configured"  # Настроен, готов к запуску
    WAITING_ENTRY = "waiting_entry"  # Ожидает срабатывания входных ордеров
    ACTIVE = "active"  # Активно торгует с защитными ордерами
    STOPPED = "stopped"  # Остановлен пользователем
    COMPLETED = "completed"  # Торговля завершена (TP достигнут)
    ERROR = "error"  # Ошибка в процессе торговли


class OrderKind(str, Enum):
    """Типы ордеров в системе хедж-торговли."""

    ENTRY = "entry"  # Входной условный ордер
    TAKE_PROFIT = "take_profit"  # Обычный тейк-профит
    FINAL_TAKE_PROFIT = "final_take_profit"  # Финальный TP (закрывает всё)
    STOP_LOSS = "stop_loss"  # Стоп-лосс ордер
    REFILL = "refill"  # Ордер доливки позиции


@dataclass(slots=True)
class ManagedOrder:
    """Управляемый ордер с полной информацией и временными метками."""

    # Основная информация об ордере
    order_id: str  # ID ордера на бирже
    symbol: str  # Торговый символ
    side: str  # Направление (Buy/Sell)
    position_side: str  # Сторона позиции (long/short)
    kind: OrderKind  # Тип ордера в системе
    quantity: float  # Количество

    # Цены (опциональные в зависимости от типа ордера)
    price: Optional[float] = None  # Лимитная цена
    trigger_price: Optional[float] = None  # Цена срабатывания триггера

    # Дополнительные атрибуты
    level: Optional[int] = None  # Уровень TP/SL (1, 2, 3...)
    status: str = "New"  # Статус на бирже
    reduce_only: bool = True  # Только сокращение позиции

    # Временные метки (автоматически устанавливаются в UTC)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def as_dict(self) -> dict:
        """Преобразует ордер в словарь для сериализации."""
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
        """Обновляет статус ордера и временную метку."""
        self.status = status
        self.updated_at = datetime.now(UTC)