# -*- coding: utf-8 -*-
"""
Модуль: получение биржевых фильтров символа на Bybit (V5).
Использует pybit==5.11.0, читает BYBIT_TESTNET из .env.
В начале кода задаётся SYMBOL (например "BTCUSDT").
При запуске печатает объект фильтров:
- qty_step  : шаг количества
- min_qty   : минимальное количество
- max_qty   : максимальное количество
- tick_size : шаг цены
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Символ указываем здесь
SYMBOL = "BTCUSDT"


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def get_symbol_filters(symbol: str) -> dict:
    """
    Возвращает объект фильтров для символа: {qty_step, min_qty, max_qty, tick_size}.
    """
    load_dotenv()
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    http = HTTP(testnet=testnet, timeout=10_000, recv_window=5_000)

    resp = http.get_instruments_info(category="linear", symbol=symbol)

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    instruments = resp["result"]["list"]
    if not instruments:
        raise RuntimeError("Символ не найден")

    inst = instruments[0]
    lot = inst.get("lotSizeFilter", {})
    price = inst.get("priceFilter", {})

    return {
        "qty_step": lot.get("qtyStep"),
        "min_qty": lot.get("minOrderQty"),
        "max_qty": lot.get("maxOrderQty"),
        "tick_size": price.get("tickSize"),
    }


if __name__ == "__main__":
    try:
        filters = get_symbol_filters(SYMBOL)
        print(filters)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
