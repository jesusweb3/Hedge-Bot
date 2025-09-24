# -*- coding: utf-8 -*-
"""
Модуль: проверка, включён ли Hedge для КОНКРЕТНОГО символа (Bybit V5).
Логика: /v5/position/list с category="linear" и symbol=..., смотрим positionIdx.
- Hedge: в списке есть и 1, и 2 (две стороны)
- One-Way: единственная запись с positionIdx=0 (или одна сторона)
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Укажи символ здесь
SYMBOL = "BTCUSDT"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def check_hedge_mode(symbol: str) -> bool:
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Нет BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret, timeout=10_000, recv_window=5_000)

    # Важно: передаем symbol, чтобы получить записи даже при отсутствии позиций
    resp = http.get_positions(category="linear", symbol=symbol)
    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    items = resp["result"]["list"] or []
    idxs = {int(i.get("positionIdx", 0)) for i in items}

    # Hedge = обе стороны доступны (1 и 2)
    return 1 in idxs and 2 in idxs

if __name__ == "__main__":
    try:
        enabled = check_hedge_mode(SYMBOL)
        print("Включен" if enabled else "Выключен")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
