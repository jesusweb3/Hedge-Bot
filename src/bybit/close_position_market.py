# -*- coding: utf-8 -*-
"""
Рыночное закрытие позиции с reduce-only для Bybit V5 (linear).
- Укажи SYMBOL и SIDE ("long" или "short") ниже.
- Модуль сам определит positionIdx (1 для long, 2 для short при Hedge; 0/отсутствует в One-Way).
- Печатает: "SUCCESS <orderId>" | "NO POSITION" | "ERROR: ...".
"""

import os
import sys
import uuid
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Настройки
SYMBOL = "BTCUSDT"
SIDE = "long"   # "long" или "short"

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def close_position_market(symbol: str, side: str) -> str | None:
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    if not api_key or not api_secret:
        raise RuntimeError("Нет ключей BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    side = side.lower().strip()
    if side not in {"long", "short"}:
        raise ValueError("SIDE должен быть 'long' или 'short'")

    # 1) Получаем позиции по символу
    resp_pos = http.get_positions(category="linear", symbol=symbol)
    if not isinstance(resp_pos, dict) or resp_pos.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error (positions): {resp_pos}")

    items = resp_pos["result"]["list"] or []

    # Картинка соответствия:
    # Hedge mode: long -> positionIdx=1 (side=Buy), short -> positionIdx=2 (side=Sell)
    # One-Way   : обычно одна запись с positionIdx=0/1 и side Buy/Sell в зависимости от направления
    target = None
    for p in items:
        p_side = (p.get("side") or "").lower()
        p_size = float(p.get("size", "0") or "0")
        if p_size == 0:
            continue
        if side == "long" and p_side == "buy":
            target = p
            break
        if side == "short" and p_side == "sell":
            target = p
            break

    if not target:
        return None  # NO POSITION

    qty = target["size"]  # строка
    pos_idx = int(target.get("positionIdx", 0))

    # 2) Формируем ордер на закрытие
    order_side = "Sell" if side == "long" else "Buy"
    order_args = dict(
        category="linear",
        symbol=symbol,
        side=order_side,
        orderType="Market",
        qty=qty,
        timeInForce="IOC",
        reduceOnly=True,
        orderLinkId=f"close-{uuid.uuid4().hex[:10]}",
    )

    # В Hedge-режиме ОБЯЗАТЕЛЕН корректный positionIdx (1 для long, 2 для short)
    # В One-Way можно не указывать (или pos_idx будет 0/1 — биржа примет).
    if pos_idx in (1, 2):
        order_args["positionIdx"] = pos_idx

    resp_order = http.place_order(**order_args)
    if not isinstance(resp_order, dict) or resp_order.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error (order): {resp_order}")

    return resp_order["result"]["orderId"]

if __name__ == "__main__":
    try:
        order_id = close_position_market(SYMBOL, SIDE)
        if order_id:
            print(f"SUCCESS {order_id}")
        else:
            print("NO POSITION")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
