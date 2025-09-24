# -*- coding: utf-8 -*-
"""
Модуль: получение всех открытых позиций по символу (Bybit V5).
Работает с фьючерсами (category="linear").
Читает ключи из .env.
В начале задаётся SYMBOL (например "BTCUSDT").
При запуске печатает список позиций.
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Символ для проверки
SYMBOL = "BTCUSDT"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def get_open_positions(symbol: str) -> list[dict]:
    """
    Возвращает список позиций по символу.
    Каждая позиция — dict с данными Bybit (size, side, entryPrice и т.д.).
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Нет BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    resp = http.get_positions(category="linear", symbol=symbol)

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    positions = resp["result"]["list"] or []
    # фильтруем только открытые (size != "0")
    open_positions = [p for p in positions if float(p.get("size", "0")) != 0]
    return open_positions

if __name__ == "__main__":
    try:
        pos = get_open_positions(SYMBOL)
        print(pos)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
