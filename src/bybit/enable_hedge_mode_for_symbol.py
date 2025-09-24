# -*- coding: utf-8 -*-
"""
Включение хедж-режима (Both Sides) для КОНКРЕТНОГО символа на Bybit V5.
- category="linear" (USDT перпетуалы)
- Символ задаётся вверху
- Ключи читаются из .env
- Итог: печатает "SUCCESS" или "ERROR: ..."
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Символ
SYMBOL = "BTCUSDT"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def enable_hedge_mode_for_symbol(symbol: str) -> None:
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Нет BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    # /v5/position/switch-mode  — mode: 0=One-Way, 3=Hedge
    resp = http.switch_position_mode(category="linear", symbol=symbol, mode=3) #mode=1 - выключение хеджа

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

if __name__ == "__main__":
    try:
        enable_hedge_mode_for_symbol(SYMBOL)
        print("SUCCESS")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
