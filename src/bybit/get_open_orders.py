# -*- coding: utf-8 -*-
"""
Модуль: получение списка всех открытых ордеров по символу (Bybit V5).
Работает для линейных контрактов (category="linear").
Читает ключи из .env.
В начале указываем SYMBOL.
При запуске печатает список ордеров (или пустой список).
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Символ
SYMBOL = "BTCUSDT"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def get_open_orders(symbol: str) -> list[dict]:
    """
    Возвращает список открытых ордеров (включая условные).
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Нет ключей BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    resp = http.get_open_orders(category="linear", symbol=symbol)

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    return resp["result"]["list"] or []

if __name__ == "__main__":
    try:
        orders = get_open_orders(SYMBOL)
        print(orders)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
