# place_limit_order.py
# -*- coding: utf-8 -*-
"""
Выставление лимитного ордера в режиме хеджирования (Bybit V5).
- Работает на линейных фьючерсах (category="linear").
- Поддерживает хедж-режим с явным указанием стороны позиции.
- Ключи читаются из .env.
- В коде задаём параметры ордера (symbol, side, qty, price, hedge_side).
- Итог: печатает "SUCCESS <orderId>" или "ERROR: ...".
"""

import os
import sys
import uuid
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Параметры ордера
SYMBOL = "BTCUSDT"
SIDE = "Sell"  # "Buy" или "Sell"
QTY = "0.001"  # количество
PRICE = "113800"  # лимитная цена
HEDGE_SIDE = "short"  # "long" или "short" - сторона хедж-позиции
TIME_IN_FORCE = "GTC"  # "GTC", "IOC", "FOK"


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_position_idx(hedge_side: str) -> int:
    """
    Преобразует строковое обозначение стороны хеджа в positionIdx.
    long -> 1, short -> 2
    """
    hedge_side_lower = hedge_side.lower().strip()
    if hedge_side_lower == "long":
        return 1
    elif hedge_side_lower == "short":
        return 2
    else:
        raise ValueError(f"Неверная сторона хеджа: {hedge_side}. Допустимы: 'long', 'short'")


def place_limit_order(symbol: str, side: str, qty: str, price: str,
                      hedge_side: str, time_in_force: str = "GTC") -> str:
    """
    Создаёт лимитный ордер в режиме хеджирования.

    Args:
        symbol: Торговая пара (например, "BTCUSDT")
        side: Направление ордера ("Buy" или "Sell")
        qty: Количество
        price: Лимитная цена
        hedge_side: Сторона хедж-позиции ("long" или "short")
        time_in_force: Время жизни ордера ("GTC", "IOC", "FOK")

    Returns:
        orderId при успехе

    Raises:
        RuntimeError: При ошибке API или отсутствии ключей
        ValueError: При неверных параметрах
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Нет ключей BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    position_idx = _get_position_idx(hedge_side)

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    resp = http.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Limit",
        qty=qty,
        price=price,
        positionIdx=position_idx,
        timeInForce=time_in_force,
        orderLinkId=f"limit-{uuid.uuid4().hex[:10]}"
    )

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    return resp["result"]["orderId"]


if __name__ == "__main__":
    try:
        oid = place_limit_order(SYMBOL, SIDE, QTY, PRICE, HEDGE_SIDE, TIME_IN_FORCE)
        print(f"SUCCESS {oid}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)