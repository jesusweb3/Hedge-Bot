# -*- coding: utf-8 -*-
"""
Модуль: получение серверного времени Bybit (V5).
Использует pybit==5.11.0, читает BYBIT_TESTNET из .env.
При запуске модуля печатает serverTime (таймстамп в мс).
"""

import os
import sys
from dotenv import load_dotenv
from pybit.unified_trading import HTTP


def _str_to_bool(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def get_server_time() -> int:
    """
    Возвращает текущее серверное время Bybit (timestamp в мс).
    """
    load_dotenv()
    testnet = _str_to_bool(os.getenv("BYBIT_TESTNET"))

    http = HTTP(testnet=testnet, timeout=10_000, recv_window=5_000)

    resp = http.get_server_time()
    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise RuntimeError(f"Bybit API error: {resp}")

    try:
        server_time = int(resp["result"]["timeSecond"]) * 1000
        return server_time
    except KeyError:
        # fallback на поле timeNano, если будет
        if "result" in resp and "timeNano" in resp["result"]:
            return int(resp["result"]["timeNano"]) // 1_000_000
        raise RuntimeError(f"Непредвиденный ответ Bybit: {resp}")


if __name__ == "__main__":
    try:
        ts = get_server_time()
        print(ts)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
