# -*- coding: utf-8 -*-
"""
Выставление условного (trigger/stop) рыночного входного ордера (Bybit V5).
- Работает на линейных фьючерсах (category="linear").
- Ключи читаются из .env.
- В коде задаём параметры ордера (symbol, side, qty, trigger_price, trigger_direction).
- Итог: печатает "SUCCESS <orderId>" или "ERROR: ...".
"""

import os
import sys
import uuid
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# 🔧 Параметры ордера
SYMBOL = "BTCUSDT"
SIDE = "Buy"             # "Buy" или "Sell"
QTY = "0.001"            # количество
TRIGGER_PRICE = "115500" # цена срабатывания
TRIGGER_BY = "LastPrice" # "LastPrice", "MarkPrice" или "IndexPrice"
TRIGGER_DIRECTION = 2    # 1 = выше триггера, 2 = ниже триггера

def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}

def place_conditional_market_order(symbol: str, side: str, qty: str,
                                   trigger_price: str, trigger_direction: int,
                                   trigger_by: str="LastPrice") -> str:
    """
    Создаёт условный рыночный ордер.
    Возвращает orderId при успехе, поднимает RuntimeError при ошибке.
    """
    load_dotenv()
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))
    if not api_key or not api_secret:
        raise RuntimeError("Нет ключей BYBIT_API_KEY/BYBIT_API_SECRET в .env")

    http = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret,
                timeout=10_000, recv_window=5_000)

    resp = http.place_order(
        category="linear",
        symbol=symbol,
        side=side,
        orderType="Market",
        qty=qty,
        triggerPrice=trigger_price,
        triggerDirection=trigger_direction,
        triggerBy=trigger_by,
        stopOrderType="Stop",
        timeInForce="IOC",
        orderLinkId=f"cond-{uuid.uuid4().hex[:10]}"
    )

    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    return resp["result"]["orderId"]

if __name__ == "__main__":
    try:
        oid = place_conditional_market_order(SYMBOL, SIDE, QTY, TRIGGER_PRICE, TRIGGER_DIRECTION, TRIGGER_BY)
        print(f"SUCCESS {oid}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
