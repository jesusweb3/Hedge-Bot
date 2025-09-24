# -*- coding: utf-8 -*-
"""
Отмена всех ордеров по символу (Bybit V5, деривативы linear).
- Укажи SYMBOL ниже.
- Скрипт считает открытые ордера, вызывает cancel_all, затем проверяет остаток.
- Итог: печатает число отменённых ордеров или ошибку.
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Символ
SYMBOL = "BTCUSDT"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1","true","yes","y","on"}

def cancel_all_for_symbol(symbol: str) -> int:
    """
    Отменяет все открытые ордера по symbol.
    Возвращает количество отменённых ордеров.
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))
    if not api_key or not api_secret:
        raise RuntimeError("Нет BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    # 1) Сколько ордеров открыто сейчас
    r_before = http.get_open_orders(category="linear", symbol=symbol)
    if not isinstance(r_before, dict) or r_before.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error (get_open_orders): {r_before}")
    before_list = r_before.get("result", {}).get("list") or []
    before_cnt = len(before_list)

    if before_cnt == 0:
        return 0

    # 2) Отменяем все
    r_cancel = http.cancel_all_orders(category="linear", symbol=symbol)
    if not isinstance(r_cancel, dict) or r_cancel.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error (cancel_all_orders): {r_cancel}")

    # 3) Проверяем остаток
    r_after = http.get_open_orders(category="linear", symbol=symbol)
    if not isinstance(r_after, dict) or r_after.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error (get_open_orders after): {r_after}")
    after_list = r_after.get("result", {}).get("list") or []
    after_cnt = len(after_list)

    cancelled = max(0, before_cnt - after_cnt)
    return cancelled

if __name__ == "__main__":
    try:
        n = cancel_all_for_symbol(SYMBOL)
        print(n)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
