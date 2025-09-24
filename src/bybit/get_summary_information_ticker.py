# -*- coding: utf-8 -*-
"""
Модуль: получение сводного тикера 24h по символу на Bybit (V5).
Работает с фьючерсным рынком (category="linear").
Читает BYBIT_TESTNET из .env.
В начале кода задаётся SYMBOL (например "BTCUSDT").
При запуске печатает словарь с данными 24h.
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Символ указываем здесь
SYMBOL = "BTCUSDT"


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def get_summary_information_ticker(symbol: str) -> dict:
    """
    Возвращает словарь с данными 24h по символу.
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
        "change_pct": float(t["price24hPcnt"]) * 100,  # в %
        "high": float(t["highPrice24h"]),
        "low": float(t["lowPrice24h"]),
        "volume": float(t["volume24h"]),     # в базовой валюте
        "turnover": float(t["turnover24h"]), # в USDT
    }


if __name__ == "__main__":
    try:
        info = get_summary_information_ticker(SYMBOL)
        print(info)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
