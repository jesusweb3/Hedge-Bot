# -*- coding: utf-8 -*-
"""
Поиск ордера по ID (Bybit V5, деривативы linear).
- Сначала ищем среди ОТКРЫТЫХ ордеров по указанному символу.
- Если не найден — ищем в ИСТОРИИ с пагинацией.
- Поддерживается полный UUID и "хвост" из 8 символов (как в UI).
Выводит словарь ордера или "не найден".
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Укажи символ и ID ордера (полный UUID или последние 8 символов)
SYMBOL = "BTCUSDT"
ORDER_ID = "8730b59c"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1","true","yes","y","on"}

def _is_tail_id(s: str) -> bool:
    s = (s or "").strip()
    return len(s) == 8 and all(ch in "0123456789abcdefABCDEF" for ch in s)

def _id_match(target: str, candidate: str) -> bool:
    t = (target or "").strip().lower()
    c = (candidate or "").strip().lower()
    return c == t or (_is_tail_id(t) and c.endswith(t))

def get_order_info(symbol: str, order_id: str) -> dict | None:
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))
    if not api_key or not api_secret:
        raise RuntimeError("Нет BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    # ---------- 1) Пытаемся найти среди ОТКРЫТЫХ ордеров по symbol ----------
    # Если ID полный — попробуем прямой фильтр, это быстрее
    if not _is_tail_id(order_id) and len(order_id) > 8:
        r = http.get_open_orders(category="linear", symbol=symbol, orderId=order_id)
        if isinstance(r, dict) and r.get("retCode") == 0:
            items = r.get("result", {}).get("list") or []
            if items:
                return items[0]

    # Иначе берём весь список по symbol и ищем совпадение по хвосту/полю
    r = http.get_open_orders(category="linear", symbol=symbol)
    if not isinstance(r, dict) or r.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error (open): {r}")
    for o in r.get("result", {}).get("list") or []:
        if _id_match(order_id, o.get("orderId", "")):
            return o

    # ---------- 2) Ищем в ИСТОРИИ с пагинацией ----------
    # Если ID полный — используем фильтр orderId (сервер сам найдёт быстрее)
    cursor = None
    pages = 0
    while pages < 10:  # лимит страниц на всякий случай
        kwargs = {"category": "linear", "symbol": symbol}
        if cursor:
            kwargs["cursor"] = cursor
        if not _is_tail_id(order_id) and len(order_id) > 8:
            kwargs["orderId"] = order_id

        r_hist = http.get_order_history(**kwargs)
        if not isinstance(r_hist, dict) or r_hist.get("retCode") != 0:
            raise RuntimeError(f"Bybit API error (history): {r_hist}")

        items = r_hist.get("result", {}).get("list") or []
        for o in items:
            if _id_match(order_id, o.get("orderId", "")):
                return o

        cursor = r_hist.get("result", {}).get("nextPageCursor")
        pages += 1
        if not cursor:
            break

    return None

if __name__ == "__main__":
    try:
        info = get_order_info(SYMBOL, ORDER_ID)
        if info:
            print(info)
        else:
            print("не найден")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
