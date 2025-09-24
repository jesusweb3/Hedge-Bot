# -*- coding: utf-8 -*-
"""
Модуль: получение позиции конкретной стороны (лонг/шорт) в хедж-режиме Bybit V5.
Работает с линейными контрактами (category="linear").
Читает ключи из .env.
В начале задаём SYMBOL и SIDE ("long" или "short").
При запуске печатает словарь позиции или "нет позиции".
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Настройки
SYMBOL = "BTCUSDT"
SIDE = "short"   # варианты: "long" или "short"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def get_position_side_for_hedg(symbol: str, side: str) -> dict | None:
    """
    Возвращает позицию для конкретной стороны (long/short) или None.
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Нет ключей BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    resp = http.get_positions(category="linear", symbol=symbol)
    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    items = resp["result"]["list"] or []

    idx_map = {"long": 1, "short": 2}
    idx = idx_map.get(side.lower())
    if idx is None:
        raise ValueError("side должен быть 'long' или 'short'")

    for p in items:
        if int(p.get("positionIdx", 0)) == idx:
            if float(p.get("size", "0")) != 0:  # открытая позиция
                return p
            break
    return None

if __name__ == "__main__":
    try:
        pos = get_position_side_for_hedg(SYMBOL, SIDE)
        if pos:
            print(pos)
        else:
            print("нет позиции")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
