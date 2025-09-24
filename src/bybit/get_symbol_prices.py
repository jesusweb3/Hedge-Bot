# -*- coding: utf-8 -*-
"""
Модуль: получение текущих цен символа (last/mark/index) на Bybit (V5).
Работает с фьючерсным рынком (category="linear").
Читает BYBIT_TESTNET из .env.
В начале кода задаётся SYMBOL (например "BTCUSDT").
При запуске печатает объект с ценами.
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Символ указываем здесь
SYMBOL = "BTCUSDT"


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def get_symbol_prices(symbol: str) -> dict:
    """
    Возвращает словарь с ценами {last, mark, index}.
    """
    load_dotenv()
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    http = HTTP(testnet=testnet, timeout=10_000, recv_window=5_000)

    resp = http.get_tickers(category="linear", symbol=symbol)

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    tickers = resp["result"]["list"]
    if not tickers:
        raise RuntimeError("Символ не найден")

    t = tickers[0]
    return {
        "last": float(t["lastPrice"]),
        "mark": float(t["markPrice"]),
        "index": float(t["indexPrice"]),
    }


if __name__ == "__main__":
    try:
        prices = get_symbol_prices(SYMBOL)
        print(prices)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
