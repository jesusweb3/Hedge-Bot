# src/hedgebot/utils.py
"""
Утилиты для работы с числовыми значениями и биржевыми фильтрами.
Предоставляет функции для точного округления цен и количеств согласно требованиям биржи,
форматирования Decimal значений и обеспечения минимальных значений.
Использует высокую точность вычислений для предотвращения ошибок округления.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, getcontext

getcontext().prec = 18


def round_to_step(value: float, step: float, rounding=ROUND_DOWN) -> Decimal:
    """
    Округляет значение до ближайшего шага с заданным правилом округления.

    Args:
        value: Исходное значение для округления
        step: Шаг округления (например, 0.01 для цен или 0.001 для количества)
        rounding: Правило округления из модуля decimal

    Returns:
        Округленное значение типа Decimal
    """
    value_dec = Decimal(str(value))
    step_dec = Decimal(str(step))
    if step_dec == 0:
        return value_dec
    quant = (value_dec / step_dec).to_integral_value(rounding=rounding)
    return quant * step_dec


def format_decimal(value: Decimal | float) -> str:
    """
    Форматирует Decimal или float в строку без экспоненциальной записи.

    Args:
        value: Значение для форматирования

    Returns:
        Строковое представление числа в обычной записи
    """
    dec = Decimal(value) if not isinstance(value, Decimal) else value
    return format(dec.normalize(), 'f') if dec else "0"


def clamp_to_step_str(value: float, step: float, rounding=ROUND_DOWN) -> str:
    """
    Округляет значение до шага и возвращает как отформатированную строку.

    Args:
        value: Исходное значение
        step: Шаг округления
        rounding: Правило округления

    Returns:
        Отформатированная строка с округленным значением
    """
    return format_decimal(round_to_step(value, step, rounding))


def ensure_minimum(value: float, minimum: float) -> float:
    """
    Обеспечивает минимальное значение параметра.

    Args:
        value: Проверяемое значение
        minimum: Минимально допустимое значение

    Returns:
        Максимальное из двух значений
    """
    return max(value, minimum)