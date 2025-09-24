# -*- coding: utf-8 -*-
"""
Модуль: проверка статуса символа на Bybit (V5).
Использует pybit==5.11.0, читает BYBIT_TESTNET из .env.
В начале кода задаётся SYMBOL (например "BTCUSDT").
При запуске модуля печатает:
- "YES Trading", если можно торговать
- "NO <status>", если символ не активен
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Здесь задаём проверяемый символ
SYMBOL = "BTCUSDT"


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def check_symbol_status(symbol: str) -> tuple[bool, str]:
    """
    Проверяет статус символа на Bybit.
    Возвращает (is_trading: bool, status: str).
    """
    load_dotenv()
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    http = HTTP(testnet=testnet, timeout=10_000, recv_window=5_000)

    resp = http.get_instruments_info(category="linear", symbol=symbol)

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    instruments = resp["result"]["list"]
    if not instruments:
        return False, "NotFound"

    status = instruments[0].get("status", "Unknown")
    return status == "Trading", status


if __name__ == "__main__":
    try:
        ok, reason = check_symbol_status(SYMBOL)
        if ok:
            print(f"YES {reason}")
        else:
            print(f"NO {reason}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
