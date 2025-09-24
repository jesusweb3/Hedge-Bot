# -*- coding: utf-8 -*-
"""
Отмена ордера по ID (Bybit V5, деривативы linear).
- SYMBOL и ORDER_ID задаём ниже.
- ORDER_ID можно указывать полным UUID или хвостом из 8 символов.
- Ищем среди открытых ордеров по символу; при хвосте — восстанавливаем полный ID.
- Вывод: "SUCCESS <orderId>" | "NOT FOUND" | "ERROR: ...".
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 укажи символ и id
SYMBOL = "BTCUSDT"
ORDER_ID = "42fae275"  # полный UUID или последние 8 символов

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1","true","yes","y","on"}

def _is_tail(s: str) -> bool:
    s = (s or "").strip()
    return len(s) == 8 and all(ch in "0123456789abcdefABCDEF" for ch in s)

def _match(target: str, candidate: str) -> bool:
    t = (target or "").strip().lower()
    c = (candidate or "").strip().lower()
    return c == t or (_is_tail(t) and c.endswith(t))

def cancel_order_by_id(symbol: str, order_id: str) -> str | None:
    """
    Отменяет ордер по ID, возвращает orderId при успехе, None если не найден среди открытых.
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))
    if not api_key or not api_secret:
        raise RuntimeError("Нет BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    full_id = order_id

    # Если передан хвост из 8 символов — найдём полный ID среди открытых ордеров
    if _is_tail(order_id):
        r = http.get_open_orders(category="linear", symbol=symbol)
        if not isinstance(r, dict) or r.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error (open): {r}")
        found_full_id = None
        for order in r.get("result", {}).get("list") or []:
            candidate_id = order.get("orderId", "")
            if _match(order_id, candidate_id):
                found_full_id = candidate_id
                break
        if not found_full_id:
            return None
        full_id = found_full_id

    # Отмена (работает и для условных ордеров)
    resp = http.cancel_order(category="linear", symbol=symbol, orderId=full_id)
    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error (cancel): {resp}")

    return full_id

if __name__ == "__main__":
    try:
        cancelled_id = cancel_order_by_id(SYMBOL, ORDER_ID)
        if cancelled_id:
            print(f"SUCCESS {cancelled_id}")
        else:
            print("NOT FOUND")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
